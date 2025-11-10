from mininet.net import Mininet
from mininet.node import Host, Node, Controller
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import Link, TCLink
import time

class LinuxRouter(Node):
    """IPフォワーディングを有効にしたLinuxルーター"""
    def config(self, **params):
        super(LinuxRouter, self).config(**params)
        # IP転送を有効化
        self.cmd('sysctl -w net.ipv4.ip_forward=1')
        # プロキシARPを有効化（重要）
        self.cmd('sysctl -w net.ipv4.conf.all.proxy_arp=1')
        
    def terminate(self):
        self.cmd('sysctl -w net.ipv4.ip_forward=0')
        super(LinuxRouter, self).terminate()

def create_simplified_fattree(k=4):
    """
    簡略化されたFat-tree: エッジ層を省略し、
    ホストを直接Pod内のルーターに接続
    """
    net = Mininet(controller=None, link=TCLink)
    
    info('=== 簡略化Fat-treeトポロジー構築 ===\n')
    info('  エッジ層を省略した実装\n\n')
    
    # コア層ルーター
    core_routers = []
    for i in range(2):  # 簡略化のため2個のコアルーター
        core = net.addHost(f'core{i}', cls=LinuxRouter)
        core_routers.append(core)
        info(f'  コアルーター core{i} を作成\n')
    
    all_hosts = []
    pod_routers = []
    
    # 各Pod（簡略化のため2個のPod）
    for pod in range(2):
        info(f'\n  === Pod {pod} 構築 ===\n')
        
        # Pod内のルーター（集約層とエッジ層の機能を統合）
        pod_router = net.addHost(f'pr{pod}', cls=LinuxRouter)
        pod_routers.append(pod_router)
        info(f'    Podルーター pr{pod} を作成\n')
        
        # このPod内のホスト（4個）
        for h in range(4):
            host_name = f'h{pod}{h}'
            # 10.pod.0.h+1 の形式でIPを割り当て
            ip = f'10.{pod}.0.{h+1}/24'
            host = net.addHost(host_name, ip=ip,
                             defaultRoute=f'via 10.{pod}.0.254')
            all_hosts.append(host)
            
            # ホストをPodルーターに直接接続
            link = net.addLink(host, pod_router)
            info(f'    ホスト {host_name} ({ip}) を接続\n')
        
        # PodルーターにこのPod用のIPアドレスを設定
        # （後で設定）
        
        # Podルーターとコアルーターの接続
        for core_idx, core in enumerate(core_routers):
            link = net.addLink(pod_router, core)
            info(f'    pr{pod} を core{core_idx} に接続\n')
    
    return net, all_hosts, pod_routers, core_routers

def configure_routers(net, pod_routers, core_routers):
    """
    ルーターのIPアドレスとルーティング設定
    """
    info('\n=== ルーターの設定 ===\n')
    
    # まず全てのルーターの全インターフェースをクリア
    info('\n  全ルーターのインターフェースをクリア中...\n')
    for router in pod_routers + core_routers:
        # 既存のルートを削除
        router.cmd('ip route flush table main')
        # 全てのIPアドレスをクリア
        for intf_name in router.intfNames():
            if intf_name != 'lo':  # loopbackは除外
                router.cmd(f'ip addr flush dev {intf_name}')
                router.cmd(f'ip link set {intf_name} down')
                router.cmd(f'ip link set {intf_name} up')
    
    # 各Podルーターの設定
    for pod_idx, pr in enumerate(pod_routers):
        info(f'\n  Podルーター pr{pod_idx} の設定:\n')
        
        # ホスト向けインターフェースの設定（ゲートウェイ）
        # 最初の4つのインターフェースはホスト向け
        for h in range(4):
            intf = pr.intfNames()[h]
            pr.cmd(f'ip addr flush dev {intf}')
            # 最初のインターフェースにのみゲートウェイIPを設定
            if h == 0:
                ip = f'10.{pod_idx}.0.254/24'
                pr.cmd(f'ip addr add {ip} dev {intf}')
                info(f'    ゲートウェイIP: 10.{pod_idx}.0.254 on {intf}\n')
            pr.cmd(f'ip link set {intf} up')
        
        # ブリッジを作成してホスト向けインターフェースを接続
        bridge_name = f'br{pod_idx}'
        pr.cmd(f'ip link add name {bridge_name} type bridge')
        pr.cmd(f'ip link set {bridge_name} up')
        pr.cmd(f'ip addr add 10.{pod_idx}.0.254/24 dev {bridge_name}')
        
        # 全てのホスト向けインターフェースをブリッジに接続
        for h in range(4):
            intf = pr.intfNames()[h]
            pr.cmd(f'ip addr flush dev {intf}')
            pr.cmd(f'ip link set {intf} master {bridge_name}')
            pr.cmd(f'ip link set {intf} up')
        
        info(f'    ブリッジ {bridge_name} を作成し、ホストインターフェースを接続\n')
        
        # コアルーター向けインターフェースの設定
        for core_idx in range(len(core_routers)):
            intf_idx = 4 + core_idx  # ホスト接続の後のインターフェース
            if intf_idx < len(pr.intfNames()):
                intf = pr.intfNames()[intf_idx]
                # バックボーンネットワーク: 192.168.x.x
                # 各リンクに異なるサブネットを割り当て
                subnet_id = pod_idx * len(core_routers) + core_idx
                ip = f'192.168.{subnet_id}.1/30'
                pr.cmd(f'ip addr add {ip} dev {intf}')
                pr.cmd(f'ip link set {intf} up')
                info(f'    コア接続IP: {ip} (subnet {subnet_id})\n')
        
        # 他のPodへの静的ルート
        for other_pod in range(2):
            if other_pod != pod_idx:
                # 他のPodへはコアルーター経由 (最初のコアルーターを使用)
                subnet_id = pod_idx * len(core_routers)  # pr-core0の接続
                next_hop = f'192.168.{subnet_id}.2'
                pr.cmd(f'ip route add 10.{other_pod}.0.0/24 via {next_hop}')
                info(f'    ルート追加: 10.{other_pod}.0.0/24 via {next_hop}\n')
    
    # コアルーターの設定
    for core_idx, core in enumerate(core_routers):
        info(f'\n  コアルーター core{core_idx} の設定:\n')
        
        for pod_idx in range(len(pod_routers)):
            intf = core.intfNames()[pod_idx]
            
            # 既存のIPアドレスを再度クリア（念のため）
            core.cmd(f'ip addr flush dev {intf}')
            
            # バックボーンネットワーク
            subnet_id = pod_idx * len(core_routers) + core_idx
            ip = f'192.168.{subnet_id}.2/30'
            core.cmd(f'ip addr add {ip} dev {intf}')
            core.cmd(f'ip link set {intf} up')
            info(f'    インターフェース {intf}: {ip} (subnet {subnet_id})\n')
            
            # 各Podネットワークへのルート
            next_hop = f'192.168.{subnet_id}.1'
            core.cmd(f'ip route add 10.{pod_idx}.0.0/24 via {next_hop}')
            info(f'    ルート追加: 10.{pod_idx}.0.0/24 via {next_hop}\n')

