#!/usr/bin/python2.7.3 -tt
# BLE iBeaconScanner based on https://github.com/adamf/BLE/blob/master/ble-scanner.py
# JCS 06/07/14

import serial
import array
import re
import os
import string
import sys
import struct
import time
import datetime
import bluetooth._bluetooth as bluez
import threading

import Adafruit_GPIO.SPI as SPI
import Adafruit_SSD1306
import Image
import ImageDraw
import ImageFont

RST = 24
path = os.path.dirname(sys.argv[0])

#SIGNAL_THRESHOLD_HIGH = -95
#SIGNAL_THRESHOLD_LOW = -115

SIGNAL_THRESHOLD_HIGH = -60
SIGNAL_THRESHOLD_LOW  = -70 	#about 4 meters
TIMEOUT_SECONDS_TICK  = 60		# 1 min

ibeaconList = []
postList = []
dict = {}
tickdict = {}
rssidict = {}
ser = serial.Serial()
bestBeacon = 0
lastBestBeacon = 0
maxrssi = -127

################### I2C monitor configuration parameters ##############################
disp = Adafruit_SSD1306.SSD1306_128_64(rst=RST)
disp.begin()
disp.clear()
disp.display()
width = disp.width
height = disp.height
velocity = -2
startpos = 64
pos = 64
image = Image.new('1', (width, height))
draw = ImageDraw.Draw(image)
font1 = ImageFont.truetype(os.path.abspath(path+'/'+'Minecraftia.ttf'), 8)
font2 = ImageFont.truetype(os.path.abspath(path+'/'+'Minecraftia.ttf'), 10)
################### I2C monitor configuration parameters ##############################

# BLE scanner based on https://github.com/adamf/BLE/blob/master/ble-scanner.py
# BLE scanner, based on https://code.google.com/p/pybluez/source/browse/trunk/examples/advanced/inquiry-with-rssi.py

# https://github.com/pauloborges/bluez/blob/master/tools/hcitool.c for lescan
# https://kernel.googlesource.com/pub/scm/bluetooth/bluez/+/5.6/lib/hci.h for opcodes
# https://github.com/pauloborges/bluez/blob/master/lib/hci.c#L2782 for functions used by lescan

# performs a simple device inquiry, and returns a list of ble advertizements 
# discovered device

# NOTE: Python's struct.pack() will add padding bytes unless you make the endianness explicit. Little endian
# should be used for BLE. Always start a struct.pack() format string with "<"

LE_META_EVENT = 0x3e
LE_PUBLIC_ADDRESS=0x00
LE_RANDOM_ADDRESS=0x01
LE_SET_SCAN_PARAMETERS_CP_SIZE=7
OGF_LE_CTL=0x08
OCF_LE_SET_SCAN_PARAMETERS=0x000B
OCF_LE_SET_SCAN_ENABLE=0x000C
OCF_LE_CREATE_CONN=0x000D

LE_ROLE_MASTER = 0x00
LE_ROLE_SLAVE = 0x01

# these are actually subevents of LE_META_EVENT
EVT_LE_CONN_COMPLETE=0x01
EVT_LE_ADVERTISING_REPORT=0x02
EVT_LE_CONN_UPDATE_COMPLETE=0x03
EVT_LE_READ_REMOTE_USED_FEATURES_COMPLETE=0x04

# Advertisment event types
ADV_IND=0x00
ADV_DIRECT_IND=0x01
ADV_SCAN_IND=0x02
ADV_NONCONN_IND=0x03
ADV_SCAN_RSP=0x04

# Global value
report_pkt_offset = 0
JAALEE_UUID = "ebefd08370a247c89837e7b5634df524"
WGX_UUID    = "e2c56db5dffb48d2b060d0f5a71096e0"

