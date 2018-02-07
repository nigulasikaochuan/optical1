from ryu.base import app_manager
from api import send_source_query
# import event
from ryu.base.app_manager import _lookup_service_brick_by_mod_name
from ryu.controller.handler import set_ev_cls
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER
from spec_resource import ResourceManageMent
import event


class my(app_manager.RyuApp):
    #  _CONTEXTS = {'res':ResourceManageMent}
    def __init__(self, *args, **kwargs):
        super(my, self).__init__(*args, **kwargs)
        self.name = "test"
        # self.res = kwargs['res']

    def test_send_request(self):
        source = send_source_query(self)
        self.logger.info(source)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def test12(self, ev):
        self.test_send_request()
