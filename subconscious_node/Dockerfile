# Pathos Subconscious Node - Standalone Container
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY *.py ./
COPY config.json ./
COPY *.jsonl ./

# Create directories for data persistence
RUN mkdir -p /app/data /app/logs

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Default command runs the full system
CMD ["python3", "-c", "import subprocess; subprocess.Popen(['python3', 'thinker.py']); exec(open('api.py').read())"]