class IBeacon:

	#local fields from raw data:
	totalLen = 0
	macAdr = ""
	uuid = ""
	major = 0
	minor = 0
	power = 0
	battery = -1
	rssi = -127
	avgrssi = -127
	rssiList = [-127,-127,-127]
	distance = 200.0
	#other fields created by TS:
	deviceName = ""
	tick = 0
	eventtype = 0
	eventcode = 0
	logonTick = 0
	logoffTick = 0
	
	def __init__(self,pkt):

		self.totalLen = struct.unpack("B", pkt[2])[0]
		self.macAdr = self.returnMacAdr(pkt[report_pkt_offset + 7:report_pkt_offset + 13])

		subpktuuid = pkt[23:39]
		self.uuid  = self.returnUUID(subpktuuid) 
		self.major = struct.unpack("B", pkt[39])[0]*256 + struct.unpack("B", pkt[40])[0]
		self.minor = struct.unpack("B", pkt[41])[0]*256 + struct.unpack("B", pkt[42])[0]
		self.power = struct.unpack("b", pkt[43])[0]
		if self.totalLen == 0x2b:
			self.battery = struct.unpack("B", pkt[44])[0] 
		else:
			self.battery = -1
		self.rssi = struct.unpack("b", pkt[-1])[0]
		#self.distance = self.returnAccuracy(self.rssi, self.power)

		if self.macAdr in dict.keys():
			self.deviceName = dict[self.macAdr]
		else:
			self.deviceName = "unknown"
		self.tick = datetime.datetime.now()
		self.rssiList = [-127,-127,-127]

	def returnMacAdr(self, pkt):
		return ':'.join('%02x'%i for i in struct.unpack("<BBBBBB", pkt[::-1]))

	def returnAvgRssi(self, rssiList):
		return sum(rssiList)/len(rssiList)

	def returnAccuracy(self, rssi, power):
		RSSI = abs(rssi)
		if RSSI == 0:
			return -1
		if power == 0:
			return -1

		ratio = RSSI * 1.0 / abs(power)
		if ratio < 1.0:
			return pow(ratio, 8.0)
		accuracy = 0.69976 * pow(ratio, 7.7095) + 0.111
		return accuracy
		#if rssi == 0:
		#	return -1.0
		#ratio = rssi * 1.0 / power
		#rssiCorrection = 0.96 + pow(abs(rssi), 3.0) % 10.0 / 150.0
		#if ratio < 1.0:

		#	try:
		#		return pow(abs(ratio), 9.98) * rssiCorrection
		#	except ValueError as err:
		#		print "%i"%rssi + " " + "%i"%power
		#		print err
	
		return (0.103 + 0.89978 * pow(abs(ratio), 7.71)) * rssiCorrection

	def returnUUID(self, pkt):
		myString = "";
		for c in pkt:
			myString += "%02x" %struct.unpack("B",c)[0]
		return myString 

def beaconInList(b, L):
	index = -1
	count = 0
	for i in L:
		if b.macAdr == i.macAdr:	
			index = count	
			break
		else:
			count = count + 1
	return index

def returnnumberpacket(pkt):
    myInteger = 0
    multiple = 256
    for c in pkt:
        myInteger += struct.unpack("B",c)[0] * multiple
        multiple = 1
    return myInteger 

def returnstringpacket(pkt):
    myString = "";
    for c in pkt:
        myString += "%02x" %struct.unpack("B",c)[0]
    return myString 

def printpacket(pkt):
    for c in pkt:
        sys.stdout.write("%02x " % struct.unpack("B",c)[0])

def get_packed_bdaddr(bdaddr_string):
    packable_addr = []
    addr = bdaddr_string.split(':')
    addr.reverse()
    for b in addr: 
        packable_addr.append(int(b, 16))
    return struct.pack("<BBBBBB", *packable_addr)

def packed_bdaddr_to_string(bdaddr_packed):
	return ':'.join('%02x'%i for i in struct.unpack("<BBBBBB", bdaddr_packed[::-1]))

def hci_enable_le_scan(sock):
    hci_toggle_le_scan(sock, 0x01)

def hci_disable_le_scan(sock):
    hci_toggle_le_scan(sock, 0x00)

def hci_toggle_le_scan(sock, enable):
    cmd_pkt = struct.pack("<BB", enable, 0x00)
    bluez.hci_send_cmd(sock, OGF_LE_CTL, OCF_LE_SET_SCAN_ENABLE, cmd_pkt)

def hci_le_set_scan_parameters(sock):
    old_filter = sock.getsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, 14)
    SCAN_RANDOM = 0x01
    OWN_TYPE = SCAN_RANDOM
    SCAN_TYPE = 0x01
    
