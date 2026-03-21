# 建议使用具体版本号（如 22.04），而非 latest，以保证构建的可重复性
FROM ubuntu:latest

LABEL maintainer="johngao"
ARG project=avelen
ENV PYTHONPATH="/app/${project}"
WORKDIR /app/${project}

COPY requirements.txt .
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
                       python3 python3-pip \
                       build-essential libssl-dev libffi-dev \
                       libgl1 libglib2.0-0 && \
    pip install --no-cache-dir -r requirements.txt --break-system-packages && \
    apt-get purge -y --auto-remove build-essential libssl-dev libffi-dev && \
    rm -rf /var/lib/apt/lists/*

COPY . /app/${project}
