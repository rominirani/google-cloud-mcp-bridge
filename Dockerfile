# Production Dockerfile for Google Cloud MCP Agent Bridge
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Create a non-privileged application user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY agent.py ./
COPY gcp_agent/ ./gcp_agent/
COPY skills/ ./skills/

# Set ownership to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Expose HTTP port for Cloud Run
EXPOSE 8080

# Launch FastAPI using Uvicorn
CMD ["uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8080"]