def parse_events(sock, loop_count=10):

	tick = 0
	while True:

		old_filter = sock.getsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, 14)

		flt = bluez.hci_filter_new()
		bluez.hci_filter_all_events(flt)
		bluez.hci_filter_set_ptype(flt, bluez.HCI_EVENT_PKT)
		sock.setsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, flt )

		pkt = sock.recv(255)
		#print printpacket(pkt)
		pktlen1 = struct.unpack("B", pkt[2])[0]
		if pktlen1 > 12:
			pktlen2 = struct.unpack("B", pkt[13])[0]
		else:
			pkelen2 = 0

		if pktlen1 >= 40 and pktlen2 > 0:
			
			ibeacon = IBeacon(pkt)

			#if (ibeacon.uuid == JAALEE_UUID or ibeacon.uuid == WGX_UUID) and ibeacon.macAdr in dict.keys():
			#if ibeacon.uuid == JAALEE_UUID and ibeacon.major == 2015 :
			#if ibeacon.uuid == WGX_UUID and ibeacon.major == 2015:
			if ibeacon.major == 2015:

				#print ibeacon.macAdr + " %i "%ibeacon.rssi + str(ibeacon.rssiList)

				index = beaconInList(ibeacon, ibeaconList)

				lock = threading.Lock()
				lock.acquire()

				if index != -1:
					
					oldeventtype = ibeaconList[index].eventtype
					ticksec = (ibeacon.tick-ibeaconList[index].tick).total_seconds()
					ibeaconList[index].rssiList.append(ibeacon.rssi);
					ibeaconList[index].rssiList.pop(0);
					avgrssi = ibeaconList[index].returnAvgRssi(ibeaconList[index].rssiList)
					ibeaconList[index].avgrssi = ibeacon.avgrssi = avgrssi
					ibeaconList[index].rssi = ibeacon.rssi
					ibeaconList[index].distance = ibeaconList[index].returnAccuracy(avgrssi, ibeacon.power)
					ibeaconList[index].tick = ibeacon.tick

					#print "%i: "%ibeacon.minor + " %i"%ibeacon.rssi + " %i "%avgrssi + str(ibeaconList[index].rssiList)
					#print "%i: "%ibeacon.minor + " %i "%ibeacon.rssi + str(ibeaconList[index].rssiList)

					#if oldeventtype != 32 and avgrssi < SIGNAL_THRESHOLD_LOW: 

					#	print "departure " + ibeacon.macAdr + " %.2fm"%ibeaconList[index].distance

					#	ibeaconList[index].eventtype = 0x20
					#	ibeaconList[index].eventcode = 0x06
					#	ibeaconList[index].logoffTick = ibeacon.tick

					#	#print int((ibeacon.logoffTick-ibeacon.logonTick).total_seconds())

					#	#ibeaconList[index] = ibeacon
					#	#postList.append(ibeacon)

					#elif oldeventtype == 32 and avgrssi >= SIGNAL_THRESHOLD_HIGH:

					#	print "arrival " + ibeacon.macAdr + " %.2fm"%ibeaconList[index].distance

					#	ibeaconList[index].eventtype = 0x10
					#	ibeaconList[index].eventcode = 0x06
					#	ibeaconList[index].logonTick = ibeacon.tick
					#	ibeaconList[index].logoffTick = 0

					#	#ibeacon.eventtype = 0x10
					#	#ibeacon.eventcode = 0x06
					#	#ibeacon.logonTick = ibeacon.tick
					#	#ibeacon.logoffTick = 0

					#	#ibeaconList[index] = ibeacon
					#	#postList.append(ibeacon)

					#elif oldeventtype != 32 and ticksec > 60.0 and avgrssi >= SIGNAL_THRESHOLD_HIGH:

					#	print "heartbeat: " + str(ticksec) + " of " + ibeacon.macAdr + " %.2fm"%ibeaconList[index].distance

					#	ibeaconList[index].eventtype = 0x00
					#	ibeaconList[index].eventcode = 0x06
					#	ibeaconList[index].logonTick = ibeacon.tick
					#	ibeaconList[index].logoffTick = 0
					#	ibeaconList[index].tick = ibeacon.tick

					#	#ibeacon.eventtype = 0x00
					#	#ibeacon.eventcode = 0x06
					#	#ibeacon.logonTick = ibeaconList[index].logonTick
					#	#ibeacon.logoffTick = 0

					#	#ibeaconList[index] = ibeacon
					#	#postList.append(ibeacon)

				elif ibeacon.rssi >= SIGNAL_THRESHOLD_LOW:

					ibeacon.eventtype = 0x10
					ibeacon.eventcode = 0x06
					ibeacon.logonTick = ibeacon.tick
					ibeacon.logoffTick = 0
					ibeacon.rssiList.append(ibeacon.rssi);
					ibeacon.rssiList.pop(0);
					ibeacon.avgrssi = ibeacon.returnAvgRssi(ibeacon.rssiList)

					ibeaconList.append(ibeacon)	
					#postList.append(ibeacon)

					print "new ibeacon " + "%i:"%ibeacon.minor + " %i"%ibeacon.rssi + " %i "%ibeacon.avgrssi + str(ibeacon.rssiList)

				lock.release() 
				
		sock.setsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, old_filter )

		#check and remove timeout ibeacons, also print the beacon's minor if this beacon has the best rssi value
		tick += 1
		if (tick % 10 == 0): #every 5 x 0.1 = 0.5 seconds

			global lastBestBeacon
			global bestBeacon
			global maxrssi

			nowtick = datetime.datetime.now()
			maxrssi = -127

			for ibeacon in ibeaconList:

				pastSec = (nowtick - ibeacon.tick).total_seconds()
				if (pastSec > TIMEOUT_SECONDS_TICK):
					print "remove timeout ibeacons: " + "m:%i "%ibeacon.minor + "len: %i "%len(ibeaconList) + "l:%i"%lastBestBeacon
					#if (len(ibeaconList) == 1) and (ibeacon.minor == lastBestBeacon):
						#sendAsciiCmd(lastBestBeacon, 0)
					ibeaconList.remove(ibeacon)
					break


				#print "beacon:" + "%i "%ibeacon.minor + " %i "%ibeacon.avgrssi + " %i"%maxrssi
				if ibeacon.avgrssi > maxrssi:
					maxrssi = ibeacon.avgrssi
					bestBeacon = ibeacon.minor
				#print "current bestBeacon is: " + str(bestBeacon)

			if lastBestBeacon != bestBeacon: 
				#sendAsciiCmd(lastBestBeacon, bestBeacon)
				lastBestBeacon = bestBeacon

		if tick > 36000:
			tick = 0

		time.sleep(0.1);

