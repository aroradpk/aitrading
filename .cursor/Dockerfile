FROM ubuntu:24.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      python3 \
      python3-pip \
      python3.12-venv \
    && rm -rf /var/lib/apt/lists/*

USER ubuntu
