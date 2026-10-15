from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api import app, obtener_base_datos
from database import Base, OrdenMantenimientoIA
from ml_engine import detector_onnx

TIMESTAMP_VALIDO = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()


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
    """Comprueba que Pydantic bloquea voltajes fuera del rango industrial (>500V)."""
    payload_malo = {
        "sensor_id": "NODO_HACKER",
        "timestamp": TIMESTAMP_VALIDO,
        "voltaje": 600.0,
    }
    respuesta = client.post("/telemetria", json=payload_malo)
    assert respuesta.status_code == 422


def test_guardia_de_seguridad_acepta_dato_correcto(client):
    """Comprueba retrocompatibilidad y operación normal."""
    payload_bueno = {
        "sensor_id": "NODO_NORMAL",
        "timestamp": TIMESTAMP_VALIDO,
        "voltaje": 24.0,
        "corriente": 5.1,
        "temperatura_c": 48.0,
        "vibracion_mm_s": 1.8,
    }
    respuesta = client.post("/telemetria", json=payload_bueno)
    assert respuesta.status_code == 201
    datos = respuesta.json()
    assert datos["sensor_id"] == "NODO_NORMAL"
    assert datos["anomalias_detectadas"] is False


def test_inferencia_onnx_detecta_anomalia_multivariable(client):
    """Comprueba que el motor ONNX Runtime detecta degradación electro-mecánica severa."""
    es_anomalia, score = detector_onnx.evaluar_medicion(
        voltaje=24.0,
        corriente=10.5,       # Sobrecorriente
        temperatura_c=82.0,   # Sobretemperatura
        vibracion_mm_s=9.2,   # Vibración crítica ISO 10816 Zona D
    )
    assert es_anomalia is True
    assert score > 0.0


def test_analitica_calcula_metricas_multivariables_y_alerta(client):
    """Comprueba el cálculo estadístico de voltaje, temperatura y vibración."""
    for voltaje in (25.0, 27.0, 28.0):
        respuesta = client.post(
            "/telemetria",
            json={
                "sensor_id": "NODO_ANALITICO",
                "timestamp": TIMESTAMP_VALIDO,
                "voltaje": voltaje,
                "temperatura_c": 72.5,
                "vibracion_mm_s": 6.4,
            },
        )
        assert respuesta.status_code == 201

    respuesta = client.get("/analitica/NODO_ANALITICO")
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["cantidad_mediciones"] == 3
    assert datos["promedio_reciente_v"] == 26.67
    assert datos["temperatura_max_c"] == 72.5
    assert datos["vibracion_max_mm_s"] == 6.4
    assert datos["alerta_sobretension"] is True


def test_endpoint_ordenes_ia_copilot(client):
    """Comprueba que el endpoint de órdenes RAG devuelve una lista válida."""
    respuesta = client.get("/ordenes-ia/MOTOR_BOMBA_01")
    assert respuesta.status_code == 200
    assert isinstance(respuesta.json(), list)


def test_sensor_sin_datos_devuelve_404(client):
    assert client.get("/analitica/SENSOR_INEXISTENTE").status_code == 404