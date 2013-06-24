#!/bin/env python
import sys
import os
import socket
import SocketServer
import threading
import Queue
import select
import re
import time
import getopt
import json
import signal


class App(object):
    '''
    For config and info purposes'
    '''
    debug= False
    ip= '127.0.0.1'
    port = 8080
    isclog = '/var/log/dhcpd.log'
    logfile = '/var/log/isc_stats.log'
    daemon = False
    queue = Queue.Queue()
    exit = threading.Event()
    pid = 0


    stats = {
        'discover': 0,
        'offer': 0,
        'request': 0,
        'ack': 0,
        'nak': 0
    }

    @staticmethod
    def usage():
        '''
        Prints usage
        '''
        print 'Usage: %s [-a address] [-p port] [-f file] [-l file] [-b] [-d] [-h]' % os.path.basename(__file__)
        print '\t-a or --address, ip address to listen on (default 127.0.0.1)'
        print '\t-p or --port, tcp port to listen on (default 8080)'
        print '\t-f or --file, isc log  location (default /var/log/dhcpd.log)'
        print '\t-l or --log, log location (default /var/log/isc_stats.log)'
        print '\t-b or --background, run in background (default foreground)'
        print '\t-d or --debug, print debug messages'
        print '\t-h or --help, prints this help message'
        sys.exit(0)

    @staticmethod
    def print_stats():
        '''
        Prints statistics dict
        '''
        print str(App.stats) + '\n'

    @staticmethod
    def get_stats():
        '''
        Returns statistics dict
        '''
        return str(App.stats) + '\n'

    @staticmethod
    def get_json():
        '''
        Returns statistics in JSON format
        '''
        return json.dumps(App.stats, indent=4) + '\n'

    @staticmethod
    def termhandler(number, stack):
        Log.info("Shutting due to signal %d" % number)
        App.server.shutdown()
        App.exit.set()

    @staticmethod
    def daemonize():
        '''
        Double double fork and std in/out/err close
        '''
        Log.debug('[mainThread] Fork #1')
        os.fork() and sys.exit(0)

        os.chdir('/')
        os.umask(022)
        os.setsid()

        Log.debug('[mainThread] Fork #2')
        os.fork() and sys.exit(0)

        App.pid = os.getpid()

        Log.debug('[mainThread] Opening log file %s' % App.logfile)
        not os.access(App.logfile, os.W_OK) and Log.fatal('Unable to open %s for writing' % App.logfile)
        
        Log.info('Running as %d pid' % App.pid)
        Log.debug('[mainThread] Closing descriptors')
        for i in range(3): os.close(i)

        sys.stdout = open(App.logfile, 'a')
        sys.stderr = open(App.logfile, 'a')
        signal.signal(signal.SIGTERM, App.termhandler)


class Log(object):
    '''
    Logging class for convinence
    '''
    @staticmethod
    def fatal(msg):
        
        sys.stderr.write('FATAL: %s\n' % msg.strip())
        sys.exit(1)

    @staticmethod
    def info(msg):
        sys.stdout.write('INFO: %s\n' % msg.strip())
        sys.stdout.flush()

    @staticmethod
    def err(msg):
        sys.stderr.write('ERROR: %s\n' %msg.strip())
        sys.stderr.flush()


    @staticmethod
    def debug(msg):
        if App.debug:
            sys.stderr.write('DEBUG: %s\n' %msg.strip())
            sys.stderr.flush()


class StatsHandler(SocketServer.StreamRequestHandler):
    '''
    Instantiated for every HTTP request passed to server
    '''
    
    http = {
        'response': 'HTTP/1.0 200 OK',
        'headers': {
            'Content-Type': 'text/plain',
            'Content-Length': ''

        },
        'content': ''
    }

    def handle(self):
        '''
        Build response, headers and data
        '''

        Log.debug('[serverThread] Handling connection %s on port %d' % self.client_address)
        http = StatsHandler.http.copy()
        content = App.get_json()
        http['content'] = content
        http['headers']['Content-Length'] = str(len(content))

        payload = http['response'] + '\r\n'

        for k,v in http['headers'].items():
            payload += '%s: %s\r\n' % (k,v)
        payload += '\r\n'

        payload += http['content']

        self.wfile.write(payload)


class StatsServer(SocketServer.ThreadingTCPServer):
    '''
    Reporting stats via HTTP requests.
    Responses are returned in json format.
    Instatiates StatsHandler for every GET request.
    '''

    allow_reuse_address = True

    def shutdown(self):

        Log.debug('[serverThread] Thread exiting on demand')
        SocketServer.ThreadingTCPServer.shutdown(self)
        return


