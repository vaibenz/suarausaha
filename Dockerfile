# Stage 1: build the accessible web app
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: API that also serves the built app
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 SUARAUSAHA_DB=/data/suarausaha.db SUARAUSAHA_WEB_DIST=/app/frontend/dist
WORKDIR /app
COPY backend/ ./backend/
RUN pip install --no-cache-dir ./backend
COPY --from=web /web/dist ./frontend/dist
RUN useradd --create-home appuser && mkdir /data && chown appuser /data
USER appuser
WORKDIR /app/backend
CMD ["sh", "-c", "uvicorn suarausaha.api:app --host 0.0.0.0 --port ${PORT}"]
