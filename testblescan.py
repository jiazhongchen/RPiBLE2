#!/usr/bin/python2.7.3 -tt
# test BLE Scanning software
# jcs 6/8/2014
# version 1.1 released on 27/11/2015 
# add timeout functions
# version 1.0 released on 27/11/2015

import serial
import blescan
import os
import sys
import time
import datetime
import threading
import urllib2
import bluetooth._bluetooth as bluez
import xml.etree.cElementTree as ET
import fcntl, socket, struct
from xml.etree.ElementTree import Element, SubElement, Comment, tostring

path = os.path.dirname(sys.argv[0])

result = os.system("ifconfig | grep wlan0")
if result == 0: 
	interface = 'wlan0'
else:
	interface = 'eth0'

def postXML(bList):

	for item in bList:
		try:
			#blescan.sendHexStr(item)
			blescan.sendAsciiStr(item)
			pass
		except OverflowError as err:
			print err
		
		#piMacAdr = open('/sys/class/net/wlan0/address').read()
		#piMacAdr = piMacAdr[:17]
		#print piMacAdr

		print "%s"%getHwAddr(interface)

		root = ET.Element("root")
		ET.SubElement(root, "custcode").text = "TS"
		ET.SubElement(root, "hardwareType").text = "3"
		ET.SubElement(root, "hardwareId").text = "%s"%getHwAddr(interface)
		ET.SubElement(root, "latitude").text = "-35.35"
		ET.SubElement(root, "longitude").text = "149.00"
		ET.SubElement(root, "eventtype").text = "%d"%item.eventtype
		ET.SubElement(root, "eventcode").text = "%d"%item.eventcode
		ET.SubElement(root, "datetimesaved").text = item.tick.strftime("%Y-%m-%d %H:%M:%S")
		ET.SubElement(root, "gmtdatetime").text = item.tick.strftime("%Y-%m-%d %H:%M:%S")
		ET.SubElement(root, "rssi").text = "%i"%item.rssi
		ET.SubElement(root, "driverID").text = item.macAdr.translate(None, ':') 
		ET.SubElement(root, "deviceName").text = item.deviceName
		ET.SubElement(root, "odometer").text = "%d"%(item.distance * 100.0)
		#print "posting " + " %.2fm"%item.distance
		if item.eventtype == 32:
			try:
				#logonInterval = int((item.logoffTick-item.logonTick).total_seconds())
				logonInterval = (item.logoffTick-item.logonTick).seconds
			except TypeError as err:
				print "catched a type error here, set the interval to 0"
				logonInterval = 0
		else:
			logonInterval = 0
		ET.SubElement(root, "engineOnElapsed").text = "%d"%logonInterval

		tree = ET.ElementTree(root)
		tree.write('/tmp/record.xml')
		os.system("curl -d \"xml=`cat /tmp/record.xml`\" http://dev1.thing-server.com/Thingevents")

	del bList[:]

def loadXML():
	print path
	tree = ET.parse(os.path.abspath(path+'/'+'dictionary.xml'))
	root = tree.getroot()
	for child in root:
		key = child.attrib.values()[0]
		value = child.attrib.keys()[0]
		blescan.dict[key]=value
	print blescan.dict

def internet_on():
	try:
		response=urllib2.urlopen('http://dev1.thing-server.com',timeout=1)
		return True
	except urllib2.URLError as err: pass
	return False

def main():

	dev_id = 0
	loadXML()

	try:
		sock = bluez.hci_open_dev(dev_id)
		print "ble thread started"

	except:
		print "error accessing bluetooth device..."
		sys.exit(1)

	blescan.hci_le_set_scan_parameters(sock)
	print "set ble scan parameters"
	blescan.hci_enable_le_scan(sock)
	print "enable ble"

	#blescan.initSerial()

	thread1 = threading.Thread(target = blescan.parse_events, args = (sock, ))
	thread1.start()

	thread2 = threading.Thread(target = blescan.checkAndPrint, args = ( ))
	thread2.start()

	while True:
		time.sleep(1)

		if len(blescan.postList) > 0: #and internet_on():
			#print "now start to post ..."
			lock1 = threading.Lock()
			lock1.acquire()
			#postXML(blescan.postList)
			lock1.release()

		#postList = blescan.parse_events(sock)
		#if len(postList) > 0:
		#	postXML(postList)

def getHwAddr(ifname):

	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	info = fcntl.ioctl(s.fileno(), 0x8927,  struct.pack('256s', ifname[:15]))
	str = ''.join(['%02x' % ord(char) for char in info[18:24]])
	return int(str,16)

if __name__ == '__main__':
    main()

