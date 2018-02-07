# coding:utf-8
import logging
import struct
import networkx as nx
from operator import attrgetter
from ryu import cfg
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
from ryu.base.app_manager import _lookup_service_brick_by_mod_name
from ryu.topology import event, switches
from ryu.topology.api import get_switch, get_link
from spec_resource import ResourceManageMent
import mynetwork
from mynetwork import Aware


class ShortestForwarding(app_manager.RyuApp):
    """
        ShortestForwarding is a Ryu app for forwarding packets in shortest
        path.
        The shortest path computation is done by module network awareness,
        network monitor and network delay detector.
    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'network_topo': Aware, "resource": ResourceManageMent, }

    # WEIGHT_MODEL = {'hop': 'weight', 'delay': "delay", "bw": "bw"}

    def __init__(self, *args, **kwargs):
        super(ShortestForwarding, self).__init__(*args, **kwargs)
        self.name = 'shortest_forwarding'
        self.awareness = _lookup_service_brick_by_mod_name("awareness")
        self.datapaths = {}

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        """
            Collect datapath information.
        """
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if not datapath.id in self.datapaths:
                #self.logger.info('register datapath: %016x', datapath.id)
                self.datapaths[datapath.id] = datapath
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                #self.logger.info('unregister datapath: %016x', datapath.id)
                del self.datapaths[datapath.id]

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
                                match=match, instructions=inst, flags=ofproto.OFPFF_SEND_FLOW_REM)
        dp.send_msg(mod)

    def send_flow_mod(self, datapath, flow_info, src_port, dst_port):
        """
            Build flow entry, and send it to datapath.
        """
        parser = datapath.ofproto_parser
        actions = []
        actions.append(parser.OFPActionOutput(dst_port))

        match = parser.OFPMatch(
            in_port=src_port, eth_type=flow_info[0],
            ipv4_src=flow_info[1], ipv4_dst=flow_info[2])

        self.add_flow(datapath, 1, match, actions,
                      idle_timeout=30, hard_timeout=30)

       #
    # @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    # def swithc_handler(self, ev):
    #     msg = ev.msg
    #     datapath = msg.datapath
    #     ofproto = datapath.ofproto
    #     parser = datapath.ofproto_parser
    #     match = parser.OFPMatch()
    #     self.logger.info("{}connected".format(datapath.id))
    #     actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
    #     self.add_flow(datapath, 0, match, actions)

    def _build_packet_out(self, datapath, buffer_id, src_port, dst_port, data):
        """
            Build packet out object.
        """
        actions = []
        if dst_port:
            actions.append(datapath.ofproto_parser.OFPActionOutput(dst_port))

        msg_data = None
        if buffer_id == datapath.ofproto.OFP_NO_BUFFER:
            if data is None:
                return None
            msg_data = data

        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath, buffer_id=buffer_id,
            data=msg_data, in_port=src_port, actions=actions)
        return out

    def send_packet_out(self, datapath, buffer_id, src_port, dst_port, data):
        """
            Send packet out packet to assigned datapath.
        """
        out = self._build_packet_out(datapath, buffer_id,
                                     src_port, dst_port, data)
        if out:
            datapath.send_msg(out)

    ##############################################################################################################
    def get_port(self, dst_ip, hosts_switches):
        """
            Get access port if dst host.
            hosts_switches: {(sw,port) :(ip, )}
        """
        if hosts_switches:
            for key in hosts_switches:
                if dst_ip == hosts_switches[key]:
                    dst_port = key[1]
                    return dst_port
        return None

    ###############################################################################################################
    def get_port_pair_from_link(self, link_between_switches, src_dpid, dst_dpid):
        """
            Get port pair of link, so that controller can install flow entry.
        """
        if (src_dpid, dst_dpid) in link_between_switches:
            return link_between_switches[(src_dpid, dst_dpid)]
        else:
            self.logger.info("dpid:%s->dpid:%s is not in links" % (
                src_dpid, dst_dpid))
            return None

    def flood(self, msg):
        """
            Flood ARP packet to the access port
            which has no record of host.
        """
        datapath = msg.datapath
        ofproto = datapath.ofproto
        # parser = datapath.ofproto_parser
        #self.logger.info(self.awareness.access_ports)
        for dpid in self.awareness.access_ports:
            for port in self.awareness.access_ports[dpid]:
                if (dpid, port) not in self.awareness.hosts_switches:
                    datapath = self.datapaths[dpid]
                    out = self._build_packet_out(
                        datapath, ofproto.OFP_NO_BUFFER,
                        ofproto.OFPP_CONTROLLER, port, msg.data)
                    datapath.send_msg(out)

      #  self.logger.info("Flooding msg")

    def arp_forwarding(self, msg, src_ip, dst_ip):
        """ Send ARP packet to the destination host,
            if the dst host record is existed,
            else, flow it to the unknow access port.
        """
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        # self.logger.info(datapath.id)
        result = self.awareness.get_host_location(dst_ip)
       # self.logger.info(result)
        if result:  # host record in access table.
            datapath_dst, out_port = result[0], result[1]
            datapath = self.datapaths[datapath_dst]
            out = self._build_packet_out(datapath, ofproto.OFP_NO_BUFFER,
                                         ofproto.OFPP_CONTROLLER,
                                         out_port, msg.data)
            datapath.send_msg(out)
        # self.logger.info("Reply ARP to knew host")
        else:
            self.flood(msg)

    def get_path(self, src, dst):
        """
            Get shortest path from network awareness module.
        """
        if self.awareness.shortest_paths is not None:
            shortest_paths = self.awareness.shortest_paths
            if shortest_paths.get(src) is not None:
                try:
                    #self.logger.info(shortest_paths.get(src).get(dst)[0])
                    return shortest_paths.get(src).get(dst)[0]
                except Exception as e:
                    #self.logger.info(e)
                    pass
    # def get_k_paths(self,src,dst):
    #     return self.awareness.shortest_paths.get(src).get(dst)
    #
    def get_sw(self, dpid, in_port, src, dst):
        """
            Get pair of source and destination switches.
        """
        src_sw = dpid
        dst_sw = None
        # 找到源ip地址主机连接的交换机和端口
        # （dpid,port）-->(ip)
        src_location = self.awareness.get_host_location(src)
        if in_port in self.awareness.access_ports[dpid]:
            if (dpid, in_port) == src_location:
                src_sw = src_location[0]
            else:
                return None

        dst_location = self.awareness.get_host_location(dst)
        if dst_location:
            dst_sw = dst_location[0]
        if dst_sw is None:
            pass
            #self.logger.info("cannot find dst_sw")
        return src_sw, dst_sw

    '''
     self.install_flow(self.datapaths,
                                  self.awareness.link_between_switches,
                                  self.awareness.hosts_switches, path,
                                  flow_info, msg.buffer_id, msg.data)
                                  
    '''

    def install_flow(self, datapaths, link_between_switches, hosts_switches, path,
                     flow_info, buffer_id, data=None):
        '''
            Install flow entires for roundtrip: go and back.
            @parameter: path=[dpid1, dpid2...]
                        flow_info=(eth_type, src_ip, dst_ip, in_port)
        '''

        if path is None or len(path) == 0:
            self.logger.info("Path error!")
            return
        self.logger.info("在path{}上安装刘表".format(path))
        in_port = flow_info[3]
        first_dp = datapaths[path[0]]
        out_port = first_dp.ofproto.OFPP_LOCAL
        back_info = (flow_info[0], flow_info[2], flow_info[1])
        #    flow_info = (eth_type, ip_src, ip_dst, in_port)
        # inter_link
        if len(path) > 2:
            for i in range(1, len(path) - 1):
                port = self.get_port_pair_from_link(link_between_switches,
                                                    path[i - 1], path[i])
                port_next = self.get_port_pair_from_link(link_between_switches,
                                                         path[i], path[i + 1])
                if port and port_next:
                    src_port, dst_port = port[1], port_next[0]
                    datapath = datapaths[path[i]]
                    self.send_flow_mod(datapath, flow_info, src_port, dst_port)
                    self.send_flow_mod(datapath, back_info, dst_port, src_port)
                    self.logger.info("inter_link flow install to dp{}".format(datapath.id))
        if len(path) > 1:
            self.logger.info("len>1")
            # the last flow entry: tor -> host
            port_pair = self.get_port_pair_from_link(link_between_switches,
                                                     path[-2], path[-1])
            if port_pair is None:
                self.logger.info("Port is not found")
                return
            src_port = port_pair[1]

            dst_port = self.get_port(flow_info[2], hosts_switches)
            if dst_port is None:
                self.logger.info("Last port is not found.")
                return

            last_dp = datapaths[path[-1]]
            self.logger.info(" len > 1 flow install to dp{}".format(last_dp.id))
            self.send_flow_mod(last_dp, flow_info, src_port, dst_port)
            self.send_flow_mod(last_dp, back_info, dst_port, src_port)

            # the first flow entry
            port_pair = self.get_port_pair_from_link(link_between_switches,
                                                     path[0], path[1])
            if port_pair is None:
                self.logger.info("Port not found in first hop.")
                return
            out_port = port_pair[0]
            self.logger.info(" len >1 flow install to dp{}".format(first_dp.id))
            self.send_flow_mod(first_dp, flow_info, in_port, out_port)
            self.send_flow_mod(first_dp, back_info, out_port, in_port)
            self.send_packet_out(first_dp, buffer_id, in_port, out_port, data)

        # src and dst on the same datapath
        else:
            out_port = self.get_port(flow_info[2], hosts_switches)
            if out_port is None:
                self.logger.info("Out_port is None in same dp")
                return
            self.logger.info("inter_link flow install to dp{}".format(first_dp.id))
            self.send_flow_mod(first_dp, flow_info, in_port, out_port)
            self.send_flow_mod(first_dp, back_info, out_port, in_port)
            self.send_packet_out(first_dp, buffer_id, in_port, out_port, data)

    # def get_path_between_hosts(self,,ip_):
    def shortest_forwarding(self, msg, eth_type, ip_src, ip_dst, path=None):
        """
            To calculate shortest forwarding path and install them into datapaths.

        """
        # 将信息发送到控制器的switch
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        # 表示从交换机的哪个端口进入
        in_port = msg.match['in_port']
        if path is None:
            # self.logger.info("path is None")
            # self.logger.info(in_port)
            result = self.get_sw(datapath.id, in_port, ip_src, ip_dst)

            if result:
                #self.logger.info(result)
                src_sw, dst_sw = result[0], result[1]
                if dst_sw:
                    # Path has already calculated, just get it.
                    path = self.get_path(src_sw, dst_sw)
                    self.logger.info("[PATH]%s<-->%s: %s" % (ip_src, ip_dst, path))
                    flow_info = (eth_type, ip_src, ip_dst, in_port)
                    # install flow entries to datapath along side the path.
                    self.install_flow(self.datapaths,
                                      self.awareness.link_between_switches,
                                      self.awareness.hosts_switches, path,
                                      flow_info, msg.buffer_id, msg.data)
        else:
            #self.logger.info("[PATH]%s<-->%s: %s" % (ip_src, ip_dst, path))
            flow_info = (eth_type, ip_src, ip_dst, in_port)
            self.logger.info("install flow table {},{}".format(ip_src, ip_dst))
            self.install_flow(self.datapaths,
                              self.awareness.link_between_switches,
                              self.awareness.hosts_switches, path,
                              flow_info, msg.buffer_id, msg.data)

    # @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    #
    # def _packet_in_handler(self, ev):
    #     '''
    #         In packet_in handler, we need to learn hosts_switches by ARP.
    #         Therefore, the first packet from UNKOWN host MUST be ARP.
    #     '''
    #     msg = ev.msg
    #     datapath = msg.datapath
    #     in_port = msg.match['in_port']
    #     pkt = packet.Packet(msg.data)
    #     arp_pkt = pkt.get_protocol(arp.arp)
    #     ip_pkt = pkt.get_protocol(ipv4.ipv4)
    #     # self.logger.info("packet in")
    #
    #     if isinstance(arp_pkt, arp.arp):
    #         self.logger.info("ARP processing{}".format(datapath.id))
    #         self.arp_forwarding(msg, arp_pkt.src_ip, arp_pkt.dst_ip)
    #         self.awareness.register_host(datapath.id, pkt, in_port)
    #     elif isinstance(ip_pkt, ipv4.ipv4):
    #         self.logger.info("IPV4 processing")
    #         if len(pkt.get_protocols(ethernet.ethernet)):
    #             eth_type = pkt.get_protocols(ethernet.ethernet)[0].ethertype
    #             self.shortest_forwarding(msg, eth_type, ip_pkt.src, ip_pkt.dst)
    #
    # # def arp_handler(self,msg,arp_pkt):
    # #     self.arp_forwarding(msg,arp_pkt.src_ip,arp_pkt.dst_ip)


if __name__ == "__main__":
    import sys
    from ryu.cmd.manager import main

    sys.argv.append("--observe-links")
    sys.argv.append("--enable-debugger")
    sys.argv.append("forwarding")
    main()
