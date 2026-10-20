# The DOMHOUSE engine, one container per apartment (P-60 step 2). Build from the repository's root:
#   docker build -f engine/Dockerfile -t domhouse-engine .
# Configuration only from the environment (engine/config.py): APARTMENT_ID, API_KEY, CONNECTOR are required.
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

COPY engine/requirements.txt ./engine/requirements.txt
RUN pip install --no-cache-dir -r engine/requirements.txt

COPY engine ./engine
# the tests and local settings stay out of the image (engine/Dockerfile.dockerignore keeps out the rest of the repo)
RUN find engine -type d \( -name tests -o -name __pycache__ \) -prune -exec rm -rf {} + \
    && rm -f engine/.env engine/.env.*

RUN useradd --create-home --uid 10001 engine && mkdir -p /data && chown engine:engine /data
USER engine

ENV HOST=0.0.0.0 PORT=8100
EXPOSE 8100
CMD ["python", "-m", "engine"]
