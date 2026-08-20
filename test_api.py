from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api import app, obtener_base_datos
from database import Base

TIMESTAMP_VALIDO = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

# 1. El Cliente de Pruebas: Es un simulador que puede hablar con tu API sin necesidad de encender el servidor con Uvicorn.
@pytest.fixture()
def client(tmp_path):
    """Cada prueba usa una base SQLite desechable, sin tocar datos locales."""
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    sesion_prueba = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def obtener_bd_prueba():
        bd = sesion_prueba()
        try:
            yield bd
        finally:
            bd.close()

    app.dependency_overrides[obtener_base_datos] = obtener_bd_prueba
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()

def test_guardia_de_seguridad_rechaza_voltaje_extremo(client):
    """
    Objetivo: Comprobar que Pydantic bloquea voltajes irreales.
    """
    # Preparamos un paquete de datos "venenoso" (150 Voltios es físicamente imposible en nuestro sistema)
    payload_malo = {
        "sensor_id": "NODO_HACKER",
        "timestamp": "2026-08-19T12:00:00",
        "voltaje": 150.0 
    }
    
    # Disparamos el dato a nuestra API
    respuesta = client.post("/telemetria", json=payload_malo)
    
    # 2. La Afirmación (Assert): Aquí es donde ocurre la magia matemática de la prueba.
    # El código de estado HTTP 422 significa "Entidad no procesable" (Datos inválidos).
    # Le decimos a Python: "Te exijo que la respuesta sea 422. Si la API acepta el dato (200), la prueba falla".
    assert respuesta.status_code == 422
    
def test_guardia_de_seguridad_acepta_dato_correcto(client):
    """
    Objetivo: Comprobar que la API funciona bien en condiciones normales.
    """
    payload_bueno = {
        "sensor_id": "NODO_NORMAL",
        "timestamp": TIMESTAMP_VALIDO,
        "voltaje": 24.5
    }
    
    respuesta = client.post("/telemetria", json=payload_bueno)
    
    assert respuesta.status_code == 201
    assert respuesta.json()["sensor_id"] == "NODO_NORMAL"


def test_analitica_calcula_metricas_y_alerta(client):
    for voltaje in (25.0, 27.0, 28.0):
        respuesta = client.post("/telemetria", json={
            "sensor_id": "NODO_ANALITICO", "timestamp": TIMESTAMP_VALIDO, "voltaje": voltaje
        })
        assert respuesta.status_code == 201

    respuesta = client.get("/analitica/NODO_ANALITICO")
    assert respuesta.status_code == 200
    assert respuesta.json()["cantidad_mediciones"] == 3
    assert respuesta.json()["promedio_reciente_v"] == 26.67
    assert respuesta.json()["alerta_sobretension"] is True


def test_sensor_sin_datos_devuelve_404(client):
    assert client.get("/analitica/SENSOR_INEXISTENTE").status_code == 404
