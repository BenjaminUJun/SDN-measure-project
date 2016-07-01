# conding=utf-8
import logging
import struct
import networkx as nx
from operator import attrgetter
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.ofproto import ether
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import arp
from ryu.lib.packet import vlan
from ryu.lib.packet import ipv4
from ryu.lib.packet import udp
from ryu.lib.packet import tcp
from ryu.topology import event, switches
from ryu.topology.api import get_switch, get_link

import time
import network_aware
import network_monitor


class Get_Delay(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    total_time = 0
    total_rtt = 0
    test_path = []
    rtt_src = {'dpid':'0','time':0}
    rtt_dst = {'dpid':'0','time':0}
    packets_NO = 0
    reply_NO = 0

    def __init__(self, *args, **kwargs):
        super(Get_Delay, self).__init__(*args, **kwargs)
        self.datapaths = {}

    @set_ev_cls(ofp_event.EventOFPStateChange,
                [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if not datapath.id in self.datapaths:
                self.logger.debug('register datapath: %016x', datapath.id)
                self.datapaths[datapath.id] = datapath
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                self.logger.debug('unregister datapath: %016x', datapath.id)
                del self.datapaths[datapath.id]

    def _build_packet_out(self, datapath, buffer_id, src_port, dst_port, data):
        actions = []
        if dst_port:
            actions.append(datapath.ofproto_parser.OFPActionOutput(dst_port))

        msg_data = None
        if buffer_id == datapath.ofproto.OFP_NO_BUFFER:
            if data is None:
                return None
            msg_data = data

        out = datapath.ofproto_parser.OFPPacketOut(datapath=datapath, buffer_id=buffer_id,data=msg_data, in_port=src_port, actions=actions)
        return out

    def send_packet_out(self, datapath, buffer_id, src_port, dst_port, data):
        out = self._build_packet_out(datapath, buffer_id,
                                     src_port, dst_port, data)
        if out:
            datapath.send_msg(out)
            return time.time()
        return None

    def send_meter_stats_request(self, datapath):
        ofp = datapath.ofproto
        ofp_parser = datapath.ofproto_parser
        req = ofp_parser.OFPMeterStatsRequest(datapath, 0, ofp.OFPM_ALL)
        datapath.send_msg(req)
        return time.time()

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        '''
            In packet_in handler, we need to learn access_table by ARP.
            Therefore, the first packet from UNKOWN host MUST be ARP.
        '''
        receive_time = time.time()
        msg = ev.msg
        datapath = msg.datapath
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        arp_pkt = pkt.get_protocol(arp.arp)
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        eth_type = pkt.get_protocols(ethernet.ethernet)[0].ethertype
        if eth_type == 0x07c3:
            result_list = pkt[-1].split('#')
            #self.total_time = receive_time-float(result_list[1])
            self.total_time -= receive_time
            self.packets_NO -= 1
            print ("received!")

    @set_ev_cls(ofp_event.EventOFPMeterStatsReply, MAIN_DISPATCHER)
    def meter_stats_reply_handler(self, ev):
        receive_time = time.time()
        dpid = ev.msg.datapath.id
        if self.rtt_src['dpid']==dpid:
            self.rtt_src['time']=receive_time-self.rtt_src['time']
        elif self.rtt_dst['dpid']==dpid:
            self.rtt_dst['time']=receive_time-self.rtt_dst['time']
        else:
            self.total_rtt -= receive_time
        self.reply_NO -= 1
        print self.reply_NO

    def test_delay(self, src_dpid, dst_dpid):
        topo = app_manager.lookup_service_brick('Shortest_Forwarding')
        test_path = topo.get_path(src_dpid,dst_dpid)
        print test_path
        if test_path is None:
            return test_path

        self.resetTime(test_path)
        #test src rtt
        self.rtt_src['time'] = self.send_meter_stats_request(self.datapaths[src_dpid])
        #test dst rtt
        self.rtt_dst['time'] = self.send_meter_stats_request(self.datapaths[dst_dpid])

        if(len(test_path) > 2):
            for dpid in test_path[1:-1]:
                self.total_rtt += self.send_meter_stats_request(self.datapaths[dpid])



        #send test packet
        for i in range(len(test_path)-1):
            src = test_path[i]
            dst = test_path[i+1]
            out_port = topo.get_link_to_port(topo.network_aware.link_to_port, src, dst)[0]
            p = self.build_packet(out_port)
            self.total_time+=self.send_packet_out(self.datapaths[src], self.datapaths[src].ofproto.OFP_NO_BUFFER, 
                self.datapaths[src].ofproto.OFPP_CONTROLLER, out_port, p.data)


        #time.sleep(1)
        while self.packets_NO != 0 or self.reply_NO != 0:
	       time.sleep(0.01)

        print ("success")
        delay_result = abs(self.total_time)-abs(self.total_rtt)-(self.rtt_src['time']+self.rtt_dst['time'])/2
        print (abs(self.total_time))
        print (abs(self.total_rtt))
        print ((self.rtt_src['time']+self.rtt_dst['time'])/2)
        return delay_result
    
    def resetTime(self, path):
        self.total_time = 0
        self.total_rtt = 0
        self.rtt_src = {'dpid':path[0],'time':0}
        self.rtt_dst = {'dpid':path[-1],'time':0}
        self.packets_NO = len(path)-1
        self.reply_NO = len(path)

    def build_packet(self, out_port):
        ethertype = 0x07c3
        dst = '00:00:00:00:00:01'
        src = '00:00:00:00:00:02' 
        e = ethernet.ethernet(dst, src, ethertype)
        p = packet.Packet()
        p.add_protocol(e)
        p.add_protocol(out_port)
        p.add_protocol('#')
        p.add_protocol(time.time())
        p.serialize()
        return p