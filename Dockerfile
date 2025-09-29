FROM ubuntu:latest

LABEL maintainer="johngao"
ARG project=weibo_tg_bot
WORKDIR /app

COPY . /app/${project}

RUN apt-get update && \
    apt-get install -y python3 python3-pip build-essential \
                       libssl-dev libffi-dev libgl1 libglib2.0-0 && \
    pip install -r /app/${project}/requirements.txt --break-system-packages && \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONPATH="/app/${project}"