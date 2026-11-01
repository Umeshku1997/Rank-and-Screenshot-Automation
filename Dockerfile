FROM node:18-bullseye-slim

# Install system dependencies & Python
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    wget \
    gnupg \
    curl \
    ca-certificates \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set Environment variables for Headless Chromium
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8

WORKDIR /app

# Copy dependency files
COPY package*.json ./
RUN npm install

# Copy Python requirements if exists
COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt || true

# Copy full application code
COPY . .

EXPOSE 10000

CMD ["node", "server.js"]
