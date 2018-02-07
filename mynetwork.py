# coding:utf-8
from ryu.base import app_manager
from ryu.controller.handler import set_ev_cls
from ryu.lib import hub
from ryu.topology import api
from ryu.topology import event
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER,CONFIG_DISPATCHER
from ryu.lib.packet import packet
from ryu.lib.packet import arp
from ryu.ofproto import ofproto_v1_3
import networkx
Event_to_listened_by_getTopo = [event.EventLinkAdd, event.EventLinkDelete, event.EventPortAdd,
                                event.EventPortDelete, event.EventPortModify, event.EventSwitchEnter, event.EventSwitchLeave]
from ryu.ofproto import ofproto_v1_3_parser
#这个用来选路
class Aware(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(Aware, self).__init__(*args, **kwargs)
        self.name = "awareness"
        self.switches = []  # 存储所有的交换机
        self.port_of_switches = {}
        # (源交换机的dpid，目的交换机的dpid)--->(src的端口号，dst的端口号)
        self.link_between_switches = {}
        self.hosts_switches = {}  # 存储host与交换机之间的链路（dpid,port_no）----->host_ip
        self.find = self.__find
        self.shortest_paths = {}  # shortest_paths[src][dst] 所有的k条路径 从src-dst
        self.graph = networkx.DiGraph()


        hub.spawn(self.__find)
        self.access_ports = {}
    def __find(self):
        i = 1
        while True:
            # self.show()
            if i == 1:
                self.getTopo(None)
                i = 0
            i = i+1
            hub.sleep(2)
    #将这个函数注册为事件的处理函数
    #在初始化的时候，会在事件提供app的observers对象中注册该app的实例
    #当事件提供者调用send_event_to_observers方法的时候，会把事件放入每个被注册为observer的app的事件队列中
    #每个app都是一个线程，可以看做同时运行
    #app的事件循环函数不断从事件队列中取出事件
    #根据取出的事件，app会检测自己的handler属性，找到对应事件的handler，即被@set_ev_cls修饰的函数，去处理
    #相应的事件
    @set_ev_cls(Event_to_listened_by_getTopo)
    def getTopo(self,ev):
        # 得到所有的交换机对象
        # Switch对象
        # 属性：  self.dp = dp
        #       self.ports = [Port实例]，有port_no,dpid
        #self.logger.info("update")
        self.switches = api.get_all_switch(self)

        # AllLink
        AllLink = api.get_all_link(self)
        self.creat_link_between_switches(AllLink)
        self.creat_port_of_switches(self.switches)
        #self.logger.info(self.port_of_switches)
        self.creat_access_ports()
        #self.logger.info(len(self.link_between_switches))
        #self.creat_graph()
       # self.creat_shortest_paths(3)
       #  self.logger.info("accc:{}".format(self.access_ports))
       #  self.logger.info("-------------------------")
       #  self.logger.info(self.port_of_switches)


    def creat_access_ports(self):
        for sw in self.switches:
            for key in self.link_between_switches:
                if sw.dp.id == key[0]:
                    self.access_ports[sw.dp.id] = self.access_ports[sw.dp.id]-{self.link_between_switches[key][0]}

    def creat_link_between_switches(self, AllLink):
        #self.logger.info("creat")
        #self.link_between_switches = {}
        for Link in AllLink:
            src_dpid = Link.src.dpid
            dst_dpid = Link.dst.dpid
            self.link_between_switches[(src_dpid, dst_dpid)] = (Link.src.port_no, Link.dst.port_no)
            #self.logger.info("link between{} and {}".format(Link.src.dpid, Link.dst.dpid))

    def creat_port_of_switches(self, switches):
        # self.logger.info(switches)
        for switch in self.switches:
            self.port_of_switches.setdefault(switch.dp.id,set())

            for port in switch.ports:
                self.port_of_switches[switch.dp.id].add(port.port_no)

        for sw_dpid in self.port_of_switches:
            self.access_ports[sw_dpid] = self.port_of_switches[sw_dpid]

    def creat_graph(self,weights=None):
        if weights is None:
            self.logger.info("weight none")
            return

        else:
            for src_switch in self.switches:
                for dst_switch in self.switches:
                    if src_switch.dp.id == dst_switch.dp.id:
                        self.graph.add_edge(src_switch.dp.id,dst_switch.dp.id,weight=0)

                    else:

                        if (src_switch.dp.id, dst_switch.dp.id) in self.link_between_switches:
                            if (src_switch.dp.id,dst_switch.dp.id) in weights:
                                weight = weights[(src_switch.dp.id,dst_switch.dp.id)]
                            elif(dst_switch.dp.id,src_switch.dp.id) in weights:
                                    weight = weights[(dst_switch.dp.id,src_switch.dp.id)]
                            else:
                                self.logger.info("return")
                                return
                            self.graph.add_edge(src_switch.dp.id, dst_switch.dp.id, weight=weight)

    def creat_shortest_paths(self, k):
        for src in self.graph.nodes():
            self.shortest_paths.setdefault(src, {src: [[src] for i in range(k)]})
            for dst in self.graph.nodes():
                if src==dst:
                    continue
                else:
                    self.shortest_paths[src].setdefault(dst,[])
                    self.shortest_paths[src][dst] = self.creat_k_paths(src,dst,k)

        # for dst_switch in self.switches:
        #     for src_switch_dpid in self.shortest_paths:
        #         if dst_switch.dp.id == src_switch_dpid:
        #             continue
        #         else:
        #             self.shortest_paths[src_switch_dpid][dst_switch.dp.id] = self.creat_k_paths(src_switch_dpid, dst_switch.dp.id, k)
        # #self.logger.info(self.shortest_paths)

    def creat_k_paths(self, src_switch_dp, dst_switch_dp, k, weight='weight'):
        import copy
        allpaths = networkx.shortest_simple_paths(copy.deepcopy(self.graph), src_switch_dp, dst_switch_dp, weight=weight)
        kpaths = []
        try:
            for path in allpaths:
                kpaths.append(path)
                k = k-1
                if k == 0:
                    break
        except Exception as e:
            #print(e)
            pass
        return kpaths

    # @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    # def _packet_in_handler(self, ev):
    #     msg = ev.msg
    #     datapath = msg.datapath
    #     dpid = datapath.id
    #     inport = msg.match['in_port']  # port_no
    #     data = msg.data
    #
    #     pkt = packet.Packet(data)
    #     arp_ = pkt.get_protocol(arp.arp)
    #     if arp_:
    #
    #         self.register_host(dpid, pkt, inport)

    def register_host(self, dpid, pkt, inport):

        arp_ = pkt.get_protocol(arp.arp)
        ip = arp_.src_ip
        # self.hosts_switches[(dpid, inport)] = src_ip
        if inport in self.access_ports[dpid]:
            if (dpid, inport) in self.hosts_switches:
                if self.hosts_switches[(dpid, inport)] == ip:
                    return
                else:
                    self.hosts_switches[(dpid, inport)] = ip
                    return
            else:
                self.hosts_switches.setdefault((dpid, inport), None)
                self.hosts_switches[(dpid, inport)] = ip
                return
        self.logger.info(self.hosts_switches)

    def get_host_location(self,ip):
        for (dpid,inport),ip_ in self.hosts_switches.items():
            if ip == ip_:
                #self.logger.info("return")
                return (dpid,inport)
        #self.logger.info("not find, please wait for more time")

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


if __name__=="__main__":
    import sys
    from ryu.cmd import manager
    sys.argv.append("--enable-debugger")
    sys.argv.append("--verbose")
    sys.argv.append('mynetwork')
    manager.main()
