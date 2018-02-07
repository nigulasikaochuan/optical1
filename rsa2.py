#coding:utf-8
from forwarding import ShortestForwarding
from mynetwork import Aware
from ryu.ofproto import ofproto_v1_3
from ryu.controller.handler import set_ev_cls
from ryu.controller.handler import MAIN_DISPATCHER,CONFIG_DISPATCHER
from ryu.base import app_manager
from ryu.controller import ofp_event
from spec_resource import ResourceManageMent
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ipv4
from ryu.lib.packet import arp

class Rsa2(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {"nettopo":Aware,'resource': ResourceManageMent,"forwarding":ShortestForwarding,}
    def __init__(self,*args,**kwargs):
        super(Rsa2, self).__init__(*args,**kwargs)

        self.net = kwargs["nettopo"]
        self.res = kwargs['resource']
        self.forwarding = kwargs["forwarding"]
    def add_flow(self, dp, p, match, actions, idle_timeout=0, hard_timeout=0):
        """
            Send a flow entry to datapath.
        """
        ofproto = dp.ofproto
        parser = dp.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]

        mod = parser.OFPFlowMod(datapath=dp, priority=p,
                                idle_timeout=idle_timeout,
                                hard_timeout=hard_timeout,
                                match=match, instructions=inst)
        dp.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def swithc_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        match = parser.OFPMatch()
        self.logger.info("{}connected".format(datapath.id))
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    @set_ev_cls(ofp_event.EventOFPPacketIn,MAIN_DISPATCHER)
    def packet_in_handler(self,ev):
        msg = ev.msg
        datapath = msg.datapath
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        arp_pkt = pkt.get_protocol(arp.arp)
        ip_pkt = pkt.get_protocol(ipv4.ipv4)

        if isinstance(arp_pkt, arp.arp):
            self.logger.debug("ARP processing")
            self.forwarding.arp_forwarding(msg, arp_pkt.src_ip, arp_pkt.dst_ip)
            self.net.register_host(datapath.id, pkt, in_port)

        if isinstance(ip_pkt, ipv4.ipv4):
            # self.logger.debug("IPV4 processing")
            # self.logger.info("交换机{},传递的inport{}".format(datapath.id, in_port))
            if len(pkt.get_protocols(ethernet.ethernet)):
                eth_type = pkt.get_protocols(ethernet.ethernet)[0].ethertype
                self.logger.info("*"*80)
                self.logger.info("datapath{},源{} 目{}".format(datapath.id,ip_pkt.src,ip_pkt.dst))
                self.logger.info("*" * 80)
                self.forwarding.shortest_forwarding(msg, eth_type, ip_pkt.src, ip_pkt.dst)
