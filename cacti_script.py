#!/usr/bin/env python
import urllib
import json


class Cacti(object):
    '''
    Helper class for formatted output
    '''
    @staticmethod
    def print_dict(stats_dict):
        'Prints python dict in cacti-understandable script output format'
        for k,v in sorted(stats_dict.items()):

            print '%s:%s' % (k.upper(), v),

class App(object):
    '''
    Main class
    '''
    stats_dict = { 
        'discover': 0,
        'offer': 0,
        'request': 0,
        'ack': 0,
        'nak': 0
    }

    @staticmethod
    def main():
        '''
        Main method
        '''
        try: 
            App.stats_dict = json.loads(urllib.urlopen(App.stats_url).read())
        except IOError:
            pass
        finally:
            Cacti.print_dict(App.stats_dict)
        
#----------------------------#
# replace this with your url # 
#----------------------------#
App.stats_url = 'http://127.0.0.1:8080/'


if __name__ == '__main__':

    App.main()

