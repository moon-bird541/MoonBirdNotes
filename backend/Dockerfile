FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install \
    --index-url https://mirrors.aliyun.com/pypi/simple/ \
    --no-cache-dir \
    -r requirements.txt

COPY backend/ ./
COPY .tmp/bge-m3-tokenizer-clean.json ./rag/assets/bge-m3-tokenizer.json
RUN mkdir -p media staticfiles \
    && useradd --create-home --uid 1000 moonbird \
    && chown -R moonbird:moonbird /app

USER moonbird

ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
CMD ["web"]
