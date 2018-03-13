import threading
import uuid
import logging

log = logging.getLogger(__name__)

def bypass(fa, fb):

    def mix(*args, **kwargs):
        fa(*args, **kwargs)
        fb(*args, **kwargs)

    return mix

class ProcWorker(threading.Thread):

    NONE = -1
    END = uuid.uuid4().bytes

    stay_running = True

    def __init__(self, i_q, o_q):
        super(ProcWorker, self).__init__()
        self._i = i_q
        self._o = o_q
        self.start()

    def run(self):
        while self.stay_running:
            evt = self._i.get(True)
            if evt:
                self.process_evt(evt)

    def process_evt(self, evt):
        if evt.get_id() == self.END:
            log.debug("Received close signal")
            self.stay_running = False
            self._i.put(None)

        pass


class Broker(ProcWorker):

    _client_qs = []

    def __init__(self, i_q, o_q):
        super(Broker, self).__init__(i_q, o_q)
        self._client_qs.append(o_q)

    def add_client(self, client_q):
        self._client_qs.append(client_q)

    def process_evt(self, evt):
        super(Broker, self).process_evt(evt)

        for q in self._client_qs:
            q.put(evt)


class Event():

    def __init__(self, id, value):
        self._id = id
        self._value = value

    def get_value(self):
        return self._value

    def get_id(self):
        return self._id

    def __str__(self):
        return "EVENT %s - %s" % (self._id, self._value )