FROM node:18-bookworm-slim

# Chromium + Python + virtual screen (Xvfb) + remote view (x11vnc/noVNC) + zip
RUN apt-get update && apt-get install -y \
    python3 python3-pip ca-certificates curl procps zip \
    xvfb x11vnc novnc websockify \
    chromium chromium-driver fonts-noto fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    DISPLAY=:99

WORKDIR /app

COPY package*.json ./
RUN npm install --omit=dev && npm install --omit=dev http-proxy@1.18.1

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

COPY . .

EXPOSE 10000

# 1) virtual screen  2) VNC server (sirf localhost)  3) websocket bridge  4) Node server
CMD ["sh", "-c", "rm -f /tmp/.X99-lock; Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp & sleep 2; x11vnc -display :99 -forever -shared -nopw -localhost -rfbport 5900 -noxdamage -quiet & websockify 127.0.0.1:6080 127.0.0.1:5900 & exec node server.js"]
