FROM python:3.12-slim

WORKDIR /lumen

# System dependencies required by PyMuPDF (PDF rendering) and other parsers.
# libgl1 + libglib2.0-0 are needed by the MuPDF rendering engine.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer-cached on rebuilds unless
# requirements.txt changes).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app/ ./app/

# Pre-create data directories. These will be overridden by the bind mount
# at runtime, but having them ensures the app starts cleanly without Docker.
RUN mkdir -p /data/uploads /data/chroma

EXPOSE 8080

# Run as the app package module so Python resolves imports correctly.
CMD ["python", "-m", "app.main"]
