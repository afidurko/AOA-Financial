FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md requirements.txt requirements-dev.txt ./
COPY src/ src/
COPY profiles/ profiles/

RUN pip install --no-cache-dir -e ".[web]"

RUN useradd --create-home --shell /bin/bash aoa
RUN mkdir -p /app/data && chown -R aoa:aoa /app
USER aoa

ENV AOA_DATA_DIR=/app/data
ENV AOA_PROFILE=paper-dry
ENV AOA_ENV=paper-dry

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["aoa", "serve"]
