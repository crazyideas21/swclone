#!/usr/bin/python

"""
Starts a pod in a k=6 fat tree: 

Pod switches:

0 1 2
3 4 5

Hosts connected to pod:

30 31 32 40 41 42 50 51 52

"""

from mininet.net import Mininet
from mininet.cli import CLI
from mininet.log import lg
from mininet.node import Node, OVSKernelSwitch, RemoteController
from mininet.topolib import TreeTopo
from mininet.util import createLink

from mininet.topo import Topo
from mininet.topo import Node as TopoNode

import sys


class FatTreeTopo( Topo ):

    def __init__( self, enable_all = True ):
        "Create custom topo."

        # Add default members to class.
        super( FatTreeTopo, self ).__init__()

        # Add hosts.
        for i in [30, 40, 50]:
            for j in range(3):
                self.add_node(i + j, TopoNode(is_switch=False))

        # Add pod switches.
        for i in range(6):
            self.add_node(i, TopoNode(is_switch=True))

        # Connect pod switches.
        for upper_sw in [0, 1, 2]:
            for lower_sw in [3, 4, 5]:
                self.add_edge(upper_sw, lower_sw)

        # Connect hosts to pod.
        for lower_sw in [3, 4, 5]:
            for i in range(0, 3):
                host = lower_sw * 10 + i
                self.add_edge(lower_sw, host)

        # Consider all switches and hosts 'on'
        self.enable_all()




class LinearTopo( Topo ):

    def __init__( self, enable_all = True ):

        super( LinearTopo, self ).__init__()

        self.add_node(30, TopoNode(is_switch=False))
        self.add_node(31, TopoNode(is_switch=False))        
        self.add_node(1,  TopoNode(is_switch=True))

        self.add_edge(30, 1)
        self.add_edge(31, 1)

        self.enable_all()






def FatTreeNet( **kwargs ):
    topo = FatTreeTopo()
    return Mininet( topo, **kwargs )


def LinearNet( **kwargs ):
    topo = LinearTopo()
    return Mininet(topo, **kwargs)


def main():

    lg.setLogLevel( 'info')
    c = lambda name: RemoteController(name, defaultIP='132.239.17.35')

    if 'fattree' in sys.argv:
        net = FatTreeNet(switch=OVSKernelSwitch, controller=c)
    elif 'linear' in sys.argv:
        net = LinearNet(switch=OVSKernelSwitch, controller=c)
    else:
        print >> sys.stderr, 'Specify either "fattree" or "linear" as the sole argument.'
        return

    net.start()
    CLI(net)
    net.stop()


if __name__ == '__main__':
    main()
