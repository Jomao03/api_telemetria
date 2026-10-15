from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import FastAPI, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import SesionLocal, RegistroTelemetria, OrdenMantenimientoIA, crear_tablas
from ml_engine import detector_onnx

LIMITE_SOBRETENSION_V = 26.0

@asynccontextmanager
async def lifespan(_: FastAPI):
    crear_tablas()
    yield

app = FastAPI(
    title="IndusTwin AI - Gateway IIoT & Mantenimiento Predictivo",
    version="2.0.0",
    description="Plataforma IIoT con ingesta MQTT/HTTP, inferencia ONNX y Copilot RAG para diagnóstico industrial.",
    lifespan=lifespan,
)

# Validador Pydantic Multivariable (retrocompatible con tests antiguos)
class MedicionIoT(BaseModel):
    sensor_id: Annotated[str, Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$", description="ID del equipo físico")]
    timestamp: datetime
    voltaje: Annotated[float, Field(gt=0, lt=500, description="Lectura en voltios (V)")]
    corriente: Annotated[float, Field(ge=0, lt=200, default=5.0, description="Corriente en amperios (A)")]
    temperatura_c: Annotated[float, Field(gt=-20, lt=250, default=45.0, description="Temperatura del rodamiento (°C)")]
    vibracion_mm_s: Annotated[float, Field(ge=0, lt=100, default=1.8, description="Vibración RMS (mm/s)")]

    @field_validator("timestamp")
    @classmethod
    def timestamp_debe_tener_zona_horaria(cls, valor: datetime) -> datetime:
        if valor.tzinfo is None or valor.utcoffset() is None:
            raise ValueError("timestamp debe incluir zona horaria, por ejemplo 2026-08-19T12:00:00Z")
        if valor > datetime.now(timezone.utc):
            raise ValueError("timestamp no puede estar en el futuro")
        return valor

class MedicionRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sensor_id: str
    timestamp: datetime
    voltaje: float
    corriente: float
    temperatura_c: float
    vibracion_mm_s: float
    anomalias_detectadas: bool
    score_anomalia: float

class AnaliticaRespuesta(BaseModel):
    sensor: str
    cantidad_mediciones: int
    promedio_reciente_v: float
    minimo_reciente_v: float
    maximo_reciente_v: float
    temperatura_max_c: float
    vibracion_max_mm_s: float
    alerta_sobretension: bool
    limite_sobretension_v: float
    ultimas_mediciones: list[MedicionRespuesta]

class OrdenIARespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sensor_id: str
    timestamp: datetime
    severidad: str
    causa_raiz: str
    procedimiento_recomendado: str

def obtener_base_datos():
    bd = SesionLocal()
    try:
        yield bd 
    finally:
        bd.close() 

@app.get("/health", tags=["operacion"])
def healthcheck():
    return {"status": "ok"}

@app.post("/telemetria", response_model=MedicionRespuesta, status_code=status.HTTP_201_CREATED, tags=["telemetria"])
def recibir_datos(medicion: MedicionIoT, bd: Session = Depends(obtener_base_datos)):
    es_anomalia, score = detector_onnx.evaluar_medicion(
        medicion.voltaje, medicion.corriente, medicion.temperatura_c, medicion.vibracion_mm_s
    )
    nuevo_registro = RegistroTelemetria(
        **medicion.model_dump(),
        anomalias_detectadas=es_anomalia,
        score_anomalia=score,
    )
    try:
        bd.add(nuevo_registro)
        bd.commit()
        bd.refresh(nuevo_registro)
    except SQLAlchemyError as error:
        bd.rollback()
        raise HTTPException(status_code=503, detail="No fue posible guardar la medición") from error
    return nuevo_registro

@app.get("/telemetria/{sensor_id}", response_model=list[MedicionRespuesta], tags=["telemetria"])
def listar_mediciones(
    sensor_id: str,
    limite: Annotated[int, Query(ge=1, le=100)] = 20,
    bd: Session = Depends(obtener_base_datos),
):
    return bd.query(RegistroTelemetria).filter(RegistroTelemetria.sensor_id == sensor_id).order_by(RegistroTelemetria.timestamp.desc()).limit(limite).all()

@app.get("/analitica/{sensor_id}", response_model=AnaliticaRespuesta, tags=["analitica"])
def obtener_historial(
    sensor_id: str,
    limite: Annotated[int, Query(ge=1, le=100)] = 10,
    bd: Session = Depends(obtener_base_datos),
):
    historial = listar_mediciones(sensor_id=sensor_id, limite=limite, bd=bd)
    if not historial:
        raise HTTPException(status_code=404, detail=f"No se encontraron datos para el sensor {sensor_id}")
        
    lista_voltajes = [r.voltaje for r in historial]
    lista_temp = [r.temperatura_c for r in historial]
    lista_vib = [r.vibracion_mm_s for r in historial]
    promedio = sum(lista_voltajes) / len(lista_voltajes)
    
    return {
        "sensor": sensor_id,
        "cantidad_mediciones": len(historial),
        "promedio_reciente_v": round(promedio, 2),
        "minimo_reciente_v": round(min(lista_voltajes), 2),
        "maximo_reciente_v": round(max(lista_voltajes), 2),
        "temperatura_max_c": round(max(lista_temp), 2),
        "vibracion_max_mm_s": round(max(lista_vib), 2),
        "alerta_sobretension": promedio > LIMITE_SOBRETENSION_V,
        "limite_sobretension_v": LIMITE_SOBRETENSION_V,
        "ultimas_mediciones": historial,
    }

@app.get("/ordenes-ia/{sensor_id}", response_model=list[OrdenIARespuesta], tags=["ia-copilot"])
def listar_ordenes_ia(
    sensor_id: str,
    limite: Annotated[int, Query(ge=1, le=50)] = 10,
    bd: Session = Depends(obtener_base_datos),
):
    """Devuelve los diagnósticos y órdenes de trabajo generados por el Agente RAG."""
    return bd.query(OrdenMantenimientoIA).filter(OrdenMantenimientoIA.sensor_id == sensor_id).order_by(OrdenMantenimientoIA.timestamp.desc()).limit(limite).all()