import logging
import os
from celery import Celery
from database import SesionLocal, OrdenMantenimientoIA, crear_tablas
from agent_rag import grafo_copilot

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [CELERY-WORKER] - %(levelname)s - %(message)s")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "industwin_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

@celery_app.task(name="diagnosticar_anomalia_rag")
def diagnosticar_anomalia_rag(payload_alerta: dict):
    """Tarea asíncrona en segundo plano ejecutada por Celery + LangGraph + Qdrant."""
    crear_tablas()
    sensor_id = payload_alerta["sensor_id"]
    logging.info(f"🧠 Iniciando Agente RAG (LangGraph + Qdrant) para anomalía en {sensor_id}...")

    estado_inicial = {
        "sensor_id": sensor_id,
        "voltaje": payload_alerta["voltaje"],
        "corriente": payload_alerta["corriente"],
        "temperatura_c": payload_alerta["temperatura_c"],
        "vibracion_mm_s": payload_alerta["vibracion_mm_s"],
        "score_anomalia": payload_alerta["score_anomalia"],
        "contexto_rag": "",
        "titulo_manual": "",
        "severidad": "",
        "causa_raiz": "",
        "procedimiento_recomendado": "",
    }

    resultado = grafo_copilot.invoke(estado_inicial)

    with SesionLocal() as bd:
        nueva_orden = OrdenMantenimientoIA(
            sensor_id=sensor_id,
            severidad=resultado["severidad"],
            causa_raiz=resultado["causa_raiz"],
            procedimiento_recomendado=resultado["procedimiento_recomendado"],
        )
        bd.add(nueva_orden)
        bd.commit()
        bd.refresh(nueva_orden)

    logging.info(
        f"✅ Orden de Mantenimiento IA #{nueva_orden.id} creada para {sensor_id} | "
        f"Severidad: {nueva_orden.severidad} | Manual: {resultado['titulo_manual']}"
    )
    return {"orden_id": nueva_orden.id, "sensor_id": sensor_id, "severidad": nueva_orden.severidad}