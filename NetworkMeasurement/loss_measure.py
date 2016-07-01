from __future__ import division
from operator import attrgetter
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub
from ryu.lib.packet import packet

import time

class LossMeasure(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _NAME = 'LossMeasure'

    reply_count_src={'dpid':0, 'port':0, 'count':0}
    reply_count_dst={'dpid':0, 'port':0, 'count':0}
    flow_reply_count = {'dpid':0, 'src_ip':'', 'dst_ip':'', 'count':0}
    is_loss_task = 0

    def __init__(self, *args, **kwargs):
        super(LossMeasure, self).__init__(*args, **kwargs)

        self.datapaths = {}
        self.port_stats = {}
        self.link_loss = {}
        self.flow_stats = {}
        self.flow_loss = {}
        self.stats = {}
        self.stats['flow'] = {}
        self.stats['port'] = {}
        self.port_link = {}

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

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply_handler(self, ev):
        if self.is_loss_task == 1:
            body = ev.msg.body
            dpid = ev.msg.datapath.id
            self.stats['flow'][dpid] = body
            self.flow_stats.setdefault(dpid, {})
            for stat in sorted([flow for flow in body if flow.priority == 1],
                               key=lambda flow: (flow.match.get('ipv4_src'),
                                                 flow.match.get('ipv4_dst'))):
                if self.flow_reply_count['src_ip'] == stat.match.get('ipv4_src') and self.flow_reply_count['dst_ip'] == stat.match.get('ipv4_dst'):
                    key = (stat.match.get('ipv4_src'), stat.match.get('ipv4_dst'))
                    value = (stat.packet_count, stat.byte_count,
                         stat.duration_sec, stat.duration_nsec)
                    self._save_stats(self.flow_stats[dpid], key, value, 3)
                    print 'get it!'
                    self.flow_reply_count['count'] -=1

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        if self.is_loss_task == 1:
            print 'get it!'
            body = ev.msg.body
            self.stats['port'][ev.msg.datapath.id] = body
            for stat in sorted(body, key=attrgetter('port_no')):
                if stat.port_no != ofproto_v1_3.OFPP_LOCAL:

		    if self.reply_count_src['dpid'] == ev.msg.datapath.id and self.reply_count_src['port'] == stat.port_no:
                        self.reply_count_src['count'] = 0
                    elif self.reply_count_dst['dpid'] == ev.msg.datapath.id and self.reply_count_dst['port'] == stat.port_no:
                        self.reply_count_dst['count'] = 0

                    key = (ev.msg.datapath.id, stat.port_no)
                    value = (stat.tx_packets, stat.rx_packets, stat.rx_errors,
                             stat.duration_sec, stat.duration_nsec)

                    self._save_stats(self.port_stats, key, value, 3)


    def _save_stats(self, dist, key, value, length):
        if key not in dist:
            dist[key] = []
        dist[key].append(value)

        if len(dist[key]) > length:
            dist[key].pop(0)

    def _get_Loss(self, now, pre, period):
        if period:
            return (now - pre) / (period)
        else:
            return 0

    def _get_time(self, sec, nsec):
        return sec + nsec / (10 ** 9)

    def _get_period(self, n_sec, n_nsec, p_sec, p_nsec):
        return self._get_time(n_sec, n_nsec) - self._get_time(p_sec, p_nsec)

    def send_port_stats_request(self, datapath, port):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        req = parser.OFPPortStatsRequest(datapath, 0, port)
        datapath.send_msg(req)

    def send_flow_stats_request(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)

    def get_Link_Loss(self, src_dpid, dst_dpid):
        self.is_loss_task = 1
        topo = app_manager.lookup_service_brick('Shortest_Forwarding')
        src_port = topo.get_link_to_port(topo.network_aware.link_to_port, src_dpid, dst_dpid)[0]
        dst_port = topo.get_link_to_port(topo.network_aware.link_to_port, dst_dpid, src_dpid)[0]
        self.send_port_stats_request(self.datapaths[src_dpid], src_port)
        self.send_port_stats_request(self.datapaths[dst_dpid], dst_port)
        self.reply_count_src={'dpid':src_dpid, 'port':src_port, 'count':1}
        self.reply_count_dst={'dpid':dst_dpid, 'port':dst_port, 'count':1}

        while self.reply_count_src['count'] != 0 or self.reply_count_dst['count'] != 0 :
            time.sleep(0.01)

        self.is_loss_task = 0

        self._get_Link_Loss(src_dpid, src_port, dst_dpid, dst_port)
        self._get_Link_Loss(dst_dpid, dst_port, src_dpid, src_port)

        return ((src_port, self.port_stats[(src_dpid, src_port)][-1], self.link_loss[(src_dpid, dst_dpid)][-1]), 
            (dst_port, self.port_stats[(dst_dpid, dst_port)][-1], self.link_loss[(dst_dpid, src_dpid)][-1]))

    def add_Link_Task(self, src_dpid, dst_dpid):
        self.is_loss_task = 1
        topo = app_manager.lookup_service_brick('Shortest_Forwarding')
        src_port = topo.get_link_to_port(topo.network_aware.link_to_port, src_dpid, dst_dpid)[0]
        dst_port = topo.get_link_to_port(topo.network_aware.link_to_port, dst_dpid, src_dpid)[0]
        self.send_port_stats_request(self.datapaths[src_dpid], src_port)
        self.send_port_stats_request(self.datapaths[dst_dpid], dst_port)
        self.reply_count_src={'dpid':src_dpid, 'port':src_port, 'count':1}
        self.reply_count_dst={'dpid':dst_dpid, 'port':dst_port, 'count':1}

        while self.reply_count_src['count'] != 0 or self.reply_count_dst['count'] != 0 :
            time.sleep(0.01)

        self.is_loss_task = 0
        return (src_dpid, src_port, dst_dpid, dst_port)


    def get_Flow_Loss(self, src_ip, dst_ip):
        self.is_loss_task = 1
        topo = app_manager.lookup_service_brick('Shortest_Forwarding')
        flow_path = topo.flowPaths[(src_ip,dst_ip)]
        self.flow_reply_count = {'src_ip':src_ip, 'dst_ip':dst_ip, 'count':2}
        self.send_flow_stats_request(self.datapaths[flow_path[0]])
        self.send_flow_stats_request(self.datapaths[flow_path[-1]])

        while self.flow_reply_count['count'] != 0 :
            time.sleep(0.01)

        self.is_loss_task = 0

        self._get_Flow_Loss(src_ip, dst_ip, flow_path[0], flow_path[-1])

        return (src_ip, dst_ip, flow_path[0], self.flow_stats[flow_path[0]][(src_ip, dst_ip)][-1],
            flow_path[-1], self.flow_stats[flow_path[-1]][(src_ip, dst_ip)][-1], self.flow_loss[(src_ip, dst_ip)][-1])

    def add_Flow_Task(self, src_ip, dst_ip):
        self.is_loss_task = 1

        topo = app_manager.lookup_service_brick('Shortest_Forwarding')
        flow_path = topo.flowPaths[(src_ip,dst_ip)]
        self.flow_reply_count = {'src_ip':src_ip, 'dst_ip':dst_ip, 'count':2}
        self.send_flow_stats_request(self.datapaths[flow_path[0]])
        self.send_flow_stats_request(self.datapaths[flow_path[-1]])

        while self.flow_reply_count['count'] != 0 :
            time.sleep(0.01)

        self.is_loss_task = 0
        return (src_ip, dst_ip, flow_path[0], flow_path[-1])

    def _get_Link_Loss(self, src_dpid, src_port, dst_dpid, dst_port):
        #(stat.tx_bytes, stat.rx_bytes, stat.rx_errors, stat.duration_sec, stat.duration_nsec)
        print self.port_stats[(src_dpid, src_port)]
        tx = self.port_stats[(src_dpid, src_port)][-1][0] - self.port_stats[(src_dpid, src_port)][-2][0]
        rc = self.port_stats[(dst_dpid, dst_port)][-1][1] - self.port_stats[(dst_dpid, dst_port)][-2][1]
        loss = 0
        if tx != 0:
            loss = (tx-rc)/tx
        self._save_stats(self.link_loss, (src_dpid, dst_dpid), loss, 2)
        return loss

    def _get_Flow_Loss(self, src_ip, dst_ip, src_dpid, dst_dpid):
        #(stat.packet_count, stat.byte_count, stat.duration_sec, stat.duration_nsec)
        #print self.port_stats[(src_ip, dst_ip)]
        rc_src = self.flow_stats[src_dpid][(src_ip, dst_ip)][-1][0] - self.flow_stats[src_dpid][(src_ip, dst_ip)][-2][0]
        rc_dst = self.flow_stats[dst_dpid][(src_ip, dst_ip)][-1][0] - self.flow_stats[dst_dpid][(src_ip, dst_ip)][-2][0]
        loss = 0
        if rc_src != 0:
            loss = (rc_src-rc_dst)/rc_src
        self._save_stats(self.flow_loss, (src_ip, dst_ip), loss, 2)
        return loss