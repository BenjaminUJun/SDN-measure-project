# conding=utf-8
import logging
import struct
import copy
import networkx as nx
from operator import attrgetter
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ipv4
from ryu.lib.packet import arp
from ryu.lib import hub

from ryu.topology import event, switches
from ryu.topology.api import get_switch, get_link

SLEEP_PERIOD = 5
IS_UPDATE = True


class Network_Aware(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _NAME = 'network_aware'

    def __init__(self, *args, **kwargs):
        super(Network_Aware, self).__init__(*args, **kwargs)
        self.name = "Network_Aware"
        self.topology_api_app = self

        # links_to_port:(src_dpid,dst_dpid)->(src_port,dst_port)
        self.link_to_port = {}
        # access_table:{(sw,port) :[host1_ip]}
        self.access_table = {}
        # switch_port_table:dpip->port_num
        self.switch_port_table = {}
        # access_port:dpid->port_num
        self.access_ports = {}
        # interior_ports: dpid->port_num
        self.interior_ports = {}

        self.graph = nx.DiGraph()
        self.pre_graph = nx.DiGraph()
        self.pre_access_table = {}
        self.pre_link_to_port = {}
        self.shortest_paths = None

        self.discover_thread = hub.spawn(self._discover)

    # show topo ,and get topo again
    def _discover(self):
        i = 0
        while True:
            self.show_topology()
            if i == 2:
                self.get_topology(None)
                i = 0
            hub.sleep(SLEEP_PERIOD)
            i = i + 1

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        msg = ev.msg
        self.logger.info("switch:%s connected", datapath.id)

        # install table-miss flow entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, dp, p, match, actions, idle_timeout=0, hard_timeout=0):
        ofproto = dp.ofproto
        parser = dp.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]

        mod = parser.OFPFlowMod(datapath=dp, priority=p,
                                idle_timeout=idle_timeout,
                                hard_timeout=hard_timeout,
                                match=match, instructions=inst)
        dp.send_msg(mod)

    def get_host_location(self, host_ip):
        for key in self.access_table.keys():
            if self.access_table[key][0] == host_ip:
                return key
        #self.logger.info("%s location is not found." % host_ip)
        return None

    def get_switches(self):
        return self.switches

    def get_links(self):
        return self.link_to_port

    # get Adjacency matrix from link_to_port
    def get_graph(self, link_list):
        for src in self.switches:
            for dst in self.switches:
                self.graph.add_edge(src, dst, weight=float('inf'))
                if src == dst:
                    self.graph.add_edge(src, dst, weight=0)
                elif (src, dst) in link_list:
                    self.graph.add_edge(src, dst, weight=1)
        return self.graph

    def create_port_map(self, switch_list):
        for sw in switch_list:
            dpid = sw.dp.id
            self.switch_port_table.setdefault(dpid, set())
            self.interior_ports.setdefault(dpid, set())
            self.access_ports.setdefault(dpid, set())

            for p in sw.ports:
                self.switch_port_table[dpid].add(p.port_no)

    # get links`srouce port to dst port  from link_list,
    # link_to_port:(src_dpid,dst_dpid)->(src_port,dst_port)
    def create_interior_links(self, link_list):
        for link in link_list:
            src = link.src
            dst = link.dst
            self.link_to_port[
                (src.dpid, dst.dpid)] = (src.port_no, dst.port_no)

            # find the access ports and interiorior ports
            if link.src.dpid in self.switches:
                self.interior_ports[link.src.dpid].add(link.src.port_no)
            if link.dst.dpid in self.switches:
                self.interior_ports[link.dst.dpid].add(link.dst.port_no)

    # get ports without link into access_ports
    def create_access_ports(self):
        for sw in self.switch_port_table:
            self.access_ports[sw] = self.switch_port_table[
                sw] - self.interior_ports[sw]

    events = [event.EventSwitchEnter,
              event.EventSwitchLeave, event.EventPortAdd,
              event.EventPortDelete, event.EventPortModify,
              event.EventLinkAdd, event.EventLinkDelete]

    @set_ev_cls(events)
    def get_topology(self, ev):
        switch_list = get_switch(self.topology_api_app, None)
        self.create_port_map(switch_list)
        self.switches = self.switch_port_table.keys()
        links = get_link(self.topology_api_app, None)
        self.create_interior_links(links)
        self.create_access_ports()
        self.get_graph(self.link_to_port.keys())

    @set_ev_cls(events)
    def get_shortest_paths(self, ev):
        self.shortest_paths = self.floyd_dict(self.graph)
        return self.shortest_paths

    def floyd_dict(self, graph, src=None, topo=None):
        return nx.all_pairs_dijkstra_path(graph)

    def register_access_info(self, dpid, in_port, ip, mac):
        if in_port in self.access_ports[dpid]:
            if (dpid, in_port) in self.access_table:
                if self.access_table[(dpid, in_port)] == (ip, mac):
                    return
                else:
                    self.access_table[(dpid, in_port)] = (ip, mac)
                    return
            else:
                self.access_table.setdefault((dpid, in_port), None)
                self.access_table[(dpid, in_port)] = (ip, mac)
                return

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath

        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)

        eth_type = pkt.get_protocols(ethernet.ethernet)[0].ethertype
        arp_pkt = pkt.get_protocol(arp.arp)
        ip_pkt = pkt.get_protocol(ipv4.ipv4)

        if arp_pkt:
            arp_src_ip = arp_pkt.src_ip
            arp_dst_ip = arp_pkt.dst_ip
            mac = arp_pkt.src_mac

            # record the access info
            self.register_access_info(datapath.id, in_port, arp_src_ip, mac)

    # show topo
    def show_topology(self):
        switch_num = len(self.graph.nodes())
        #if self.pre_graph != self.graph or IS_UPDATE:
            #print "---------------------Topo Link---------------------"
            #print '%10s' % ("switch"),
            #for i in xrange(1, switch_num + 1):
            #    print '%10d' % i,
            #print ""
            #for i in self.graph.nodes():
            #    print '%10d' % i,
            #    for j in self.graph[i].values():
            #        print '%10.0f' % j['weight'],
            #    print ""
            #self.pre_graph = copy.deepcopy(self.graph)

        if self.pre_link_to_port != self.link_to_port or IS_UPDATE:
            #print "---------------------Link Port---------------------"
            print "Topology Measurement Result:"
            print '%10s' % ("switch"),
            for i in xrange(1, switch_num + 1):
                print '%10d' % i,
            print ""
            for i in xrange(1, switch_num + 1):
                print '%10d' % i,
                for j in xrange(1, switch_num + 1):
                    if (i, j) in self.link_to_port.keys():
                        print '%10s' % str(self.link_to_port[(i, j)]),
                    else:
                        print '%10s' % "None",
                print ""
            self.pre_link_to_port = copy.deepcopy(self.link_to_port)

        # show host info:{(sw,port) :[host1_ip],...}
        #if self.pre_access_table != self.access_table or IS_UPDATE:
        #    print "----------------Access Host-------------------"
        #    print '%10s' % ("switch"), '%12s' % "Host"
        #    if not self.access_table.keys():
        #        print "    NO found host"
        #    else:
        #        for tup in self.access_table:
        #            print '%10d:    ' % tup[0], self.access_table[tup]
        #    self.pre_access_table = copy.deepcopy(self.access_table)
