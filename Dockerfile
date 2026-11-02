FROM node:18-bookworm-slim

RUN apt-get update && apt-get install -y \
    python3 python3-pip ca-certificates curl \
    chromium chromium-driver fonts-noto fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app

COPY package*.json ./
RUN npm install --omit=dev

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

COPY . .

EXPOSE 10000
CMD ["node", "server.js"]
