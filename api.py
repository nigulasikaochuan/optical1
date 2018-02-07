import event
from ryu.base import app_manager


def send_source_query(app):
    reply = app.send_request(event.EventRequestSpectrumRemain('link_resource'))
    return reply.rsc


app_manager.require_app('spec_resource', api_style=True)
