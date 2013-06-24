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


class App(object):
    'For config and infor purposes'

    debug = False

    stats = {
        'discover': 0,
        'offer': 0,
        'request': 0,
        'ack': 0,
        'nak': 0
    }

    @staticmethod
    def usage():
        print 'Usage: %s [-a address] [-p port] [-f file] [-b] [-d] [-h]' % os.path.basename(__file__)
        print '\t-a or --address, ip address to listen on (default 127.0.0.1)'
        print '\t-p or --port, tcp port to listen on (default 8080)'
        print '\t-f or --file, isc dhcp log file location (default /var/log/dhcpd.log)'
        print '\t-b or --background, run in background (default foreground)'
        print '\t-d or --debug, print debug messages'
        print '\t-h or --help, prints this help message'
        sys.exit(0)

    @staticmethod
    def print_stats():

        print str(App.stats) + '\n'

    @staticmethod
    def get_stats():

        return str(App.stats) + '\n'

    @staticmethod
    def get_json():

        return json.dumps(App.stats) + '\n'


class Log(object):
    'For logging purposes'

    @staticmethod
    def fatal(msg):
        sys.stderr.write('FATAL: %s\n' % msg.strip())
        sys.exit(1)

    @staticmethod
    def info(msg):
        sys.stdout.write('INFO: %s\n' % msg.strip())

    @staticmethod
    def err(msg):
        sys.stderr.write('ERROR: %s\n' %msg.strip())


    @staticmethod
    def debug(msg):
        if App.debug:
            sys.stderr.write('DEBUG: %s\n' %msg.strip())


class StatsHandler(SocketServer.StreamRequestHandler):
    'Handles each HTTP request and returns current stats'
    
    http = {
        'response': 'HTTP/1.0 200 OK',
        'headers': {
            'Content-Type': 'text/plain',
            'Content-Length': ''

        },
        'content': ''
    }

    def handle(self):

        Log.debug('Handling connection %s on port %d' % self.client_address)
        http = StatsHandler.http.copy()
        content = App.get_json()
        http['content'] = content
        http['headers']['Content-Length'] = str(len(content))

        payload = http['response'] + '\r\n'
        payload += ''.join( ['%s: %s\r\n' % (k,v) for k,v in http['headers'].items()] ) + '\r\n'
        payload += http['content']

        self.wfile.write(payload)


class StatsServer(SocketServer.ThreadingTCPServer):
    '''
    Reporting stats via HTTP requests
    Responses are returned in json format
    '''
    allow_reuse_address = True

    def shutdown(self):

        SocketServer.ThreadingTCPServer.shutdown(self)
        return


class Filehandle(object):

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
        
        lines = []

        while len(lines) < count:

            line = self.filehandle.readline().strip()

            # on eof we return the lines that we've read so far
            if not line:
                return lines

            lines.append(line)

        return lines

        
class Line(object):

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


    def __init__(self, queue, name):

        threading.Thread.__init__(self, name=name)
        self.name = name
        self.queue = queue
        self.item = None

    def run(self):

        while True:

            Log.debug('%s waiting for queue data...' % self.name)
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
            Log.debug('%s data: %s' % (self.name, App.get_stats()))


# ------------------------#
# Program run starts here #
# ------------------------#

# arg: parse
try: App.options = getopt.getopt(sys.argv[1:], 'a:p:f:bdh', longopts=['address=', 'port=', 'file=', 'background', 'debug', 'help'])
except getopt.GetoptError: App.usage()

# arg: defaults
App.debug= False
App.ip= '127.0.0.1'
App.port = 8080
App.logfile = '/var/log/dhcpd.log'
App.daemon = False
App.queue = Queue.Queue()

# arg: check
for option in App.options[0]:

    (opt, val) = option
    if opt in ['-a', '--address']: App.ip = val
    elif opt in ['-p', '--port']: App.port = int(val)
    elif opt in ['-f', '--file']: App.logfile = val
    elif opt in ['-b', '--background']: App.daemon = True
    elif opt in ['-d', '--debug']: App.debug = True
    elif opt in ['-h', '--help']: App.usage()

# socket: setup
Log.debug('Instantiating server...')
App.addr = (App.ip, App.port)
App.server = StatsServer(App.addr, StatsHandler)

# thread: server
Log.debug('Instantiating Server thread...')
thread_server = threading.Thread(target=App.server.serve_forever)
thread_server.daemon = True
thread_server.start()

# thread: parser
Log.debug('Instantiating Parser thread...')
App.parser = ParserThread(App.queue, name="parserThread")
App.parser.daemon = True
App.parser.start()

# filehandle: setup
Log.debug('Opening logfile %s' % App.logfile)
App.fh = Filehandle(App.logfile)

try: App.fh.open()
except IOError, e: Log.fatal('Opening %s failed: %s' % (App.logfile, e[1]))

App.fh.pos_end()

Log.info('Monitoring file %s with inode of %d' % (App.logfile, App.fh.inode))
Log.info("Listening on %s port %d" % App.addr)

# main
try:

    while True:

        # parse 1000 lines
        isc_lines = App.fh.get_lines(1000)

        # same file?
        if not isc_lines:

            if App.fh.inode != App.fh.get_inode():
                Log.info('Inode change for %s: %d => %d. Reopening file...' % (App.logfile, App.fh.inode, App.fh.get_inode()))
                App.fh.reopen()
            else:
                time.sleep(1)

        # notify parser thread to parse new dataz
        App.queue.put(isc_lines)



except KeyboardInterrupt:
    Log.info("Caught break signal, exiting")
    pass

# cleanup
Log.info("Shutting down server thread")
App.server.shutdown()
App.fh.close()
