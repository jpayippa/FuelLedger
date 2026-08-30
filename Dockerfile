FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py db.py ocr.py crop.py export.py uploads.py image_quality.py .
COPY templates/ templates/
COPY static/ static/

EXPOSE 80
CMD ["python", "app.py"]
