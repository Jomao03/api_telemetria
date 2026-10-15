# IndusTwin AI: Event-Driven IIoT Predictive Maintenance & Agentic RAG Copilot

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)
![MQTT](https://img.shields.io/badge/MQTT-Eclipse_Mosquitto-3C5280.svg)
![ONNX](https://img.shields.io/badge/ONNX_Runtime-Sub--ms_Inference-005CED.svg)
![Qdrant](https://img.shields.io/badge/Vector_DB-Qdrant-DC244C.svg)
![LangGraph](https://img.shields.io/badge/Agentic_AI-LangGraph-FF6F00.svg)
![Celery](https://img.shields.io/badge/Async_Queue-Celery_%2B_Redis-37814A.svg)
![TimescaleDB](https://img.shields.io/badge/Time_Series-TimescaleDB-FDB515.svg)

Plataforma Industrial IoT (IIoT) orientada a eventos para **mantenimiento predictivo en tiempo real** y **generación autónoma de órdenes de trabajo mediante IA Agéntica (RAG)**.

El sistema ingiere telemetría multivariable de planta vía **MQTT**, ejecuta detección de anomalías electro-mecánicas en **<1 ms con ONNX Runtime**, y despacha tareas asíncronas mediante **Celery y Redis** hacia un flujo multi-agente en **LangGraph + Qdrant** que consulta manuales técnicos (norma ISO 10816 / protocolos LOTO) para diagnosticar la causa raíz.

---

## Arquitectura del Sistema

```mermaid
graph LR
    A[PLC / Edge Simulator] -->|MQTT QoS 1| B(Eclipse Mosquitto Broker)
    B --> C[MQTT Ingestor Service]
    C -->|Sub-ms Inference| D[[ONNX Runtime Engine]]
    C -->|Time-Series Storage| E[(TimescaleDB / PostgreSQL)]
    C -->|Sliding Window & Locks| F[(Redis)]
    C -->|Anomaly Trigger| G[Celery Async Worker]
    G --> H{LangGraph Agentic Workflow}
    H -->|Semantic Search| I[(Qdrant Vector DB)]
    H -->|Work Order Persistence| E
    E --> J[FastAPI REST Gateway]
    E --> K[Grafana Real-Time Dashboard]