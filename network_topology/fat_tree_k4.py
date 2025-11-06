from mininet.net import Mininet
from mininet.node import Host, Node
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import Link, Intf
import time

class LinuxBridge(Node):
    """
    Linuxブリッジを使った簡易スイッチの実装
    カーネルモジュールの制限を回避するために、
    標準的なLinuxのブリッジ機能を使用
    """
    def __init__(self, name, **params):
        super(LinuxBridge, self).__init__(name, **params)
        self.bridge_name = name
    
    def start(self, controllers=None):
        """ブリッジの初期化と起動"""
        # ブリッジデバイスを作成
        self.cmd(f'ip link add name {self.bridge_name}-br type bridge')
        self.cmd(f'ip link set dev {self.bridge_name}-br up')
        
        # 各インターフェースをブリッジに追加
        for intf in self.intfList():
            if intf.name != 'lo':
                self.cmd(f'ip link set dev {intf.name} master {self.bridge_name}-br')
                self.cmd(f'ip link set dev {intf.name} up')
        
        # STP（Spanning Tree Protocol）を無効化して高速化
        self.cmd(f'echo 0 > /sys/class/net/{self.bridge_name}-br/bridge/stp_state')
        
        # 転送遅延を最小化
        self.cmd(f'echo 0 > /sys/class/net/{self.bridge_name}-br/bridge/forward_delay')
    
    def stop(self, deleteIntfs=True):
        """ブリッジの停止とクリーンアップ"""
        self.cmd(f'ip link delete {self.bridge_name}-br')
        super(LinuxBridge, self).stop(deleteIntfs)

def create_simplified_fattree(k=4):
    """
    簡略化されたFat-treeトポロジーの作成
    GitHub Codespace環境向けに最適化
    """
    # カスタムスイッチクラスを使用してネットワークを作成
    net = Mininet(switch=LinuxBridge, controller=None)
    
    info('=== Fat-tree トポロジー (k=4) を構築中 ===\n')
    info('  - コアスイッチ: 4個\n')
    info('  - 集約スイッチ: 8個 (各Pod 2個)\n')  
    info('  - エッジスイッチ: 8個 (各Pod 2個)\n')
    info('  - ホスト: 16個 (各エッジスイッチ 2個)\n\n')
    
    # コアスイッチの作成（簡略化のため数を削減）
    core_switches = []
    num_core = (k // 2) ** 2
    for i in range(num_core):
        core_sw = net.addSwitch(f'c{i}')
        core_switches.append(core_sw)
    
    all_hosts = []
    
    # 各Podの構築
    for pod in range(k):
        # 集約層スイッチ
        pod_agg = []
        for i in range(k // 2):
            agg_sw = net.addSwitch(f'a{pod}_{i}')
            pod_agg.append(agg_sw)
        
        # エッジ層スイッチとホスト
        pod_edge = []
        for i in range(k // 2):
            edge_sw = net.addSwitch(f'e{pod}_{i}')
            pod_edge.append(edge_sw)
            
            # 各エッジスイッチにホストを接続
            for j in range(k // 2):
                host_name = f'h{pod}{i}{j}'
                # IPアドレスを明示的に設定
                ip_addr = f'10.{pod}.{i}.{j+1}/24'
                host = net.addHost(host_name, ip=ip_addr)
                all_hosts.append(host)
                net.addLink(edge_sw, host)
        
        # エッジ層と集約層の接続
        for edge_sw in pod_edge:
            for agg_sw in pod_agg:
                net.addLink(edge_sw, agg_sw)
        
        # 集約層とコア層の接続
        for i, agg_sw in enumerate(pod_agg):
            for j in range(k // 2):
                core_idx = i * (k // 2) + j
                net.addLink(agg_sw, core_switches[core_idx])
    
    return net, all_hosts

def setup_routing(net, hosts):
    """
    静的ルーティングの設定
    異なるサブネット間の通信を可能にする
    """
    info('\n=== ルーティングを設定中 ===\n')
    
    # 各ホストにデフォルトゲートウェイを設定
    for host in hosts:
        host_name = host.name
        pod = int(host_name[1])
        edge = int(host_name[2])
        
        # デフォルトゲートウェイの設定（簡略化）
        gateway = f'10.{pod}.{edge}.254'
        host.cmd(f'route add default gw {gateway}')
        
        # ARPテーブルのタイムアウトを延長
        host.cmd('echo 300 > /proc/sys/net/ipv4/neigh/default/gc_stale_time')

def run_throughput_experiment(net):
    """
    h000からh111への10秒間のスループット測定実験
    環境制限を考慮した設定で実行
    """
    info('\n' + '='*60 + '\n')
    info('  スループット測定実験を開始\n')
    info('='*60 + '\n')
    
    h000 = net.get('h000')
    h111 = net.get('h111')
    
    info(f'  送信元: h000 (IP: {h000.IP()}) → 送信先: h111 (IP: {h111.IP()})\n')
    info('  測定時間: 10秒\n')
    info('  測定間隔: 1秒\n\n')
    
    # 接続性の確認
    info('  接続性を確認中...\n')
    ping_result = h000.cmd(f'ping -c 1 {h111.IP()}')
    if '1 received' not in ping_result:
        info('  警告: ホスト間の接続が確立できません\n')
        info('  ネットワークの初期化を待機中...\n')
        time.sleep(3)
    
    # iperfサーバーを起動
    info('  h111でiperfサーバーを起動中...\n')
    h111.cmd('iperf -s > /tmp/iperf_server.log 2>&1 &')
    time.sleep(2)
    
    # iperfクライアントを実行
    info('  h000からトラフィックを送信中...\n\n')
    result = h000.cmd(f'iperf -c {h111.IP()} -t 10 -i 1')
    
    info('='*60 + '\n')
    info('  測定結果:\n')
    info('='*60 + '\n')
    info(result)
    
    # サーバープロセスの停止
    h111.cmd('pkill -9 iperf')

def main():
    setLogLevel('info')
    
    info('\n=== Mininet Fat-tree実験環境 ===\n')
    info('GitHub Codespace向けに最適化された設定\n\n')
    
    # ネットワークの作成
    net, hosts = create_simplified_fattree(k=4)
    
    info('\n=== ネットワークを起動中 ===\n')
    net.start()
    
    # ルーティングの設定
    setup_routing(net, hosts)
    
    # ネットワークの安定化を待つ
    info('\nネットワークの初期化を待機中...\n')
    time.sleep(3)
    
    # スループット測定実験
    run_throughput_experiment(net)
    
    # CLI起動
    info('\n=== CLI を起動 ===\n')
    info('  使用可能なコマンド:\n')
    info('    - nodes: ノード一覧の表示\n')
    info('    - net: ネットワーク情報の表示\n')
    info('    - h000 ping -c 3 h111: 特定ホスト間のping\n')
    info('    - h000 iperf -s &: iperfサーバーの起動\n')
    info('    - h111 iperf -c 10.0.0.1: iperfクライアントの実行\n')
    info('    - exit: 終了\n\n')
    
    CLI(net)
    
    info('\n=== ネットワークを停止中 ===\n')
    net.stop()
    info('\n=== 実験終了 ===\n')

if __name__ == '__main__':
    main()