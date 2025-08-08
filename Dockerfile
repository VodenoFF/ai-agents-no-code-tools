FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    fonts-ebgaramond \
    ffmpeg \
    libsndfile1 \
    fonts-dejavu \
    build-essential \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY assets/HappyBoy.ttf /usr/share/fonts/truetype/HappyBoy.ttf
RUN fc-cache -f -v


COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY assets/overlay /app/assets/overlay
COPY api_server /app/api_server
COPY utils /app/utils
COPY video /app/video
COPY server.py /app/server.py

ENV PYTHONUNBUFFERED=1

CMD ["fastapi", "run", "server.py", "--host", "0.0.0.0", "--port", "8000"]
