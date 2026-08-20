# 1. El Sistema Operativo: Partimos de un Linux minimalista con Python 3.10 preinstalado
FROM python:3.10-slim

# 2. La Carpeta: Le decimos a Docker que trabaje dentro de una carpeta llamada /app
WORKDIR /app

# 3. Las Dependencias: Copiamos la lista de compras y ordenamos instalarla
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. El Código: Copiamos todo tu código (api.py, database.py, etc.) dentro del contenedor
COPY . .

# El directorio se inicializa con permisos del usuario de ejecución para el volumen de SQLite.
RUN useradd --create-home appuser && mkdir /data && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

# 5. El Encendido: El comando que debe ejecutar la máquina cuando despierte
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
