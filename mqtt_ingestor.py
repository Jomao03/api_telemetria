import json
import logging
import os
import redis
import paho.mqtt.client as mqtt

from api import MedicionIoT
from database import SesionLocal, RegistroTelemetria, crear_tablas
from ml_engine import detector_onnx
from celery_worker import diagnosticar_anomalia_rag

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [MQTT-INGESTOR] - %(levelname)s - %(message)s")

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = "planta/sensores/+/telemetria"

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
cliente_redis = redis.from_url(REDIS_URL, decode_responses=True)

def al_conectar(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        logging.info(f"Conectado exitosamente al Broker MQTT ({MQTT_BROKER}:{MQTT_PORT})")
        client.subscribe(MQTT_TOPIC, qos=1)
        logging.info(f"Suscrito al tópico industrial: {MQTT_TOPIC}")
    else:
        logging.error(f"Fallo al conectar al Broker MQTT. Código: {reason_code}")

def al_recibir_mensaje(client, userdata, msg):
    try:
        datos_crudos = json.loads(msg.payload.decode("utf-8"))
        # 1. Validamos con Pydantic
        medicion_valida = MedicionIoT(**datos_crudos)

        # 2. Inferencia en tiempo real con ONNX Runtime (<1ms)
        es_anomalia, score = detector_onnx.evaluar_medicion(
            medicion_valida.voltaje,
            medicion_valida.corriente,
            medicion_valida.temperatura_c,
            medicion_valida.vibracion_mm_s,
        )

        # 3. Guardamos en TimescaleDB incluyendo el diagnóstico del modelo ONNX
        with SesionLocal() as bd:
            registro = RegistroTelemetria(
                **medicion_valida.model_dump(),
                anomalias_detectadas=es_anomalia,
                score_anomalia=score,
            )
            bd.add(registro)
            bd.commit()

        # 4. Actualizamos la ventana deslizante en Redis (últimas 10 lecturas)
        clave_ventana = f"ventana:{medicion_valida.sensor_id}"
        datos_crudos["es_anomalia"] = es_anomalia
        datos_crudos["score_anomalia"] = score
        cliente_redis.lpush(clave_ventana, json.dumps(datos_crudos))
        cliente_redis.ltrim(clave_ventana, 0, 9)

        if es_anomalia:
            logging.warning(
                f"🚨 [ONNX ALERTA] Anomalía en {medicion_valida.sensor_id} | Severidad: {score} | "
                f"I: {medicion_valida.corriente}A | T: {medicion_valida.temperatura_c}°C | Vib: {medicion_valida.vibracion_mm_s} mm/s"
            )
            # Candado anti-spam en Redis (1 orden IA máximo cada 60s por equipo)
            candado_key = f"cooldown_ia:{medicion_valida.sensor_id}"
            if cliente_redis.set(candado_key, "1", nx=True, ex=60):
                logging.info(f"📤 Enviando tarea asíncrona a Celery Worker para {medicion_valida.sensor_id}...")
                diagnosticar_anomalia_rag.delay(datos_crudos)
        else:
            logging.info(
                f"[{medicion_valida.sensor_id}] Normal (ONNX OK) | "
                f"V: {medicion_valida.voltaje}V | I: {medicion_valida.corriente}A | "
                f"T: {medicion_valida.temperatura_c}°C | Vib: {medicion_valida.vibracion_mm_s} mm/s"
            )
    except Exception as e:
        logging.error(f"Error procesando mensaje MQTT en {msg.topic}: {e}")

def iniciar_ingestor():
    crear_tablas()
    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ingestor_central_iiot")
    cliente.on_connect = al_conectar
    cliente.on_message = al_recibir_mensaje

    logging.info(f"Conectando a {MQTT_BROKER}:{MQTT_PORT}...")
    cliente.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    cliente.loop_forever()

if __name__ == "__main__":
    iniciar_ingestor()