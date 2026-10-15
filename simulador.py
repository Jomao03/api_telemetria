import asyncio
import json
import logging
import os
import random
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
INTERVALO_SEGUNDOS = float(os.getenv("INTERVALO_SEGUNDOS", "2"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [PLC-SIM] - %(levelname)s - %(message)s")

def generar_telemetria_fisica(id_sensor: str, voltaje_base: float) -> dict:
    """Simula el comportamiento físico acoplado de un motor industrial."""
    voltaje = voltaje_base + random.uniform(-0.4, 0.4)
    corriente = 5.2 + random.uniform(-0.3, 0.3)
    temperatura = 48.0 + random.uniform(-1.5, 1.5)
    vibracion = 1.8 + random.uniform(-0.2, 0.2)

    # 10% de probabilidad de simular desgaste mecánico de rodamiento / sobrecarga
    if random.random() < 0.10:
        logging.warning(f"⚠️ [{id_sensor}] Inyectando patrón de anomalía electro-mecánica...")
        corriente += random.uniform(3.5, 6.0)       # El motor pide más corriente por fricción
        temperatura += random.uniform(20.0, 35.0)   # Calentamiento en el eje
        vibracion += random.uniform(5.5, 9.0)       # Vibración severa (>7.1 mm/s es zona crítica ISO 10816)

    return {
        "sensor_id": id_sensor,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "voltaje": round(voltaje, 2),
        "corriente": round(corriente, 2),
        "temperatura_c": round(temperatura, 2),
        "vibracion_mm_s": round(vibracion, 2),
    }

async def simular_plc_mqtt(cliente_mqtt: mqtt.Client, id_sensor: str, voltaje_base: float):
    topico = f"planta/sensores/{id_sensor}/telemetria"
    logging.info(f"Publicando telemetría de {id_sensor} en tópico MQTT: {topico}")

    while True:
        payload = generar_telemetria_fisica(id_sensor, voltaje_base)
        info = cliente_mqtt.publish(topico, json.dumps(payload), qos=1)
        if info.rc == mqtt.MQTT_ERR_SUCCESS:
            logging.info(f"[{id_sensor}] MQTT TX -> V:{payload['voltaje']}V | T:{payload['temperatura_c']}°C | Vib:{payload['vibracion_mm_s']}mm/s")
        else:
            logging.error(f"[{id_sensor}] Error al publicar en MQTT (rc={info.rc})")
        await asyncio.sleep(INTERVALO_SEGUNDOS)

async def main():
    cliente_mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="plc_edge_simulator")
    cliente_mqtt.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    cliente_mqtt.loop_start()

    try:
        await asyncio.gather(
            simular_plc_mqtt(cliente_mqtt, "MOTOR_BOMBA_01", voltaje_base=24.0),
            simular_plc_mqtt(cliente_mqtt, "COMPRESOR_02", voltaje_base=24.0),
        )
    finally:
        cliente_mqtt.loop_stop()
        cliente_mqtt.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Simulador detenido manualmente.")