import os

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# 1. El Motor: Establece la conexión. SQLite creará un archivo llamado 'telemetria.db'
URL_BASE_DATOS = os.getenv("DATABASE_URL", "sqlite:///./telemetria.db")
opciones_motor = {"connect_args": {"check_same_thread": False}} if URL_BASE_DATOS.startswith("sqlite") else {}
motor = create_engine(URL_BASE_DATOS, **opciones_motor)

# 2. La Sesión: Es la "ventana" de comunicación temporal con la base de datos
SesionLocal = sessionmaker(autocommit=False, autoflush=False, bind=motor)

# 3. La Base: Plantilla maestra de SQLAlchemy
Base = declarative_base()

# 4. El Modelo ORM: Transformamos una clase de Python en una tabla SQL
class RegistroTelemetria(Base):
    __tablename__ = "historial_telemetria"

    # Definimos las columnas y sus tipos de datos
    id = Column(Integer, primary_key=True)
    sensor_id = Column(String(64), index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), index=True, nullable=False)
    voltaje = Column(Float, nullable=False)

# 5. Ejecución: Le decimos al motor que cree físicamente la tabla si no existe
def crear_tablas():
    """Crea el esquema al iniciar la aplicación (idempotente para SQLite)."""
    Base.metadata.create_all(bind=motor)
