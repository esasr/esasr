FROM python:3.12-slim

ARG INSTALL_RERANKER=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/esasr-api

WORKDIR /app

COPY esasr-api/requirements.txt /tmp/requirements.txt
COPY esasr-api/requirements-reranker.txt /tmp/requirements-reranker.txt

RUN pip install --upgrade pip \
    && pip install -r /tmp/requirements.txt \
    && if [ "$INSTALL_RERANKER" = "true" ]; then \
         pip install -r /tmp/requirements-reranker.txt; \
       fi

# The image contains only the non-secret template. Runtime secrets and service
# addresses are injected through Compose environment variables.
COPY config_example.yaml /app/config.yaml
COPY esasr-api /app/esasr-api

WORKDIR /app/esasr-api

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
