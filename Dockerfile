FROM node:18-bookworm-slim

# Install system dependencies, Chromium, Python & Virtual Display (Xvfb)
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    xvfb \
    wget \
    gnupg \
    curl \
    ca-certificates \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set Environment variables for Headless Chromium and Virtual Display
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV DISPLAY=:99

WORKDIR /app

# Copy dependency files and install Node packages
COPY package*.json ./
RUN npm install

# Copy Python requirements if exists
COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages || true

# Copy full application code
COPY . .

EXPOSE 10000

# Start Xvfb virtual display before starting the Node server
CMD ["sh", "-c", "Xvfb :99 -screen 0 1920x1080x24 & node server.js"]
