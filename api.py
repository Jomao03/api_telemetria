from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import FastAPI, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

# Importamos las herramientas del "bodeguero" que acabamos de crear
from database import SesionLocal, RegistroTelemetria, crear_tablas

LIMITE_SOBRETENSION_V = 26.0


@asynccontextmanager
async def lifespan(_: FastAPI):
    crear_tablas()
    yield


app = FastAPI(
    title="Gateway de Telemetría IoT",
    version="1.0.0",
    description="Recibe mediciones de sensores industriales y expone analítica reciente.",
    lifespan=lifespan,
)

# El Guardia de Seguridad (Validador Pydantic)
class MedicionIoT(BaseModel):
    sensor_id: Annotated[str, Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$", description="ID del equipo físico")]
    timestamp: datetime
    voltaje: Annotated[float, Field(gt=0, lt=100, description="Lectura en voltios")]

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


class AnaliticaRespuesta(BaseModel):
    sensor: str
    cantidad_mediciones: int
    promedio_reciente_v: float
    minimo_reciente_v: float
    maximo_reciente_v: float
    alerta_sobretension: bool
    limite_sobretension_v: float
    ultimas_mediciones: list[MedicionRespuesta]

# 1. El Administrador de Ventanillas (Inyección de Dependencia)
def obtener_base_datos():
    """Crea una sesión temporal con la BD y la cierra al terminar."""
    bd = SesionLocal()
    try:
        # yield es como un 'return' con pausa. Entrega la sesión a la API...
        yield bd 
    finally:
        # ... y cuando la API termina, el código sigue por aquí y cierra la puerta.
        bd.close() 

# 2. La Puerta de Entrada Actualizada
@app.get("/health", tags=["operacion"])
def healthcheck():
    """Punto de comprobación para Docker, despliegues y monitores."""
    return {"status": "ok"}


@app.post("/telemetria", response_model=MedicionRespuesta, status_code=status.HTTP_201_CREATED, tags=["telemetria"])
def recibir_datos(medicion: MedicionIoT, bd: Session = Depends(obtener_base_datos)):
    nuevo_registro = RegistroTelemetria(**medicion.model_dump())
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
    """Consulta paginada de las mediciones más recientes de un sensor."""
    return bd.query(RegistroTelemetria).filter(RegistroTelemetria.sensor_id == sensor_id).order_by(RegistroTelemetria.timestamp.desc()).limit(limite).all()


@app.get("/analitica/{sensor_id}", response_model=AnaliticaRespuesta, tags=["analitica"])
def obtener_historial(
    sensor_id: str,
    limite: Annotated[int, Query(ge=1, le=100)] = 10,
    bd: Session = Depends(obtener_base_datos),
):
    """
    Busca el historial y calcula métricas en tiempo real para detectar anomalías.
    """
    historial = listar_mediciones(sensor_id=sensor_id, limite=limite, bd=bd)
    
    if not historial:
        raise HTTPException(status_code=404, detail=f"No se encontraron datos para el sensor {sensor_id}")
        
    # --- 1. LÓGICA MATEMÁTICA ---
    # Extraemos solo los voltajes y calculamos el promedio
    lista_voltajes = [registro.voltaje for registro in historial]
    promedio = sum(lista_voltajes) / len(lista_voltajes)
    
    # --- 2. MOTOR DE ALERTAS ---
    # Si el promedio de las últimas 10 lecturas supera los 26V, disparamos alerta
    alerta = False
    if promedio > LIMITE_SOBRETENSION_V:
        alerta = True
        
    # 3. Respuesta enriquecida
    return {
        "sensor": sensor_id,
        "cantidad_mediciones": len(historial),
        "promedio_reciente_v": round(promedio, 2),
        "minimo_reciente_v": round(min(lista_voltajes), 2),
        "maximo_reciente_v": round(max(lista_voltajes), 2),
        "alerta_sobretension": alerta,
        "limite_sobretension_v": LIMITE_SOBRETENSION_V,
        "ultimas_mediciones": historial,
    }
