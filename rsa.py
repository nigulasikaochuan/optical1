# coding:utf-8
from ryu.base import app_manager
from ryu.ofproto import ofproto_v1_3
from mynetwork import Aware
from spec_resource import ResourceManageMent
from ryu.controller.handler import register_service
from forwarding import ShortestForwarding
from ryu.controller.handler import set_ev_cls
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller import ofp_event
from ryu.lib.packet import packet
from ryu.lib.packet import ipv4
from ryu.lib.packet import ethernet
from ryu.lib.packet import arp
import event
import random
import math
from ryu.ofproto import ofproto_v1_3_parser


class Rsa(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {"nettopo": Aware,
                 "resource": ResourceManageMent,
                 'forwarding': ShortestForwarding}

    sub_carrier_abililty = {'BPSK': 25, 'QPSK': 50, '8-QAM': 75, '16-QAM': 100}
    BandRequest = [100, 200, 300, 400]

    def __init__(self, *args, **kwargs):
        super(Rsa, self).__init__(*args, **kwargs)

        self.name = "rsa"
        self.net_topo = kwargs['nettopo']
        self.resource = kwargs['resource']
        self.forwarding = kwargs['forwarding']
        self.datapaths = self.forwarding.datapaths
        self.modulation_format = None
        self.slot_used = {}

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

    '''
    流程：ping报文进入，找到起始地点，确定调制格式------>2.最短路径选路径----->3.在这条路径上分配频谱，并修改权重------->4.没有合适的频谱就阻塞
    '''

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        arp_pkt = pkt.get_protocol(arp.arp)
        ip_pkt = pkt.get_protocol(ipv4.ipv4)

        if isinstance(arp_pkt, arp.arp):
            # self.net_topo.register_host(datapath.id, pkt, in_port)
            # self.forwarding.arp_handler(msg,arp_pkt)
            self.net_topo.register_host(datapath.id, pkt, in_port)
            self.forwarding.arp_forwarding(msg, arp_pkt.src_ip, arp_pkt.dst_ip)
            # self.logger.info(arp_pkt)
            # self.logger.info(self.net_topo.hosts_switches)
            # self.logger.info("ARP processing{}".format(datapath.id))
        if isinstance(ip_pkt, ipv4.ipv4):
            # self.logger.info("ip processing")
            # self.logger.info(ip_pkt)
            self.logger.info(
                "jiaohuanji{}send packet in message,send the data from {} to {} ".format(msg.datapath.id, ip_pkt.src,
                                                                                         ip_pkt.dst))
            src_ip = ip_pkt.src
            dst_ip = ip_pkt.dst
            try:
                src_location = self.net_topo.get_host_location(src_ip)[0]
                dst_location = self.net_topo.get_host_location(dst_ip)[0]
            except Exception as e:
                pass
            # src_dpid = None
            # dst_dpid = None
            distance = 0
            # distance = self.get_distance()
            in_port = msg.match['in_port']
            # self.logger.info("交换机{},传递的inport{}".format(datapath.id,in_port))
            # self.logger.info("交换机与主机的链接为{} {}".format(self.net_topo.access_ports,self.net_topo.hosts_switches))
            self.logger.info("datapath id is{}".format(datapath.id))
            res = self.forwarding.get_sw(datapath.id, in_port, src_ip, dst_ip)
            # self.logger.info(res)
            if res:
                src_switch, dst_switch = res[0], res[1]
                if dst_switch:
                    path = self.forwarding.get_path(src_switch, dst_switch)
                    if path:
                        if path[0] == src_location and path[-1] == dst_location:
                            for index in range(len(path) - 1):
                                src_dpid = path[index]
                                dst_dpid = path[index + 1]
                                # self.logger.info('{}{}'.format(src_dpid,dst_dpid))
                                for key in self.resource.distance_between_nodes:
                                    # self.logger.info(key)
                                    if key == (src_dpid, dst_dpid) or key == (dst_dpid, src_dpid):
                                        distance += self.resource.distance_between_nodes[key]
                                        break
                                        # self.logger.info("---------------------------{}".format(distance))
                        # # self.logger.info(elif len(path)==1:
                        else:
                            self.logger.info("else")
                            # self.logger.info("path is {}".format(path))
                            try:
                                path = self.slot_used.get((src_location, dst_location))[0]
                            except Exception as e:
                                print('--------------------------------------------')
                                print(self.slot_used)
                                print("----------------------------------------------")
                            for index, value in enumerate(path):
                                if path[index] == datapath.id:
                                    path = path[index:]
                                    break
                            if len(pkt.get_protocols(ethernet.ethernet)):
                                eth_type = pkt.get_protocols(ethernet.ethernet)[0].ethertype
                                self.forwarding.shortest_forwarding(ev.msg, eth_type, src_ip, dst_ip, path)
                                return
                    else:
                        self.logger.info("no path")
                        return

            else:
                return
            if distance != 0:

                if distance >= 3000:
                    self.modulation_format = 'BPSK'
                elif distance >= 1500 and distance < 3000:
                    self.modulation_format = 'QPSK'
                elif distance >= 700 and distance < 1500:
                    self.modulation_format = '8-QAM'
                else:
                    self.modulation_format = "16-QAM"

                # self.logger.info('distance {}, modulation format{}'.format(distance,self.modulation_format))
                band_width_request = random.choice(Rsa.BandRequest)
                required_slots = band_width_request / Rsa.sub_carrier_abililty[self.modulation_format]
                required_slots = math.ceil(required_slots)
                # self.logger.info(
                #     "band_width_request is {} and the slot need to be allocated is {}".format(band_width_request,
                #                                                                               required_slots))
                remain_slot = self.send_request(event.EventRequestSpectrumRemain(dst='link_resource')).rsc
                # self.logger.info(remain_slot)
                assigment_res = self.do_assignment(band_width_request, required_slots, remain_slot, path)
                # assigment_res = True
                if assigment_res[0]:
                    if (path[0], path[-1]) not in self.slot_used:
                        self.slot_used.setdefault((path[0], path[-1]), [])
                        self.slot_used[(path[0], path[-1])].append(path)
                    self.logger.info(assigment_res[0])
                    if (path[0], path[-1]) in self.slot_used:
                        if self.slot_used[(path[0], path[-1])]:
                            if len(self.slot_used[(path[0], path[-1])]) == 1:
                                # self.logger.info("registed slot used")
                                self.slot_used[(path[0], path[-1])].append(assigment_res[1])
                            # self.logger.info("after registation{}".format(self.slot_used[(path[0], path[-1])]))
                    # self.logger.info(self.slot_used)
                    #  self.logger.info("assigment_res:{}".format(assigment_res[1]))
                    # self.logger.info("IPV4 processing,slot allocated is {}".format(assigment_res[1]))
                    if len(pkt.get_protocols(ethernet.ethernet)):
                        eth_type = pkt.get_protocols(ethernet.ethernet)[0].ethertype
                        # self.logger.info("id{},,chuan di de path{}".format(datapath.id, path))
                        self.forwarding.shortest_forwarding(ev.msg, eth_type, src_ip, dst_ip, path)
                    # src_dpid = None
                    # dst_dpid = None
                else:
                    self.logger.info(assigment_res[0])
                    self.logger.info(path)
                    self.logger.info("assignment failed")

    def do_assignment(self, band_width_request, required_slots, remain_slot, path):
        # self.logger.info("do assinging")
        slot_between_src_dst = {}
        can_be_allowed = set()
        # for循环结束后，就得到从源节点到目的节点路径上所有残留的slot
        for index in range(len(path) - 1):
            src_dpid = path[index]
            dst_dpid = path[index + 1]

            for key in remain_slot:
                if (src_dpid, dst_dpid) == key or (dst_dpid, src_dpid) == key:
                    slot_between_src_dst[(src_dpid, dst_dpid)] = remain_slot[key]

        # 循环结束后的集合中为每条链路残留的相同位置上的频谱槽
        for s_d in slot_between_src_dst:
            if len(slot_between_src_dst[s_d]) < required_slots:
                self.logger.info("no enough spectrum slots")
                return (False,)
            if len(can_be_allowed) == 0:
                if not isinstance(slot_between_src_dst[s_d], list):
                    slot_between_src_dst[s_d] = list(slot_between_src_dst[s_d])
                can_be_allowed = set(slot_between_src_dst[s_d])
            else:
                can_be_allowed = set(slot_between_src_dst[s_d]) & can_be_allowed

        if len(can_be_allowed) < required_slots:
            # self.logger.info("no enough spectrum slots")
            return (False,)
        else:
            can_be_allowed = sorted(can_be_allowed)

            index = 0
            res = set()
            while index < len(can_be_allowed) - 1:

                if len(res) >= required_slots:
                    break
                if can_be_allowed[index + 1] - can_be_allowed[index] == 1:
                    res.add(can_be_allowed[index])
                    res.add(can_be_allowed[index + 1])
                else:
                    res = set()
                index += 1

            if len(res) >= required_slots:
                if required_slots == 1:
                    for index in range(len(path) - 1):
                        src_dpid = path[index]
                        dst_dpid = path[index + 1]
                        # self.logger.info('{}{}'.format(src_dpid,dst_dpid))
                        for key in self.resource.remainSlots:
                            if key == (src_dpid, dst_dpid) or key == (dst_dpid, src_dpid):
                                self.resource.remainSlots[key].remove(sorted(res)[0])
                    # self.logger.info('---------------------------{}'.format(distance))
                    return True, sorted(res)[0]

                for index in range(len(path) - 1):
                    src_dpid = path[index]
                    dst_dpid = path[index + 1]
                    # self.logger.info('{}{}'.format(src_dpid,dst_dpid))
                    for key in self.resource.remainSlots:
                        # self.logger.info("youmeiyoujinru{}".format(key))
                        if key == (src_dpid, dst_dpid) or key == (dst_dpid, src_dpid):
                            for i in sorted(res):
                                self.resource.remainSlots[key].remove(i)
                            # self.logger.info("shandiaodekey{}".format(key))
                            # self.logger.info("shanchuhou key{} {}".format(key,self.resource.remainSlots))
                            break

                    # self.logger.info('---------------------------{}'.format(distance))

                self.resource.calc_weight()
                self.resource.set_weight_of_link()
                return True, sorted(res)
            else:
                self.logger.info("no continued slots for request")
                return (False,)

        return (False,)

    #
    @set_ev_cls(ofp_event.EventOFPFlowRemoved, MAIN_DISPATCHER)
    def flow_removed_handler(self, ev):

        msg = ev.msg
        datapath = msg.datapath
        # ofproto = datapath.ofproto
        # parser = datapath.ofproto_parser
        # match = msg.match
        # self.logger.info("*"*50)
        # self.logger.info("resource before give back:{}".format(self.resource.remainSlots))
        # self.logger.info(match)

        src_in_match = msg.match["ipv4_src"]
        dst_in_match = msg.match["ipv4_dst"]
        src_dpid = self.net_topo.get_host_location(src_in_match)[0]
        dst_dpid = self.net_topo.get_host_location(dst_in_match)[0]
        # if key in self.slot_used:
        for key in self.slot_used:
            # self.logger.info("删除中的key是{}".format(key))
            # self.logger.info("src{},dst{}".format(src_dpid, dst_dpid))
            if key == (src_dpid, dst_dpid):
                try:
                    path, src_to_returned = self.slot_used[key]
                # sorces_to_returned = self.slot_used[key][1:]
                except Exception as e:
                    # import os
                    # # os.system("sudo touch /mnt/sdn1/optical1 name{}jilu{}.txt".format(key[0],key[1]))
                    # for i in range(13):
                    #     os.system('sudo ovs-ofctl -O openflow13 dump-flows s{} > /mnt/sdn1/optical1/name{}{}jilu{}.txt'.format(i,i, key[0],key[1]))

                    self.logger.info('*' * 80)
                    self.logger.info(e)
                    self.logger.info("{}  {}".format(key, self.slot_used[key]))
                    # self.logger.info(self.slot_used[key])
                    self.logger.info("*" * 80)
                    # print(self.slot_used)

                    path = None
                    src_to_returned = None

                del (self.slot_used[key])
                break
        else:
            return
            # self.logger.info("error----------------")
        if path is not None:
            for index in range(len(path) - 1):
                for key in self.resource.remainSlots:
                    if key == (path[index], path[index + 1]) or key == (path[index + 1], path[index]):
                        # self.logger.info("guihuandaode key{}".format(key))
                        if not isinstance(src_to_returned, list):
                            src_to_returned = [src_to_returned]
                            # self.logger.info("resource before give back:{}".format(self.resource.remainSlots))
                        self.resource.remainSlots[key].extend(src_to_returned)
                        self.resource.remainSlots[key].sort()
                        break

        # for key in self.resource.remainSlots:
        #     # for src_dpid,dst_dpid in path:
        #     if key == (src_dpid, dst_dpid) or key == (dst_dpid, src_dpid):
        #         for src_to_returned in sorces_to_returned:
        #             if not isinstance(src_to_returned, list):
        #                 src_to_returned = [src_to_returned]
        #             #self.logger.info("resource before give back:{}".format(self.resource.remainSlots))
        #             self.resource.remainSlots[key].extend(src_to_returned)
        #             self.resource.remainSlots[key].sort()
        #
        #             #self.logger.info("resource after give back:{}".format(self.resource.remainSlots))
        #             break
        # self.logger.info("resource after give back:{}".format(self.resource.remainSlots))
        # 重新计算权重
        # 重新设置图
        self.resource.calc_weight()
        self.resource.set_weight_of_link()
        for key in self.resource.remainSlots:
            self.logger.info(len(self.resource.remainSlots[key]))
        #     # # if len(self.resource.remainSlots[key]) < 128:
        #     # #     self.logger.info(key)
        #     # #    #self.logger.info(self.resource.remainSlots[key])
        #     # #     print()
        self.logger.info(self.slot_used)