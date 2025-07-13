# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/
COPY README.md ./

# Install the package in production mode
RUN pip install --no-cache-dir -e .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV PORT=8080

# Expose port for HTTP server
EXPOSE $PORT

# The command will be provided by smithery.yaml
# Default command for local testing
CMD ["sh", "-c", "fastmcp -t streamable-http --host 0.0.0.0 --port $PORT pragweb/mcp_server.py"]