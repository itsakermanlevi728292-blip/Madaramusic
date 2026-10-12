FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

# ffmpeg: audio/video for voice chats and /song; gcc: builds tgcrypto (faster Telegram encryption);
# fonts: the now-playing card (Latin, Hindi/Devanagari, CJK-safe fallbacks)
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg gcc libc6-dev fonts-dejavu-core fonts-noto-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY config.py session.py start ./
COPY strings ./strings
COPY SHUBHMUSIC ./SHUBHMUSIC

# The bot keeps its small database and Telegram session in DATA_DIR.
# On Railway attach a volume at /app/data so it survives redeploys.
ENV DATA_DIR=/app/data
RUN mkdir -p /app/data

CMD ["bash", "start"]
