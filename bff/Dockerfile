FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

COPY bff/requirements.txt ./bff/requirements.txt
RUN pip install --no-cache-dir -r bff/requirements.txt

COPY bff ./bff
# D-99 N3: also when built from a context without .gcloudignore (a local docker build)
RUN rm -f bff/.env bff/.env.*
COPY contract ./contract
# P-60: the demonstration apartments run on the engine's SimulatedConnector (its tests stay out, see .gcloudignore)
COPY engine ./engine

RUN useradd --create-home --uid 10001 app && chown -R app:app /srv
USER app

# Cloud Run injects PORT; everything else comes from env vars / Secret Manager (see cloudrun.yaml).
ENV PORT=8080 APP_ENV=prod AUTH_MODE=firebase INSTANCE_MODE=real REPOSITORY=firestore
EXPOSE 8080
CMD ["sh", "-c", "uvicorn bff.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
