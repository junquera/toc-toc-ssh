import uuid
import socket
import threading
from proc_worker import *
from proc_worker import bypass
from ttp import TocTocPortsWorker

import logging

log = logging.getLogger(__name__)

class KnockablePort():

    def __init__(self, socket, next_port):
        self._socket = socket
        self._next_port = next_port

    def get_next_port(self):
        return self._next_port

    def get_socket(self):
        return self._socket


class PortManager():

    def __init__(self):
        self._sockets = []
        self._threads = []

    def wait_and_listen(self, kp):

        s = kp.get_socket()
        p = s.getsockname()
        next_port = kp.get_next_port()

        # TODO Ver por qué no termina el hilo...
        while 1:
            try:
                sock, addr = s.accept()
                self.notify_connection(p, addr, next_port)
                self.handle_connection(sock, addr)
            except Exception as e:
                log.debug("Thread del socket %s" % str(p))
                break

    def handle_connection(self, sock, addr):
        sock.close()

    def notify_first_port(self, p):
        log.debug("First port: %d" % p)

    def notify_connection(self, p, addr, next_port):
        if next_port:
            log.debug("New connection to %d from %s, next step %d" %(p[1], addr[0], next_port))
        else:
            log.debug("New connection to %d from %s, open the result!" % (p[1], addr[0]))

    def notify_error_opening_socket(self):
        pass

    def open_socket(self, port):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('0.0.0.0', port))
            s.listen(5)
            return s
        except socket.error as e:
            if e.errno == 98:
                log.critical("El puerto %d ya está siendo utilizado por otro proceso" % port)
        except Exception as e:
            self.notify_error_opening_socket()

    def open(self, port_list):

        n = port_list.next()

        if n:
            self.notify_first_port(n)

        while n:
            port = n
            n = port_list.next()

            log.info("Opening %d" % port)

            s = self.open_socket(port)
            if s:
                kp = KnockablePort(s, n)
                self._sockets.append(kp)
                t = threading.Thread(target=self.wait_and_listen, args=(kp,))
                self._threads.append(t)
                t.start()
            else:
                self.close()
                break

    def notify_socket_closed(self, s_addr):
        log.debug("Closing socket on port %d" % (s_addr[1]))

    def close_socket(self, s):
        self.notify_socket_closed(s.getsockname())
        try:
            s.close()
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(s.getsockname())
            log.debug("Closing %d" % s.getsockname()[1])
        except Exception as e:
            pass

    def close_thread(self, t):
        try:
            t.exit()
        except:
            pass

    def close_threads(self):
        while len(self._threads):
            try:
                t = self._threads.pop()
                self.close_thread(t)
            except:
                pass

    def close_sockets(self):
        while len(self._sockets):
            try:
                kp = self._sockets.pop()
                s = kp.get_socket()
                self.close_socket(s)
            except:
                pass

    def close(self):
        # TODO Close firewall
        self.close_sockets()
        self.close_threads()

    def reset(self):
        self.close()
        self.open()


# https://eli.thegreenplace.net/2011/12/27/python-threads-communication-and-stopping
# http://www.bogotobogo.com/python/Multithread/python_multithreading_Event_Objects_between_Threads.php
class PortManagerWorker(ProcWorker):

    NEW_CONNECTION = uuid.uuid4().bytes
    CLOSING_SOCKET = uuid.uuid4().bytes
    FIRST_PORT = uuid.uuid4().bytes
    LAST_PORT = uuid.uuid4().bytes

    def __init__(self, i_q, o_q, pm=PortManager()):
        super(PortManagerWorker, self).__init__(i_q, o_q)

        self._pm = pm

        self._pm.notify_socket_closed = bypass(self._pm.notify_socket_closed, self.notify_socket_closed)
        self._pm.notify_connection = bypass(self._pm.notify_connection, self.notify_connection)
        self._pm.notify_first_port = bypass(self._pm.notify_first_port, self.notify_first_port)
        self._pm.notify_error_opening_socket = bypass(self._pm.notify_error_opening_socket, self.notify_error_opening_socket)

    def notify_error_opening_socket(self):
        print("Bypass error opening")
        self._o.put(Event(ProcWorker.END, None))

    def notify_first_port(self, p):
        print("Bypass first port")
        self._o.put(Event(self.FIRST_PORT, {'port': p}))

    def notify_socket_closed(self, s_addr):
        self._o.put(Event(self.CLOSING_SOCKET, {'port': s_addr[1]}))

    def notify_connection(self, p, addr, next_port):
        if next_port:
            self._o.put(Event(self.NEW_CONNECTION, {'port': p[1], 'address': addr[0], 'next': next_port}))
        else:
            self._o.put(Event(self.LAST_PORT, {'port': p[1], 'address': addr[0]}))

    def process_evt(self, evt):
        super(PortManagerWorker, self).process_evt(evt)

        if evt.get_id() == ProcWorker.END:
            self._pm.close()

        if evt.get_id() == TocTocPortsWorker.NEW_SLOT:
            self._pm.close()
            self._pm.open(evt.get_value()['port_list'])
