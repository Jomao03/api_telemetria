import hashlib
import logging
import os
from typing import TypedDict
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from langgraph.graph import StateGraph, END

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [AGENT-RAG] - %(levelname)s - %(message)s")

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLECCION_MANUALES = "manuales_industriales_iiot"
DIM_VECTOR = 64

# Base de conocimiento técnico industrial (Fragmentos de manuales SOP / ISO 10816)
MANUALES_SOP = [
    {
        "id": 1,
        "equipo": "MOTOR_BOMBA",
        "titulo": "SOP-MEC-01: Falla en Rodamientos y Desalineación de Eje (Norma ISO 10816)",
        "contenido": (
            "Cuando la velocidad RMS de vibración supera los 7.1 mm/s (Zona D - Daño Severo según ISO 10816) "
            "acompañada de un incremento de temperatura en carcasa/rodamiento (>65°C) y sobrecorriente (>8.0A), "
            "la causa raíz principal es degradación de pistas de rodamiento por fatiga superficial, falta de "
            "lubricación o desalineación angular en el acople motor-bomba. "
            "PROCEDIMIENTO: 1) Aplicar protocolo LOTO (Lockout/Tagout) y desenergizar el circuito de 24V/480V. "
            "2) Verificar alineación láser del eje. 3) Extraer rodamiento dañado con extractor hidráulico y "
            "reemplazar por serie SKF Explorer. 4) Relubricar con grasa de complejo de litio para alta temperatura."
        ),
    },
    {
        "id": 2,
        "equipo": "COMPRESOR",
        "titulo": "SOP-COMP-02: Sobrecarga Térmica y Fatiga Mecánica en Compresor",
        "contenido": (
            "Lecturas simultáneas de vibración >7.0 mm/s, corriente >8.5A y temperatura >68°C en unidades de "
            "compresión indican desgaste en válvulas de descarga, holgura excesiva en cojinetes de biela o "
            "restricción en el cabezal de descarga. "
            "PROCEDIMIENTO: 1) Ejecutar parada controlada y despresurizar el pulmón de aire (0 PSI) aplicando LOTO. "
            "2) Inspeccionar temperatura de válvulas con cámara termográfica. 3) Verificar nivel y viscosidad del "
            "aceite sintético en el cárter. 4) Reemplazar kit de sellos y rodamientos de cigüeñal."
        ),
    },
    {
        "id": 3,
        "equipo": "GENERAL",
        "titulo": "SOP-ELEC-03: Anomalía de Tensión y Desbalance Eléctrico",
        "contenido": (
            "Si el voltaje supera los 26.0V o cae por debajo de 20.0V sin incremento proporcional de vibración, "
            "existe una falla en la fuente conmutada del tablero PLC o sobretensión transitoria en el bus DC. "
            "PROCEDIMIENTO: 1) Medir rizado (ripple) con osciloscopio en la fuente de alimentación. "
            "2) Revisar borneras sulfatadas y protecciones termomagnéticas."
        ),
    },
]


