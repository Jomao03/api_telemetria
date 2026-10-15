import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.orm import declarative_base, sessionmaker

# 1. El Motor: Usa PostgreSQL/TimescaleDB en Docker, o SQLite por defecto en local/tests
URL_BASE_DATOS = os.getenv("DATABASE_URL", "sqlite:///./telemetria.db")
opciones_motor = {"connect_args": {"check_same_thread": False}} if URL_BASE_DATOS.startswith("sqlite") else {}
motor = create_engine(URL_BASE_DATOS, **opciones_motor)

# 2. La Sesión
SesionLocal = sessionmaker(autocommit=False, autoflush=False, bind=motor)

# 3. La Base
Base = declarative_base()

# 4. Modelo ORM 1: Telemetría Física Multivariable
class RegistroTelemetria(Base):
    __tablename__ = "historial_telemetria"

    id = Column(Integer, primary_key=True)
    sensor_id = Column(String(64), index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), index=True, nullable=False)
    
    # Variables físicas del equipo industrial
    voltaje = Column(Float, nullable=False)
    corriente = Column(Float, nullable=False, default=5.0)         # Amperios (A)
    temperatura_c = Column(Float, nullable=False, default=45.0)    # Grados Celsius (°C)
    vibracion_mm_s = Column(Float, nullable=False, default=1.8)    # Velocidad RMS (mm/s - ISO 10816)
    
    # Resultados del motor de IA (ONNX)
    anomalias_detectadas = Column(Boolean, default=False, nullable=False)
    score_anomalia = Column(Float, default=0.0, nullable=False)

# 5. Modelo ORM 2: Diagnósticos generados por el Agente RAG (LangGraph + Qdrant)
class OrdenMantenimientoIA(Base):
    __tablename__ = "ordenes_mantenimiento_ia"

    id = Column(Integer, primary_key=True)
    sensor_id = Column(String(64), index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    severidad = Column(String(32), nullable=False)                 
    causa_raiz = Column(Text, nullable=False)                      
    procedimiento_recomendado = Column(Text, nullable=False)       

from sqlalchemy.exc import IntegrityError, OperationalError

def crear_tablas():
    """Crea el esquema de tablas de forma segura ante arranques concurrentes en Docker."""
    try:
        Base.metadata.create_all(bind=motor, checkfirst=True)
    except (IntegrityError, OperationalError):
        # Si otro contenedor hermano (ej. api-iot) acaba de crear la tabla en el mismo milisegundo,
        # ignoramos la colisión porque la tabla ya quedó creada exitosamente.
        pass