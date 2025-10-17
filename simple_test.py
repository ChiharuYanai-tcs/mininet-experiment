#!/usr/bin/python3
"""
Mininetを使った簡単なネットワーク実験（Linuxブリッジ版）
"""

from mininet.net import Mininet
from mininet.node import Host
from mininet.link import Link
from mininet.cli import CLI
from mininet.log import setLogLevel, info

def simple_network_test():    
    setLogLevel('info')
    
    # コントローラーもスイッチも使わない、最もシンプルな構成
    info('*** ネットワークの作成を開始します\n')
    net = Mininet()
    
    # 2つのホストを作成
    info('*** ホストを追加\n')
    h1 = net.addHost('h1', ip='10.0.0.1/24')
    h2 = net.addHost('h2', ip='10.0.0.2/24')
    
    # ホストを直接接続（スイッチなし）
    info('*** リンクを作成（ホスト間を直接接続）\n')
    net.addLink(h1, h2)
    
    # ネットワークを起動
    info('*** ネットワークを起動\n')
    net.start()
    
    # 実験を開始
    info('\n*** 接続性テスト（ping）を実行\n')
    result = net.ping([h1, h2], timeout='1')
    info(f'パケットロス率: {result}%\n')
    
    if result == 0:
        info('Successful : 接続成功 \n')
        
        info('\n*** RTT（往復遅延時間）を詳細に測定\n')
        h1_output = h1.cmd('ping -c 10 10.0.0.2')
        info(h1_output)
        
        info('\n*** 帯域幅テスト（iperfを使用）\n')
        # iperfがインストールされているか確認
        iperf_check = h1.cmd('which iperf')
        if iperf_check.strip():
            h2.cmd('iperf -s &')
            info('iperfサーバーを起動中...\n')
            net.waitConnected()
            
            info('帯域幅測定を開始...\n')
            h1_iperf = h1.cmd('iperf -c 10.0.0.2 -t 10')
            info(h1_iperf)
            
            h2.cmd('kill %iperf')
        else:
            info('iperfがインストールされていません。帯域幅テストをスキップします。\n')
            info('インストールする場合: apt-get install -y iperf\n')
    else:
        info('Error : 接続に失敗しました\n')
    
    # 対話的なCLIを起動
    info('\n*** 対話的CLIを起動（exitで終了）\n')
    CLI(net)
    
    # ネットワークを停止
    info('*** ネットワークを停止\n')
    net.stop()

if __name__ == '__main__':
    simple_network_test()