def texto_a_vector_semilla(texto: str) -> list[float]:
    """
    Convierte texto técnico en un vector numérico normalizado de 64 dimensiones
    basado en n-gramas de palabras clave (sin requerir descarga de modelos pesados en CPU).
    """
    vector = [0.0] * DIM_VECTOR
    palabras = texto.lower().replace(",", " ").replace(".", " ").split()
    for palabra in palabras:
        h = int(hashlib.md5(palabra.encode("utf-8")).hexdigest(), 16)
        indice = h % DIM_VECTOR
        signo = 1.0 if (h // DIM_VECTOR) % 2 == 0 else -1.0
        vector[indice] += signo
    norma = sum(x * x for x in vector) ** 0.5 or 1.0
    return [round(x / norma, 6) for x in vector]


def inicializar_qdrant() -> QdrantClient:
    """Crea la colección vectorial en Qdrant e indexa los manuales técnicos."""
    cliente = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    colecciones = [c.name for c in cliente.get_collections().collections]

    if COLECCION_MANUALES not in colecciones:
        logging.info(f"Creando colección vectorial '{COLECCION_MANUALES}' en Qdrant...")
        cliente.create_collection(
            collection_name=COLECCION_MANUALES,
            vectors_config=VectorParams(size=DIM_VECTOR, distance=Distance.COSINE),
        )
        puntos = [
            PointStruct(
                id=doc["id"],
                vector=texto_a_vector_semilla(doc["equipo"] + " " + doc["titulo"] + " " + doc["contenido"]),
                payload=doc,
            )
            for doc in MANUALES_SOP
        ]
        cliente.upsert(collection_name=COLECCION_MANUALES, points=puntos)
        logging.info("Manuales SOP indexados exitosamente en Qdrant.")
    return cliente


# --- DEFINICIÓN DEL GRAFO MULTI-AGENTE CON LANGGRAPH ---
class EstadoAgente(TypedDict):
    sensor_id: str
    voltaje: float
    corriente: float
    temperatura_c: float
    vibracion_mm_s: float
    score_anomalia: float
    contexto_rag: str
    titulo_manual: str
    severidad: str
    causa_raiz: str
    procedimiento_recomendado: str


def nodo_recuperador_rag(state: EstadoAgente) -> dict:
    """Nodo 1: Busca en Qdrant el manual técnico más relevante para la falla."""
    cliente_qdrant = inicializar_qdrant()
    consulta = (
        f"Equipo {state['sensor_id']} vibracion {state['vibracion_mm_s']} mm/s "
        f"temperatura {state['temperatura_c']} C corriente {state['corriente']} A rodamiento sobrecarga"
    )
    vector_busqueda = texto_a_vector_semilla(consulta)

    resultados = cliente_qdrant.query_points(
        collection_name=COLECCION_MANUALES,
        query=vector_busqueda,
        limit=1,
    ).points

    if resultados:
        mejor_doc = resultados[0].payload
        return {
            "contexto_rag": mejor_doc["contenido"],
            "titulo_manual": mejor_doc["titulo"],
        }
    return {
        "contexto_rag": MANUALES_SOP[0]["contenido"],
        "titulo_manual": MANUALES_SOP[0]["titulo"],
    }


def nodo_diagnosticador_ingenieria(state: EstadoAgente) -> dict:
    """Nodo 2: Correlaciona las variables físicas con el manual recuperado de Qdrant."""
    vib = state["vibracion_mm_s"]
    temp = state["temperatura_c"]
    corr = state["corriente"]
    score = state["score_anomalia"]

    if vib > 7.1 or temp > 75.0 or score > 11.5:
        severidad = "CRÍTICA (ISO 10816 Zona D)"
    elif vib > 4.5 or temp > 60.0:
        severidad = "ALTA (ISO 10816 Zona C)"
    else:
        severidad = "MEDIA (Advertencia Predictiva)"

    # Si el usuario configura GEMINI_API_KEY, usa Gemini; de lo contrario, síntesis técnica determinista
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=api_key, temperature=0.1)
            prompt = (
                f"Actúa como Ingeniero Senior de Confiabilidad. Equipo: {state['sensor_id']}. "
                f"Telemetría: V={state['voltaje']}V, I={corr}A, T={temp}°C, Vib={vib}mm/s (Score ONNX={score}). "
                f"Basado estrictamente en este manual recuperado de Qdrant ({state['titulo_manual']}): "
                f"{state['contexto_rag']}, redacta en 2 párrafos cortos: 1) Causa raíz y 2) Procedimiento."
            )
            respuesta_llm = llm.invoke(prompt).content
            return {
                "severidad": severidad,
                "causa_raiz": f"[{state['titulo_manual']}] {respuesta_llm}",
                "procedimiento_recomendado": state["contexto_rag"].split("PROCEDIMIENTO:")[-1].strip(),
            }
        except Exception as e:
            logging.warning(f"Usando motor determinista RAG (detalle LLM: {e})")

    causa = (
        f"Correlación multivariable detectada por ONNX (Score {score}): "
        f"Vibración severa ({vib} mm/s > límite 7.1 mm/s ISO 10816), sobrecorriente ({corr}A) "
        f"y elevación térmica ({temp}°C). Referencia RAG: {state['titulo_manual']}. "
        f"{state['contexto_rag'].split('PROCEDIMIENTO:')[0].strip()}"
    )
    procedimiento = state["contexto_rag"].split("PROCEDIMIENTO:")[-1].strip()

    return {
        "severidad": severidad,
        "causa_raiz": causa,
        "procedimiento_recomendado": procedimiento,
    }


# Compilamos el Grafo de LangGraph
workflow = StateGraph(EstadoAgente)
workflow.add_node("recuperador_rag", nodo_recuperador_rag)
workflow.add_node("diagnosticador", nodo_diagnosticador_ingenieria)
workflow.set_entry_point("recuperador_rag")
workflow.add_edge("recuperador_rag", "diagnosticador")
workflow.add_edge("diagnosticador", END)

grafo_copilot = workflow.compile()