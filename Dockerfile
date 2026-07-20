FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install EIF
COPY pyproject.toml ./
COPY eif/ ./eif/
COPY README.md ./

# Install EIF with MCP + HTTP server deps
RUN pip install --no-cache-dir ".[server]"

# Non-root user for security
RUN useradd -m -u 1000 eif
USER eif

ENV EIF_ENV=production

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["uvicorn", "eif.mcp_server.http_server:app", \
     "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
