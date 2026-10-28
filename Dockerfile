# VersoML: o singură imagine, două procese (zona client și zona AML) pornite separat de docker-compose.
FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock* README.md ./
COPY versoml/ versoml/
RUN uv sync --no-dev --frozen || uv sync --no-dev
COPY --from=ui /ui/dist frontend/dist
# Cheia Bedrock NU intră în imagine: se dă la rulare prin variabila AWS_BEARER_TOKEN_BEDROCK.
EXPOSE 8000 8001
CMD ["uv", "run", "--no-dev", "versoml", "up"]
