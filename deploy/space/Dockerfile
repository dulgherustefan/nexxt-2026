# VersoML on a Hugging Face Space (Docker SDK): both zones in one container, the console on port 7860.
# The Bedrock key is never in the image: set AWS_BEARER_TOKEN_BEDROCK as a secret in the Space settings.
FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_NO_CACHE=1 \
    VERSOML_HOST=0.0.0.0 VERSOML_CLIENT_PORT=7860 VERSOML_AML_PORT=8001 \
    VERSOML_CLIENT_URL=http://127.0.0.1:7860 VERSOML_AML_URL=http://127.0.0.1:8001
# LightGBM needs the OpenMP runtime
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv && useradd -m -u 1000 user && mkdir -p /app && chown user:user /app
WORKDIR /app
COPY --chown=user pyproject.toml uv.lock README.md ./
COPY --chown=user versoml/ versoml/
COPY --chown=user --from=ui /ui/dist frontend/dist
USER user
RUN uv sync --no-dev --frozen
# Synthetic data, models and the fast evaluation are built into the image, so a cold start takes seconds
RUN uv run --no-dev versoml setup --no-ui
EXPOSE 7860
CMD ["uv", "run", "--no-dev", "versoml", "up"]
