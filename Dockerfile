FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    mininet \
    net-tools \
    iputils-ping \
    iproute2 \
    openvswitch-switch \
    openvswitch-common \
    tcpdump \
    vim \
    python3 \
    python3-pip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Mininetに必要なPythonパッケージをインストール
# matplotlib は結果を可視化する際に便利です
RUN pip3 install matplotlib pandas

RUN mkdir -p /var/run/openvswitch

WORKDIR /root

CMD ["/bin/bash"]