class Filehandle(object):
    '''
    Convinence class for our log filehandle
    '''
    def __init__(self, path):

        self.path = path
        self.inode = 0L
        self.filehandle = None

    def open(self):

        self.filehandle = open(self.path)
        self.inode = self.get_inode()

    def close(self):

        self.filehandle.close()
        self.inode = 0

    def reopen(self):

        self.close()
        self.open()

    def pos_start(self):

        self.filehandle.seek(0,0)

    def pos_end(self):

        self.filehandle.seek(0,2)
        

    def get_inode(self):

        return os.stat(self.path).st_ino

    def get_lines(self, count=10):
        '''
        Returns count lines, empty list or lines parsed up until we hit EOF
        '''
        
        lines = []

        while len(lines) < count:

            line = self.filehandle.readline().strip()

            # on eof we return the lines that we've read so far
            if not line:
                return lines

            lines.append(line)

        return lines

        
class Line(object):
    '''
    Convinince class for checking what kind of message are we seeing
    '''
    @staticmethod
    def discover(line):

        return 'DHCPDISCOVER' in line

    @staticmethod
    def offer(line):

        return 'DHCPOFFER' in line

    @staticmethod
    def request(line):

        return 'DHCPREQUEST' in line

    @staticmethod
    def ack(line):
        
        return 'DHCPACK' in line

    @staticmethod
    def nak(line):

        return 'DHCPNAK' in line
    

class ParserThread(threading.Thread):
    '''
    This thread waits for queue items,
    calls static method in Line class
    and updates statistics in App.stats
    '''

    def __init__(self, queue, name, exit):

        threading.Thread.__init__(self, name=name)
        self.name = name
        self.queue = queue
        self.exit = exit
        self.item = None

    def run(self):

        while True:

            if self.exit.is_set():
                Log.debug('[parserThread] Thread exiting on demand')
                break

            Log.debug('[parserThread] Waiting for queue data...')
            self.item = None
            self.item = self.queue.get()

            for line in self.item:

                if Line.discover(line):
                    App.stats['discover'] += 1
                elif Line.offer(line):
                    App.stats['discover'] += 1
                elif Line.request(line):
                    App.stats['request'] += 1
                elif Line.ack(line):
                    App.stats['ack'] += 1
                elif Line.nak(line):
                    App.stats['nak'] += 1

            self.queue.task_done()
            Log.debug('[parserThread] Stats dict: %s' % App.get_stats())


# ------------------------#
# Program run starts here #
# ------------------------#

# arg: parse
try:
    App.options = getopt.getopt(sys.argv[1:], 'a:p:f:l:bdh',
    longopts=['address=', 'port=', 'file=', 'log=', 'background', 'debug', 'help'])
except getopt.GetoptError:
    App.usage()

# arg: check
for option in App.options[0]:

    (opt, val) = option
    if opt in ['-a', '--address']: App.ip = val
    elif opt in ['-p', '--port']: App.port = int(val)
    elif opt in ['-f', '--file']: App.isclog = val
    elif opt in ['-l', '--log']: App.logfile = val
    elif opt in ['-b', '--background']: App.daemon = True
    elif opt in ['-d', '--debug']: App.debug = True
    elif opt in ['-h', '--help']: App.usage()

# app: daemon?
App.daemon and App.daemonize()

# socket: setup
Log.debug('[mainThread] Instantiating server...')
App.addr = (App.ip, App.port)
App.server = StatsServer(App.addr, StatsHandler)

# thread: server
Log.debug('[mainThread] Instantiating Server thread...')
thread_server = threading.Thread(target=App.server.serve_forever)
thread_server.daemon = True
thread_server.start()

# thread: parser
Log.debug('[mainThread] Instantiating Parser thread...')
App.parser = ParserThread(App.queue, "parserThread", App.exit)
App.parser.daemon = True
App.parser.start()

# filehandle: setup
Log.debug('[mainThread] Opening logfile %s' % App.isclog)
App.fh = Filehandle(App.isclog)

try:
    App.fh.open()
except IOError, e:
    Log.fatal('Opening %s failed: %s' % (App.isclog, e[1]))

App.fh.pos_end()

# app: notify user that we're running
Log.info('Monitoring file %s with inode of %d' % (App.isclog, App.fh.inode))
Log.info("Listening on %s port %d" % App.addr)

# main
try:

    while True:

        if App.exit.is_set():
            break

        # parse 1000 lines
        isc_lines = App.fh.get_lines(1000)

        # same file?
        if not isc_lines:

            if App.fh.inode != App.fh.get_inode():
                Log.info('Inode change for %s: %d => %d. Reopening file...' % (App.isclog, App.fh.inode, App.fh.get_inode()))
                App.fh.reopen()
            else:
                time.sleep(1)

        # notify parser thread to parse new dataz
        App.queue.put(isc_lines)



except KeyboardInterrupt:
    Log.info("Caught break signal, shutting down")
    pass

# cleanup
Log.debug("[mainThread] Shutting down server thread")
App.server.shutdown()

Log.debug("[mainThread] Shutting down parser thread")
App.exit.set()

Log.debug("[mainThread] Closing log filehandle")
App.fh.close()
