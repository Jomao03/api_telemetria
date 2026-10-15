import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from skl2onnx import to_onnx

RUTA_MODELO_ONNX = "modelo_anomalias_iiot.onnx"

def entrenar_y_exportar():
    print("1. Generando dataset sintético de operación nominal de planta...")
    rng = np.random.default_rng(42)
    n_muestras = 5000

    # Régimen normal: V ~24V (o 12V), I ~5.2A, Temp ~48°C, Vibración ~1.8 mm/s
    voltaje = rng.normal(loc=24.0, scale=0.4, size=n_muestras)
    corriente = rng.normal(loc=5.2, scale=0.3, size=n_muestras)
    temperatura = rng.normal(loc=48.0, scale=1.5, size=n_muestras)
    vibracion = rng.normal(loc=1.8, scale=0.2, size=n_muestras)

    X_train = np.column_stack([voltaje, corriente, temperatura, vibracion]).astype(np.float32)

    print("2. Entrenando Pipeline (StandardScaler + IsolationForest)...")
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("iforest", IsolationForest(n_estimators=100, contamination=0.02, random_state=42))
    ])
    pipeline.fit(X_train)

    print("3. Convirtiendo y optimizando el modelo a formato ONNX...")
    # Definimos un ejemplo de entrada (1 fila, 4 columnas float32)
    ejemplo_entrada = X_train[:1]
    modelo_onnx = to_onnx(
        pipeline,
        ejemplo_entrada,
        target_opset={"": 15, "ai.onnx.ml": 3}
    )

    with open(RUTA_MODELO_ONNX, "wb") as f:
        f.write(modelo_onnx.SerializeToString())

    print(f" Modelo exportado exitosamente en: {RUTA_MODELO_ONNX}")

if __name__ == "__main__":
    entrenar_y_exportar()