import os
import sys

for i in range(13):
    os.system('sudo ovs-ofctl -O openflow13 dump-flows s{}'.format(i+1))

