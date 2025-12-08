# Use lightweight Python base image instead of Azure Functions
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    TRANSFORMERS_CACHE=/tmp/.cache/huggingface \
    HF_HOME=/tmp/.cache/huggingface \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies for pyodbc (ODBC SQL Server driver)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    unixodbc-dev \
    && curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create working directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip cache purge

# Copy application code
COPY . .

# Model will be downloaded on first run and cached in /tmp
# This keeps the image small and allows for 0-replica scaling

# Run the custom queue processor
CMD ["python", "-u", "queue_processor.py"]
