FROM python:3.11-slim

# Install system dependencies (ffmpeg is required for streaming audio to Discord)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the rest of the application code
COPY . .

# Install Python requirements
RUN pip install --no-cache-dir -r requirements.txt

# Render exposes the $PORT environment variable, which app.py reads automatically
CMD ["python", "app.py"]
