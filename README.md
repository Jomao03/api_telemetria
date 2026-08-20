# Gateway de Telemetría IoT

API REST en FastAPI que recibe mediciones de sensores industriales, las guarda en SQLite y entrega analítica reciente con alerta de sobretensión. Incluye un simulador asíncrono, pruebas automáticas y contenedor Docker.

## Qué demuestra

- Diseño de API REST con documentación interactiva en `/docs`.
- Validación de datos de entrada: identificador seguro, voltaje en rango y fecha con zona horaria.
- Persistencia mediante SQLAlchemy y manejo seguro de transacciones.
- Analítica de promedio, mínimo, máximo y alerta sobre un umbral configurable en código.
- Simulación de sensores y reintentos con espera incremental ante fallos de red.
- Pruebas aisladas: nunca escriben en la base de datos real.

## Ejecutarlo localmente

Requiere Python 3.10 o posterior.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn api:app --reload
```

En otra terminal, inicia el simulador:

```bash
python simulador.py
```

Abre `http://127.0.0.1:8000/docs` para probar la API. Usa timestamps ISO 8601 con zona horaria, por ejemplo `2026-08-19T12:00:00Z`.

## Endpoints

| Método | Ruta | Propósito |
| --- | --- | --- |
| GET | `/health` | Verifica que el servicio responda. |
| POST | `/telemetria` | Guarda una medición y devuelve `201 Created`. |
| GET | `/telemetria/{sensor_id}?limite=20` | Lista las últimas mediciones. |
| GET | `/analitica/{sensor_id}?limite=10` | Devuelve métricas y alerta de sobretensión. |

Ejemplo de carga válida:

```json
{
  "sensor_id": "NODO_01",
  "timestamp": "2026-08-19T12:00:00Z",
  "voltaje": 24.5
}
```

## Pruebas

```bash
pytest -q
```

## Docker

```bash
docker compose up --build
```

La base de datos queda en el volumen nombrado `telemetry_data`, así que los datos sobreviven reinicios del contenedor. Para cambiar la URL de la base en otro entorno, define `DATABASE_URL`. El simulador acepta `API_URL` e `INTERVALO_SEGUNDOS` como variables de entorno.
