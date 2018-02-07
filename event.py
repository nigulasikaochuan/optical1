from ryu.controller import handler
from ryu.controller import event


class EventRequestSpectrumRemain(event.EventRequestBase):

    def __init__(self,dst):
        super(EventRequestSpectrumRemain, self).__init__()
        self.dst = dst


    def __str__(self):
        return 'EventRequestSpectrumRemain<src=%s, dpid=%s>' % \
               (self.src, self.dpid)


class EventReplySpectrumRemain(event.EventReplyBase):

    def __init__(self, dst, rsc):
        super(EventReplySpectrumRemain, self).__init__(dst)
        self.rsc = rsc

    def __str__(self):
        return 'EventLinkReply<spectrum_resouce_remained{}>'.format(self.rsc)


handler.register_service('spec_resource')
