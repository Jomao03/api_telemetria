import asyncio
import os
import random
import logging
from datetime import datetime, timezone
import httpx  # <- Nueva librería para hacer peticiones web

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
INTERVALO_SEGUNDOS = float(os.getenv("INTERVALO_SEGUNDOS", "2"))
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def enviar_a_la_nube(cliente, payload):
    """Envía los datos reales a la API de FastAPI usando HTTP asíncrono"""
    
    # 1. Simulamos que la red de la planta falla físicamente a veces (10%)
    if random.random() < 0.10:
        raise ConnectionError("Falla física: Se perdió la señal WiFi.")

    # 2. El cliente asíncrono hace la petición real al puerto 8000
    try:
        respuesta = await cliente.post("/telemetria", json=payload)
        respuesta.raise_for_status()
    except httpx.ConnectError:
        raise ConnectionError("El Gateway (API) está apagado o inalcanzable.")

async def simular_sensor(cliente, id_sensor, voltaje_base):
    logging.info(f"Iniciando sensor {id_sensor}...")
    
    espera_reintento = 1
    while True:
        try:
            ruido = random.uniform(-0.5, 0.5)
            voltaje_actual = round(voltaje_base + ruido, 2)
            
            if random.random() < 0.05:  
                voltaje_actual = round(voltaje_actual * 1.5, 2)
            
            payload = {
                "sensor_id": id_sensor,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "voltaje": voltaje_actual
            }
            
            # Intenta enviar por HTTP real
            await enviar_a_la_nube(cliente, payload)
            logging.info(f"[{id_sensor}] Dato enviado a la API: {voltaje_actual}V")
            espera_reintento = 1
            
        except ConnectionError as error_red:
            logging.warning(f"[{id_sensor}] {error_red}. Reintentando en {espera_reintento}s...")
            await asyncio.sleep(espera_reintento)
            espera_reintento = min(espera_reintento * 2, 30)
            continue
        except httpx.HTTPError as error_http:
            logging.warning(f"[{id_sensor}] Error HTTP: {error_http}. Reintentando en {espera_reintento}s...")
            await asyncio.sleep(espera_reintento)
            espera_reintento = min(espera_reintento * 2, 30)
            continue
            
        await asyncio.sleep(INTERVALO_SEGUNDOS)

async def main():
    logging.info(f"Arrancando sistema de telemetría industrial contra {API_URL}...")
    async with httpx.AsyncClient(base_url=API_URL, timeout=5.0) as cliente:
        await asyncio.gather(
            simular_sensor(cliente, "NODO_01", voltaje_base=24.0),
            simular_sensor(cliente, "NODO_02", voltaje_base=12.0)
        )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("\nApagado manual detectado.")
