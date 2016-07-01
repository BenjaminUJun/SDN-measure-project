#!/usr/bin/env python
import json
import logging

from ryu.app.network_aware import loss_measure
from webob import Response
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.app.wsgi import ControllerBase, WSGIApplication, route
from ryu.lib import dpid as dpid_lib

loss_instance_name = 'loss_api_app'
set_url = '/measurement/loss/set/{src_dpid}/{dst_dpid}'
get_url = '/measurement/loss/get/{src_dpid}/{dst_dpid}'
set_flow = '/measurement/loss/flow/set/{src_ip}/{dst_ip}'
get_flow = '/measurement/loss/flow/get/{src_ip}/{dst_ip}'

class LossMeasureREST(loss_measure.LossMeasure):

    _CONTEXTS = { 'wsgi': WSGIApplication }

    def __init__(self, *args, **kwargs):
        super(LossMeasureREST, self).__init__(*args, **kwargs)
        wsgi = kwargs['wsgi']
        wsgi.register(LossMeasureController, {loss_instance_name:self})

    def addLinkTask(self, src_dpid, dst_dpid):
        print 'REST!!'
        result = self.add_Link_Task(src_dpid,dst_dpid)
        print result
        return result

    def getLinkLoss(self, src_dpid, dst_dpid):
        print 'REST!!'
        result = self.get_Link_Loss(src_dpid,dst_dpid)
        print result
        return result

    def addFlowTask(self, src_ip, dst_ip):
        print 'REST!!'
        result = self.add_Flow_Task(src_ip, dst_ip)
        #result = 0
        print result
        return result

    def getFlowLoss(self, src_ip, dst_ip):
        print 'REST!!'
        result = self.get_Flow_Loss(src_ip, dst_ip)
        #result = 0
        print result
        return result

class LossMeasureController(ControllerBase):

    def __init__(self, req, link, data, **config):
        super(LossMeasureController, self).__init__(req, link, data, **config)
        self.loss_spp = data[loss_instance_name]

    @route('add_link_loss', set_url, methods=['GET'])
    def addLinkTask(self, req, **kwargs):
        loss_api = self.loss_spp
        src_dpid = int(kwargs['src_dpid'])
        dst_dpid = int(kwargs['dst_dpid'])

        result = loss_api.addLinkTask(src_dpid,dst_dpid)
        if result is not None:
            body = json.dumps({'src_dpid':result[0],'src_port':result[1],
                'dst_dpid':result[2],'dst_port':result[3]})
        else:
            body = json.dumps({'result':result})
        return Response(content_type='application/json', body=body)

    @route('get_link_loss', get_url, methods=['GET'])
    def getLinkLoss(self, req, **kwargs):
        loss_api = self.loss_spp
        src_dpid = int(kwargs['src_dpid'])
        dst_dpid = int(kwargs['dst_dpid'])

        result = loss_api.getLinkLoss(src_dpid,dst_dpid)
        if result is not None:
            body = json.dumps({'src_dpid':src_dpid,'src_port':result[0][0], 'src_stats': result[0][1], 'loss_forward': result[0][2],
                'dst_dpid':dst_dpid,'dst_port':result[1][0], 'dst_stats': result[1][1], 'loss_back': result[1][2]})
        else:
            body = json.dumps({'result':result})
        return Response(content_type='application/json', body=body)

    @route('add_flow_loss', set_flow, methods=['GET'])
    def addFlowTask(self, req, **kwargs):
        loss_api = self.loss_spp
        src_ip = kwargs['src_ip']
        dst_ip = kwargs['dst_ip']

        result = loss_api.addFlowTask(src_ip, dst_ip)
        if result is not None:
            body = json.dumps({'src':result[0], 'dst':result[1],
                'src_dpid': result[2], 'dst_dpid': result[3]})
        else:
            body = json.dumps({'result':result})
        return Response(content_type='application/json', body=body)

    @route('get_flow_loss', get_flow, methods=['GET'])
    def getFlowLoss(self, req, **kwargs):
        loss_api = self.loss_spp
        src_ip = kwargs['src_ip']
        dst_ip = kwargs['dst_ip']

        result = loss_api.getFlowLoss(src_ip, dst_ip)
        if result is not None:
            body = json.dumps({'src':result[0], 'dst':result[1],
                'src_dpid': result[2], 'src_dpid_stats':result[3],
                'dst_dpid': result[4], 'dst_dpid_stats':result[5],
                'loss':result[6]})
        else:
            body = json.dumps({'result':result})
        return Response(content_type='application/json', body=body)
