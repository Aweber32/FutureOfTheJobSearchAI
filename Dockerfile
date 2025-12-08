# Use the official Azure Functions Python base image
FROM mcr.microsoft.com/azure-functions/python:4-python3.11

# Set environment variables for Container Apps
ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    PYTHONUNBUFFERED=1 \
    TRANSFORMERS_CACHE=/tmp/.cache/huggingface \
    HF_HOME=/tmp/.cache/huggingface

# Copy requirements first for better layer caching
COPY requirements.txt /home/site/wwwroot/

# Install dependencies
# Use CPU-only PyTorch to reduce image size significantly
RUN cd /home/site/wwwroot && \
    pip install --no-cache-dir -r requirements.txt && \
    pip cache purge

# Copy application code
COPY . /home/site/wwwroot

# Set working directory
WORKDIR /home/site/wwwroot

# Model will be downloaded on first run and cached in /tmp
# This keeps the image small and allows for 0-replica scaling

# Don't set CMD here - Container Apps needs to set it explicitly
# The proper command for Container Apps with Azure Functions Python is:
# /opt/startup/start_nonappservice.sh
# This script properly initializes the Python worker
