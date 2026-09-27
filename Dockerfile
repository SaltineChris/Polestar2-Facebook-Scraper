FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Create non-root user and give ownership of app and data dirs
RUN useradd -m -r appuser \
    && chown -R appuser:appuser /app \
    && mkdir -p /data && chown -R appuser:appuser /data

USER appuser

# Expose API port
EXPOSE 25000

ENV PORT=25000
CMD ["python", "api_server.py"]
