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

class BandwidthMeasure(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _NAME = 'BandwidthMeasure'

    reply_count_src={'dpid':0, 'port':0, 'count':0}
    reply_count_dst={'dpid':0, 'port':0, 'count':0}
    flow_reply_count = {'dpid':0, 'src_ip':'', 'dst_ip':'', 'count':0}

    def __init__(self, *args, **kwargs):
        super(BandwidthMeasure, self).__init__(*args, **kwargs)

        self.datapaths = {}
        self.port_stats = {}
        self.port_speed = {}
        self.flow_stats = {}
        self.flow_speed = {}
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
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        self.stats['flow'][dpid] = body
        self.flow_stats.setdefault(dpid, {})
        self.flow_speed.setdefault(dpid, {})
        for stat in sorted([flow for flow in body if flow.priority == 1],
                           key=lambda flow: (flow.match.get('ipv4_src'),
                                             flow.match.get('ipv4_dst'))):
            if self.flow_reply_count['src_ip'] == stat.match.get('ipv4_src') and self.flow_reply_count['dst_ip'] == stat.match.get('ipv4_dst'):
                key = (stat.match.get('ipv4_src'), stat.match.get('ipv4_dst'))
                value = (stat.packet_count, stat.byte_count,
                         stat.duration_sec, stat.duration_nsec)
                self._save_stats(self.flow_stats[dpid], key, value, 2)
		print 'get it!'

                # Get flow's speed.
                pre = 0
                speed = 0
                period = 1
                tmp = self.flow_stats[dpid][key]
                if len(tmp) > 1:
                    pre = tmp[-2][1]
                    period = self._get_period(tmp[-1][2], tmp[-1][3],
                                              tmp[-2][2], tmp[-2][3])

                speed = self._get_speed(self.flow_stats[dpid][key][-1][1], pre, period)

                self._save_stats(self.flow_speed[dpid], key, speed, 2)
		self.flow_reply_count['count'] = 0

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        body = ev.msg.body
        self.stats['port'][ev.msg.datapath.id] = body
        for stat in sorted(body, key=attrgetter('port_no')):
            if stat.port_no != ofproto_v1_3.OFPP_LOCAL:

        	if self.reply_count_src['dpid'] == ev.msg.datapath.id and self.reply_count_src['port'] == stat.port_no:
		    self.reply_count_src['count'] = 0
		elif self.reply_count_dst['dpid'] == ev.msg.datapath.id and self.reply_count_dst['port'] == stat.port_no:
		    self.reply_count_dst['count'] = 0

		key = (ev.msg.datapath.id, stat.port_no)
                value = (stat.tx_bytes, stat.rx_bytes, stat.rx_errors,
                         stat.duration_sec, stat.duration_nsec)

                self._save_stats(self.port_stats, key, value, 2)

                # Get port speed.
                pre = 0
                period = 1
                tmp = self.port_stats[key]
                if len(tmp) > 1:
                    pre = tmp[-2][0] + tmp[-2][1]
                    period = self._get_period(tmp[-1][3], tmp[-1][4],
                                              tmp[-2][3], tmp[-2][4])

                print period
                speed = self._get_speed(
                    self.port_stats[key][-1][0] + self.port_stats[key][-1][1],
                    pre, period)

                self._save_stats(self.port_speed, key, speed, 2)

    def _request_stats(self, datapath):
        self.logger.debug('send stats request: %016x', datapath.id)
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)

        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)

        req = parser.OFPPortDescStatsRequest(datapath, 0)
        datapath.send_msg(req)

    def _save_stats(self, dist, key, value, length):
        if key not in dist:
            dist[key] = []
        dist[key].append(value)

        if len(dist[key]) > length:
            dist[key].pop(0)

    def _get_speed(self, now, pre, period):
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

    def get_Port_Bandwidth(self, src_dpid, dst_dpid):
        topo = app_manager.lookup_service_brick('Shortest_Forwarding')
        src_port = topo.get_link_to_port(topo.network_aware.link_to_port, src_dpid, dst_dpid)[0]
        dst_port = topo.get_link_to_port(topo.network_aware.link_to_port, dst_dpid, src_dpid)[0]
        self.send_port_stats_request(self.datapaths[src_dpid], src_port)
        self.send_port_stats_request(self.datapaths[dst_dpid], dst_port)
        self.reply_count_src={'dpid':src_dpid, 'port':src_port, 'count':1}
        self.reply_count_dst={'dpid':dst_dpid, 'port':dst_port, 'count':1}

        while self.reply_count_src['count'] != 0 or self.reply_count_dst['count'] != 0 :
            time.sleep(0.01)

        return ((src_port, self.port_stats[(src_dpid, src_port)][-1], self.port_speed[(src_dpid, src_port)][-1]),
            (dst_port, self.port_stats[(src_dpid, src_port)][-1], self.port_speed[(src_dpid, src_port)][-1]))

    def add_Port_Task(self, src_dpid, dst_dpid):
        topo = app_manager.lookup_service_brick('Shortest_Forwarding')
        src_port = topo.get_link_to_port(topo.network_aware.link_to_port, src_dpid, dst_dpid)[0]
        dst_port = topo.get_link_to_port(topo.network_aware.link_to_port, dst_dpid, src_dpid)[0]
        self.send_port_stats_request(self.datapaths[src_dpid], src_port)
        self.send_port_stats_request(self.datapaths[dst_dpid], dst_port)
        return (src_dpid, src_port, dst_dpid, dst_port)


    def get_Flow_Bandwidth(self, dpid, src_ip, dst_ip):
        topo = app_manager.lookup_service_brick('Shortest_Forwarding')
        self.flow_reply_count = {'dpid':dpid, 'src_ip':src_ip, 'dst_ip':dst_ip, 'count':1}
        self.send_flow_stats_request(self.datapaths[dpid])

	while self.flow_reply_count['count'] != 0 :
            time.sleep(0.01)
	print self.flow_stats
	return (dpid, src_ip, dst_ip, self.flow_stats[dpid][(src_ip, dst_ip)][-1], self.flow_speed[dpid][(src_ip, dst_ip)][-1])

    def add_Flow_Task(self, dpid, src_ip, dst_ip):
        topo = app_manager.lookup_service_brick('Shortest_Forwarding')
        self.flow_reply_count = {'dpid':dpid, 'src_ip':src_ip, 'dst_ip':dst_ip, 'count':1}
        self.send_flow_stats_request(self.datapaths[dpid])
        return (dpid,src_ip,dst_ip)