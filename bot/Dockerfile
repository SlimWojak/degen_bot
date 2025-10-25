FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy bot code
COPY bot /app/bot

# Copy utils package
COPY utils /app/utils

# Copy shared common package
COPY common /app/common

# Copy main entry point
COPY main.py /app/main.py

# Set Python path
ENV PYTHONPATH=/app

# Create data directory
RUN mkdir -p /app/data

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the bot
CMD ["python", "main.py"]
