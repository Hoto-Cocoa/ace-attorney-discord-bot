FROM python:3.10-slim-bullseye
WORKDIR /app

COPY requirements.txt .
RUN apt-get update && \
  apt install ffmpeg libsm6 libxext6 pkg-config libicu-dev build-essential tk -y && \
  pip install -r requirements.txt && \
  python3 -m pip install pyICU pycld2 morfessor polyglot && \
  python -m spacy download en_core_web_sm && \
  apt purge build-essential -y && \
  apt clean && \
  rm -rf ~/.cache/pip/*

COPY . .

CMD python ./main.py

