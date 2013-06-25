### ISC DHCP messages counter written in python

This application watches ISC DHCP logfile for DISCOVER/OFFER/REQUEST/ACK/NAK messages
and listens on given TCP port for incoming connections to report the the statistics to
web clients in JSON format.
I have written this to monitor the number of messages for our production servers which serve
around 200.000 clients with variable lease time (around 1000 messages/second).

#### Requirements:

Python standard library (>=2.6)


#### Configuration options

> Usage: isc_stats.py [-a address] [-p port] [-f file] [-b] [-d] [-h]
> 	-a or --address, ip address to listen on (default 127.0.0.1)
> 	-p or --port, tcp port to listen on (default 8080)
> 	-f or --file, isc dhcp log file location (default /var/log/dhcpd.log)
> 	-b or --background, run in background (default foreground)
> 	-d or --debug, print debug messages
> 	-h or --help, prints this help message


#### Example usage server:


> $ ./isc_stats.py -f /storage/logs/iptv/dhcpd.log
> INFO: Monitoring file /storage/logs/iptv/dhcpd.log with inode of 2902560
> INFO: Listening on 127.0.0.1 port 8080


#### Example usage client:

> $ wget -t1  -O- 127.0.0.1:8080 -q
> {
>     "ack": 35,
>     "nak": 0,
>     "request": 36,
>     "discover": 2829,
>     "offer": 0
> }


#### Issues:

* report issues when found
* tested on Solaris 10, Solaris 11, CentOS 6.4 with Python 2.6 and 2.7


#### TODO:

* add option to check files in format /path/to/file/dhcpd-%D%m%y.log
* create init script 
