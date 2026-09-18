FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HAPPY_DB=/data/happy.sqlite3
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 happy \
    && mkdir /data && chown happy:happy /data
COPY --chown=happy:happy happy ./happy
COPY --chown=happy:happy scripts/download_model.py ./scripts/download_model.py
USER happy
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"
CMD ["python", "-m", "happy", "--host", "0.0.0.0", "--port", "8000"]
