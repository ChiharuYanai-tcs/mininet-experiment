# Mininet on Docker for GitHub Codespaces

GitHub CodespacesでDockerとMininetを使ったネットワーク実験環境。

## 概要

仮想的なネットワークトポロジーを作成し、遅延・帯域幅・パケットロスなどを制御してネットワークの挙動を実験できます。

## セットアップ

### 1. Dockerイメージのビルド

```bash
docker build -t mininet-ubuntu .
```

### 2. コンテナの起動

```bash
docker run -it --privileged -v $(pwd):/root/workspace --name mininet-container mininet-ubuntu
```

### 3. コンテナ内での準備

```bash
service openvswitch-switch start
apt-get update && apt-get install -y iperf
cd workspace
```

## 使い方

### Pythonスクリプトで実験

```bash
# 基本的なネットワーク実験
python3 simple_test_linuxbridge.py

# パラメータ変更のデモ
python3 network_params_demo.py
```

### 対話的CLI

スクリプト実行後、`exit`で終了するまで以下のコマンドが使えます：

```bash
h1 ping h2         # ping実行
nodes              # ノード一覧
net                # ネットワーク構成
link h1 h2 down    # リンクダウン
link h1 h2 up      # リンクアップ
```

## ネットワークパラメータ

### リンク作成時

```python
from mininet.link import TCLink

net = Mininet(link=TCLink)
net.addLink(h1, h2,
    bw=10,              # 帯域幅（Mbps）
    delay='10ms',       # 遅延
    loss=5,             # パケットロス率（%）
    max_queue_size=100, # キューサイズ
    jitter='2ms'        # ジッター
)
```

## ファイル構成

```
.
├── Dockerfile
├── simple_test.py    # 基本実験
└── README.md
```

## 実験例

```python
# 低遅延・高速
net.addLink(h1, h2, bw=100, delay='1ms', loss=0)

# 高遅延・低速・不安定
net.addLink(h1, h3, bw=1, delay='50ms', loss=5)
```

## コンテナの再利用

```bash
# 既存コンテナの削除と再作成
docker rm -f mininet-container
docker run -it --privileged -v $(pwd):/root/workspace --name mininet-container mininet-ubuntu

# または既存コンテナの再起動
docker start mininet-container
docker exec -it mininet-container /bin/bash
```

## 補足
- GitHub Codespaces 環境では、Open vSwitchが動作しません。

## 参考

- [Mininet公式サイト](http://mininet.org/)
- [Mininet Python API](http://mininet.org/api/annotated.html)