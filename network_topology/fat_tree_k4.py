from mininet.net import Mininet
from mininet.node import UserSwith, Host
from mininet.cli import CLI
from mininet.log import setLogLevel, info

def create_fattree(k=4):
    # UserSwith でネットワークを作成
    net = Mininet(switch=UserSwith, waitConnected=True)

    return net