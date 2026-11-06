FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONSULT_DATA_DIR=/data \
    PORT=8000

WORKDIR /app
RUN useradd --system --uid 10001 --home /app consult \
    && mkdir -p /data \
    && chown -R consult:consult /data

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY src ./src
COPY static ./static

USER consult
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"

CMD ["python", "app.py"]
