FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY backend/requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy backend code
COPY backend /app/backend

# Copy shared common package
COPY common /app/common

# Copy bot package for trade_test endpoint
COPY bot /app/bot

# Set Python path
ENV PYTHONPATH=/app

# Create data directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 8000

# Run FastAPI backend
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
