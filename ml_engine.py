import os
import logging
import numpy as np
import onnxruntime as ort
from train_onnx_model import RUTA_MODELO_ONNX, entrenar_y_exportar

class DetectorAnomaliasONNX:
    def __init__(self, ruta_modelo: str = RUTA_MODELO_ONNX):
        if not os.path.exists(ruta_modelo):
            logging.info("Modelo ONNX no encontrado. Entrenando y exportando automáticamente...")
            entrenar_y_exportar()

        # Cargamos la sesión de ONNX Runtime optimizada para CPU
        self.sesion = ort.InferenceSession(ruta_modelo, providers=["CPUExecutionProvider"])
        self.nombre_entrada = self.sesion.get_inputs()[0].name
        logging.info(f"Motor ONNX Runtime inicializado ({ruta_modelo})")

    def evaluar_medicion(
        self, voltaje: float, corriente: float, temperatura_c: float, vibracion_mm_s: float
    ) -> tuple[bool, float]:
        """
        Ejecuta inferencia en <1ms.
        Retorna: (es_anomalia: bool, score_severidad: float)
        """
        vector = np.array([[voltaje, corriente, temperatura_c, vibracion_mm_s]], dtype=np.float32)
        salidas = self.sesion.run(None, {self.nombre_entrada: vector})

        # En IsolationForest ONNX: salidas[0] es el label (1 = normal, -1 = anomalía)
        # salidas[1] es el decision_function (valores negativos indican mayor anomalía)
        etiqueta = int(salidas[0].squeeze())
        puntaje_crudo = float(salidas[1].squeeze())

        es_anomalia = etiqueta == -1
        # Convertimos el puntaje en un índice de severidad positivo fácil de leer
        score_severidad = round(max(0.0, -puntaje_crudo * 100), 2) if es_anomalia else 0.0

        return es_anomalia, score_severidad

# Instancia singleton lista para usar en la API y en el Ingestor MQTT
detector_onnx = DetectorAnomaliasONNX()