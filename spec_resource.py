#coding:utf-8
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import set_ev_cls
from ryu.controller.handler import CONFIG_DISPATCHER,MAIN_DISPATCHER,DEAD_DISPATCHER
from ryu.ofproto import ofproto_v1_3
from ryu.topology import event
from ryu.base.app_manager import _lookup_service_brick_by_mod_name
from ryu.lib import hub
from ryu.lib.packet import packet
from mynetwork import Aware
import event

#Event_to_listened_by_getTopo = [event.EventLinkAdd, event.EventLinkDelete, event.EventPortAdd,
 #                               event.EventPortDelete, event.EventPortModify, event.EventSwitchEnter, event.EventSwitchLeave]
class ResourceManageMent(app_manager.RyuApp):
  #  _CONTEXTS = {'network_topo': Aware}
    #resource = ['1999', '2000', '2001', '2002']

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ResourceManageMent, self).__init__(*args, **kwargs)
        self.name = 'link_resource'
        self.network_topo = _lookup_service_brick_by_mod_name("awareness")
        #self.distance_between_nodes = self.network_topo.distances_between_nodes
        self.distance_between_nodes = {
            (2, 1): 1050, (2, 3): 600, (2, 4): 750, (1, 3): 1500, (1, 8): 2400, (3, 6): 1800, (4, 5): 600,
            (4, 11): 1950, (5, 7): 600,
            (5, 6): 1200, (7, 8): 750, (7, 10): 1350, (6, 14): 1800, (6, 10): 1050, (8, 9): 750, (9, 13): 300,
            (9, 10): 750, (9, 12): 300,
            (11, 12): 600, (11, 13): 750, (12, 14): 300, (13, 14): 150
        }
        #hahjkdfjalkjdkljakldfjakljfkdlklajkl
        self.remainSlots = {key:[i for i in range(128)] for key in self.distance_between_nodes}
        self.weight={}
        for (src_dpid, dst_dpid) in self.distance_between_nodes:
                self.weight[(src_dpid, dst_dpid)] = self.distance_between_nodes[(src_dpid, dst_dpid)] / len(self.remainSlots[(src_dpid, dst_dpid)])

        self.paths =[]
       
        self.monitor = hub.spawn(self.__monitor)

    def __monitor(self):
        i = 0
        while True:
            if i==5:
                self.set_weight_of_link()
                i=0
            hub.sleep(1)
            i=i+1

    @set_ev_cls(ofp_event.EventOFPStateChange)
    def event_ofp_state_change(self,ev):

        if ev.state == MAIN_DISPATCHER:
            self.paths.append(ev.datapath)
            #self.logger.info('register...{}'.format(ev.datapath.id))
        if ev.state == DEAD_DISPATCHER:
            self.paths.remove(ev.datapath)
            self.logger.info('remove...{}'.format(ev.datapath.id))

    def set_weight_of_link(self):
        self.calc_weight()
        self.network_topo.creat_graph(self.weight)
        #self.logger.info('adj:{}'.format(self.network_topo.graph.adj))
        self.network_topo.creat_shortest_paths(3)

    @set_ev_cls(event.EventRequestSpectrumRemain)
    def reply_ResourceManageMent(self, request):
        reply = event.EventReplySpectrumRemain(request.dst, self.remainSlots)
        self.reply_to_request(request, reply)
    def calc_weight(self):
        for (src_dpid, dst_dpid) in self.distance_between_nodes:
            try:
                self.weight[(src_dpid, dst_dpid)] = self.distance_between_nodes[(src_dpid, dst_dpid)]/len(self.remainSlots[(src_dpid, dst_dpid)])
            except ZeroDivisionError:
                self.weight[(src_dpid,dst_dpid)] = 9999999
    def first_feeding_spec(self):
        pass