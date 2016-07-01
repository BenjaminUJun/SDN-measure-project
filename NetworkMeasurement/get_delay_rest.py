#!/usr/bin/env python
import json
import logging

from ryu.app.network_aware import get_delay
from webob import Response
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.app.wsgi import ControllerBase, WSGIApplication, route
from ryu.lib import dpid as dpid_lib

get_delay_instance_name = 'get_delay_api_app'
url = '/measurement/delay/{src_dpid}/{dst_dpid}'

class GetDelayRest(get_delay.Get_Delay):

    _CONTEXTS = { 'wsgi': WSGIApplication }

    def __init__(self, *args, **kwargs):
        super(GetDelayRest, self).__init__(*args, **kwargs)
        wsgi = kwargs['wsgi']
        wsgi.register(GetDelayController, {get_delay_instance_name:self})

    def get_delay_result(self, src_dpid, dst_dpid):
        result = self.test_delay(src_dpid,dst_dpid)
        return result

        src_dpid = int(kwargs['src_dpid'])
        dst_dpid = int(kwargs['dst_dpid'])

class GetDelayController(ControllerBase):

    def __init__(self, req, link, data, **config):
        super(GetDelayController, self).__init__(req, link, data, **config)
        self.get_delay_spp = data[get_delay_instance_name]

    @route('measurement', url, methods=['GET'])
    def list_mac_table(self, req, **kwargs):
        get_delay_api = self.get_delay_spp
        src_dpid = int(kwargs['src_dpid'])
        dst_dpid = int(kwargs['dst_dpid'])

        result = get_delay_api.get_delay_result(src_dpid,dst_dpid)
        body = json.dumps({'delay_result':result})
        return Response(content_type='application/json', body=body)