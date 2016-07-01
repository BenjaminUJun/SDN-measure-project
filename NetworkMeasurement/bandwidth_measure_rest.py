#!/usr/bin/env python
import json
import logging

from ryu.app.network_aware import bandwidth_measure
from webob import Response
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.app.wsgi import ControllerBase, WSGIApplication, route
from ryu.lib import dpid as dpid_lib

bandwidth_instance_name = 'bandwidth_api_app'
set_url = '/measurement/bandwidth/set/{src_dpid}/{dst_dpid}'
get_url = '/measurement/bandwidth/get/{src_dpid}/{dst_dpid}'
set_flow = '/measurement/bandwidth/flow/set/{dpid}/{src_ip}/{dst_ip}'
get_flow = '/measurement/bandwidth/flow/get/{dpid}/{src_ip}/{dst_ip}'

class BandwidthMeasureREST(bandwidth_measure.BandwidthMeasure):

    _CONTEXTS = { 'wsgi': WSGIApplication }

    def __init__(self, *args, **kwargs):
        super(BandwidthMeasureREST, self).__init__(*args, **kwargs)
        wsgi = kwargs['wsgi']
        wsgi.register(BandwidthMeasureController, {bandwidth_instance_name:self})

    def addPortTask(self, src_dpid, dst_dpid):
        print 'REST!!'
        result = self.add_Port_Task(src_dpid,dst_dpid)
        print result
        return result

    def getPortBandWidth(self, src_dpid, dst_dpid):
        print 'REST!!'
        result = self.get_Port_Bandwidth(src_dpid,dst_dpid)
        print result
        return result

    def addFlowTask(self, dpid, src_ip, dst_ip):
        print 'REST!!'
	result = self.add_Flow_Task(dpid, src_ip, dst_ip)
        print result
        return result

    def getFlowBandwidth(self, dpid, src_ip, dst_ip):
        print 'REST!!'
	result = self.get_Flow_Bandwidth(dpid, src_ip, dst_ip)
        print result
        return result

class BandwidthMeasureController(ControllerBase):

    def __init__(self, req, link, data, **config):
        super(BandwidthMeasureController, self).__init__(req, link, data, **config)
        self.bandwidth_spp = data[bandwidth_instance_name]

    @route('add_port_measure', set_url, methods=['GET'])
    def addPortTask(self, req, **kwargs):
        bandwidth_api = self.bandwidth_spp
        src_dpid = int(kwargs['src_dpid'])
        dst_dpid = int(kwargs['dst_dpid'])

        result = bandwidth_api.addPortTask(src_dpid,dst_dpid)
        if result is not None:
            body = json.dumps({'src_dpid':result[0],'src_port':result[1],
                'dst_dpid':result[2],'dst_port':result[3]})
        else:
            body = json.dumps({'result':result})
        return Response(content_type='application/json', body=body)

    @route('get_port_bandwidth', get_url, methods=['GET'])
    def getPortBandWidth(self, req, **kwargs):
        bandwidth_api = self.bandwidth_spp
        src_dpid = int(kwargs['src_dpid'])
        dst_dpid = int(kwargs['dst_dpid'])

        result = bandwidth_api.getPortBandWidth(src_dpid,dst_dpid)
        if result is not None:
            body = json.dumps({'src_dpid':src_dpid,'src_port':result[0][1], 'src_stats': result[0][2], 'src_speed': result[0][2],
                'dst_dpid':dst_dpid,'dst_port':result[1][0], 'dst_stats': result[1][1], 'dst_speed': result[1][2]})
        else:
            body = json.dumps({'result':result})

        return Response(content_type='application/json', body=body)

    @route('add_flow_bandwidth', set_flow, methods=['GET'])
    def add_Flow_Task(self, req, **kwargs):
        bandwidth_api = self.bandwidth_spp
        dpid = int(kwargs['dpid'])
        src_ip = kwargs['src_ip']
        dst_ip = kwargs['dst_ip']

        result = bandwidth_api.addFlowTask(dpid, src_ip, dst_ip)
        if result is not None:
            body = json.dumps({'dpid':result[0], 'src':result[1], 'dst':result[2]})
        else:
            body = json.dumps({'result':result})
        return Response(content_type='application/json', body=body)

    @route('get_flow_bandwidth', get_flow, methods=['GET'])
    def getFlowBandWidth(self, req, **kwargs):
        bandwidth_api = self.bandwidth_spp
        dpid = int(kwargs['dpid'])
        src_ip = kwargs['src_ip']
        dst_ip = kwargs['dst_ip']

        result = bandwidth_api.getFlowBandwidth(dpid, src_ip, dst_ip)
        if result is not None:
            body = json.dumps({'dpid':result[0], 'src':result[1], 'dst':result[2],
		'stats':result[3], 'speed':result[4]})
        else:
            body = json.dumps({'result':result})
        return Response(content_type='application/json', body=body)
