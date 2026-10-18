# syntax=docker/dockerfile:1
FROM python:3.13-slim

WORKDIR /app

RUN useradd --no-create-home --shell /bin/false appuser \
    && mkdir -p /data \
    && chown appuser:appuser /data

COPY url_shortener/ ./url_shortener/

USER appuser

EXPOSE 8000

ENV DB_PATH=/data/links.db

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

CMD ["python3", "url_shortener/app.py"]
