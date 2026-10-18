ARG OPENCLASS_RUNTIME_IMAGE=python:3.12-slim
FROM node:22-alpine AS frontend-build
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ${OPENCLASS_RUNTIME_IMAGE}
WORKDIR /app
COPY pyproject.toml ./
COPY backend ./backend
COPY mcp_service ./mcp_service
COPY mcp_servers ./mcp_servers
COPY security ./security
COPY mock_data ./mock_data
RUN pip install --no-cache-dir '.[cloud]'
COPY --from=frontend-build /web/dist ./static
ENV FRONTEND_DIST=/app/static
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