def checksum(hexlist):
	result = hexlist[0] 
	for hex in hexlist[1:]:
		result = result ^ hex
	return result

def initSerial():
	ser.port = '/dev/ttyUSB0'
	ser.baudrate = 9600
	ser.timeout = 1
	ser.open()

def sendHexStr(item):
	print "start to send via serial port:"
	newMacAdr = item.macAdr.translate(None, ':') 
	print newMacAdr
	mac = bytearray(newMacAdr.decode('hex'))
	print item.rssi 
	str = ''
	li = []
	li.append(0xFF)
	li.append(0x08)
	li.append(0x90)
	li.append(0x01)
	li.append(0xEA)
	li.append(0x10)
	li.append(mac[0])
	li.append(mac[1])
	li.append(mac[2])
	li.append(mac[3])
	li.append(mac[4])
	li.append(mac[5])
	li.append(item.eventtype)
	li.append(item.eventcode)
	li.append(tohex(item.rssi, 8))
	li.append(checksum(li))	
	str = array.array('B', li).tostring()
	ser.write(str)

def sendAsciiStr(item):
	str = "at$app msg "
	str += "ZZ"
	str += "%02x"%item.eventtype
	str += "%02x"%item.eventcode
	str += item.macAdr.translate(None,':')
	str += "%02x"%tohex(item.rssi, 8)
	str += " 1\r\n"
	print str
	ser.write(str)

def sendAsciiCmd(old, new):
	str1 = "at$app msg ZZB103"
	str2 = "at$app acc set 2 "
	str3 = "at$app msg ZZB102"
	endstr1 = " 1\r\n"
	endstr2 = "\r\n"

	if old != 0:

		str = str1 + "%08i"%old + endstr1
		print(str)
		ser.write(str)
		time.sleep(0.5);

	str = str2 + "%08i"%new + endstr2
	print(str)
	ser.write(str)
	time.sleep(0.5);

	if new != 0:

		str = str3 + "%08i"%new + endstr1
		print(str)
		ser.write(str)
		time.sleep(0.5);

def tohex(val, nbits):
	newval = (val + (1 << nbits)) % (1 << nbits) 
	print hex(newval)
	return newval

def checkAndPrint(): # Check any timeout ibeacons and print found ibeacons list

	startpos = 64
	pos = startpos
	velocity = -2
	charWidth, charHeight = draw.textsize("helloworld", font=font1)

	while True:

		# print ibeacon list on OLED
	
		draw.rectangle((0,0,width,height), outline=0, fill=0)
		#draw.text((2, 0), '%s : %d'%('TS Tokens',len(ibeaconList)), font=font1, fill=255)
		draw.text((2, 0), '%s:%d:%i'%('Beacon',bestBeacon, maxrssi ), font=font1, fill=255)
		x = 2
		y = pos

		for item in ibeaconList:
			str = '%i : %i'%(item.minor, item.rssi)
			#str = '%s : %.2fm'%(item.macAdr.upper(), item.distance)
			if y > height:
				break
			if y < 16:				
				charWidth, charHeight = draw.textsize(str, font=font1)
				y += charHeight	
				continue
			draw.text((x, y ), str,  font=font1, fill=255)
			charWidth, charHeight = draw.textsize(str, font=font1)
			y += charHeight	

		disp.image(image)
		disp.display()
		pos += velocity 

		if pos < len(ibeaconList) * charHeight * -1:
			pos = startpos
		time.sleep(0.1);


