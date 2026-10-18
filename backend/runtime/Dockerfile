ARG OPENCLASS_RUNTIME_BASE=python:3.12-slim
FROM ${OPENCLASS_RUNTIME_BASE}
WORKDIR /app
COPY pyproject.toml ./
COPY backend ./backend
COPY mcp_servers ./mcp_servers
COPY security ./security
ARG OPENCLASS_REUSE_DEPENDENCIES=false
RUN if [ "$OPENCLASS_REUSE_DEPENDENCIES" = "true" ]; then \
      pip install --no-cache-dir --no-deps .; \
    else pip install --no-cache-dir ".[cloud]"; fi
ARG AGENT_GATEWAY_ROOT_CERTIFICATES
RUN if [ -n "$AGENT_GATEWAY_ROOT_CERTIFICATES" ]; then \
      printf '%s\n' "$AGENT_GATEWAY_ROOT_CERTIFICATES" | awk 'BEGIN {c=0} /BEGIN CERTIFICATE/ {c++} c > 0 {print > "/usr/local/share/ca-certificates/openclass-gateway-" c ".crt"}'; \
      update-ca-certificates; \
    fi
ENV GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    AGENT_GATEWAY_ROOT_CERT_302034098528=/etc/ssl/certs/ca-certificates.crt
ENV PORT=8080
CMD ["uvicorn", "backend.runtime.server:app", "--host", "0.0.0.0", "--port", "8080"]
