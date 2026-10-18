FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY backend ./backend
COPY mcp_servers ./mcp_servers
COPY security ./security
RUN pip install --no-cache-dir ".[cloud]"
EXPOSE 8080
CMD ["uvicorn", "mcp_servers.data.server:app", "--host", "0.0.0.0", "--port", "8080"]