def verify_connectivity(net):
    """接続性の詳細な検証"""
    info('\n=== 接続性の検証 ===\n')
    
    h00 = net.get('h00')
    h13 = net.get('h13')  # Pod1のホスト
    
    info(f'\n  テスト1: h00 ({h00.IP()}) → ゲートウェイ (10.0.0.254)\n')
    result = h00.cmd('ping -c 2 10.0.0.254')
    if '2 received' in result or '2 packets received' in result:
        info('    ✓ ゲートウェイに到達可能\n')
    else:
        info('    ✗ ゲートウェイに到達不可\n')
        info(f'    デバッグ: {result}\n')
    
    info(f'\n  テスト2: h00 ({h00.IP()}) → h13 ({h13.IP()})\n')
    result = h00.cmd(f'ping -c 3 {h13.IP()}')
    if '3 received' in result or '3 packets received' in result:
        info('    ✓ Pod間通信成功！\n')
        return True
    else:
        info('    ✗ Pod間通信失敗\n')
        
        # デバッグ情報
        info('\n  === デバッグ情報 ===\n')
        info('  h00のルーティングテーブル:\n')
        info(h00.cmd('ip route'))
        info('\n  pr0のルーティングテーブル:\n')
        pr0 = net.get('pr0')
        info(pr0.cmd('ip route'))
        info('\n  core0のルーティングテーブル:\n')
        core0 = net.get('core0')
        info(core0.cmd('ip route'))
        info('\n  pr1のルーティングテーブル:\n')
        pr1 = net.get('pr1')
        info(pr1.cmd('ip route'))
        info('\n  ARPテーブル (h00):\n')
        info(h00.cmd('arp -n'))
        
        # traceroute で経路確認
        info('\n  経路確認 (traceroute):\n')
        info(h00.cmd(f'traceroute -n -m 5 {h13.IP()}'))
        
        # pr0からcore0へのping
        info('\n  pr0 → core0 (192.168.0.2) ping:\n')
        info(pr0.cmd('ping -c 2 192.168.0.2'))
        
        # core0からpr1へのping
        info('\n  core0 → pr1 (192.168.0.3) ping:\n')
        info(core0.cmd('ping -c 2 192.168.0.3'))
        
        # pingの詳細
        info('\n  詳細なping結果:\n')
        info(h00.cmd(f'ping -c 1 -v {h13.IP()}'))
        
        return False

def run_iperf_test(net):
    """iperf測定の実行"""
    if not verify_connectivity(net):
        info('\n接続性の問題があるため、iperf測定をスキップします\n')
        return
    
    info('\n=== iPerf スループット測定 ===\n')
    
    h00 = net.get('h00')
    h13 = net.get('h13')
    
    info(f'  送信元: h00 ({h00.IP()}) → 送信先: h13 ({h13.IP()})\n')
    
    # サーバー起動
    info('  iperfサーバーを起動...\n')
    h13.cmd('iperf -s &')
    time.sleep(2)
    
    # クライアント実行
    info('  測定中...\n\n')
    result = h00.cmd(f'iperf -c {h13.IP()} -t 10 -i 2')
    info(result)
    
    # サーバー停止
    h13.cmd('killall iperf')

def main():
    setLogLevel('info')
    
    info('\n=== Mininet簡略化Fat-tree (動作確認版) ===\n\n')
    
    # ネットワーク構築
    net, hosts, pod_routers, core_routers = create_simplified_fattree()
    
    info('\n=== ネットワーク起動 ===\n')
    net.start()
    
    # ルーター設定
    configure_routers(net, pod_routers, core_routers)
    
    # 安定化待機
    info('\n少し待機中...\n')
    time.sleep(2)
    
    # テスト実行
    run_iperf_test(net)
    
    # CLI
    info('\n=== CLI (exitで終了) ===\n')
    CLI(net)
    
    net.stop()
    info('\n=== 終了 ===\n')

if __name__ == '__main__':
    main()