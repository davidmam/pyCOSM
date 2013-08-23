'''
Created on Oct 23, 2012

@author: dmamartin
'''


from __future__ import with_statement
import datetime
from time import strftime,strptime
from time import time
import time

import sys
import array
import os
import fcntl, sys
import optparse
import subprocess
from threading import Thread 
from struct import unpack

try:
    import rrdtool
except:
    raise Exception("You need rrdtool to run this script!")
 
try:
    import usb.core
except:
    raise Exception("You need pyusb-1 (usb.core) to run this script!")

try:
    import usb.util
except:
    raise Exception("You need pyusb-1 (usb.util) to run this script!")


class TL500:
    '''
    Adapted from original as described below.
    # This Version of the TL500 logger only reads from the usb Device and writes a raw File raw.txt
    # This part of the programm has to be run with enhanced priviledges. That's why the 
    # functionality is reduced to a minimum.
    # The resulting raw data then can be processed with the conversion 
    # script tl500-read-raw2rrd-v0.3-2.py 
    #
    # Another benefit of splitting the capture and the conversion is to be able to 
    # adapt the conversion afterwards. This is usefull, since I'm sure that I still 
    # don't know everything of the bytes returned by the logger.
    #
    # To automatically start and restart the Logger you can add a line into your crontab
    # /etc/crontab:
    # */10 *  * * *   root /usr/local/bin/tl500-raw-logger_v0.3-3.py

    # Original Python Source from
    # http://www.j-raedler.de/2010/08/reading-arexx-tl-500-with-python-on-linux-part-ii/
    ''' 
    debug=False
    errors=0
    
    def __init__(self,  rawAction=None, debug=False, usbtimeout=100):
        self.dev = None
        self.rawAction = rawAction
        self.debug=debug
        self._buffer = array.array('B', [0]*64)
        if self.debug:
            print "TL500 Init Done"
        self.errors = 0
        self.timeout=usbtimeout

    def connect(self):
        
        #try to reset the device
        try:
            bus=None
            p=subprocess.Popen("lsusb", stdout=subprocess.PIPE)
            o=p.communicate()[0]
            for d in o.split("\n"):
                f=d.split()
                if len(f)==0:
                    continue
                if f[5]=='0451:3211':
                    bus="/dev/bus/usb/%s/%s"%(f[1],f[3].replace(':',''))
            if bus !=None:
                subprocess.call(['usbreset',bus])
            else:
                raise Exception("No TL-500 found")
        except Exception, e:
            raise Exception("Error initialising USB bus: %s "%e)
        try:
            #usb.core.reset()
            self.dev = usb.core.find( idVendor=0x0451, idProduct=0x3211 )
        except Exception, e:
            print datetime.datetime.now(),"TL500: Error: " 
            print e
            self.errors += 1
            raise Exception("Cannot Connect to Arexx TL-500!")

        if not self.dev:
            raise Exception("Arexx TL-500 not found!")

        # to avoid a SIGSEG with newer Linux-Kernels
        try:
            self.dev.set_configuration() 
        except Exception, e:
            print datetime.datetime.now(),"TL500: Error: Cannot COnfigure USB Device"
            print e
            self.errors += 1

        if self.debug:
            print "TL500: Connect Done"
            #print str(self.dev.bConfigurationValue) + '\n'

    def loopCollect(self, interval=10):
        if not self.dev:
            try:
                self.connect()
            except Exception, e:
                print "TL500: Cannot connect to logger - exiting: %s"%e
                exit(1)
        # Switch device in the correct Mode
        if self.debug:
            print "TL500: pre first write "
        self._buffer[0] = 4
        try:
            resp=self.dev.write(0x1, self._buffer, 0, self.timeout)
        except Exception, e:
            print datetime.datetime.now(),"TL500: Error: Cannot set Mode for logging Device"
            print e
            self.errors += 1

        if self.debug:
            print "TL500: First write done: %s"%resp

        # Ask for Data and read it
        self._buffer = array.array('B', [0]*64)
        self._buffer[0] = 3
        self.running=1
        while self.running==1:
            try:
                resp=self.dev.write(0x1, self._buffer, 0, self.timeout)
                #if self.debug==True:
                #    print "wrote 0x1 got %s"%( resp,)
            except Exception, e:
                print datetime.datetime.now(),"TL500: Error: Cannot ask for new Data"
                print e
                self.errors += 1
                
            try:
                rawData = self.dev.read(0x81, 64, 0, self.timeout)
                if rawData[1] != 0:
                    if self.debug==True:
                        print "TL500: calling callback for tl500 data: %s"%self.rawAction 
                    if self.rawAction:
                        self.rawAction(rawData)
            except Exception, e:
                print datetime.datetime.now(),"TL500: Error: Cannot read new Data"
                print e
                self.errors += 1
            
            time.sleep(interval)
            try:
                resp=self.dev.write(0x1, None, 0,self.timeout)
                rawData=self.dev.read(0x81,0,0,self.timeout)
            except Exception, e:
                print datetime.datetime.now(),"TL500: Error: Null read/write"
                print e
            if self.debug: # Progress Dots
                sys.stdout.write(".")
        print "Finished Logging."

class Logger:
    '''Implements the logger functionality for the TL500 - holds the input and output details.'''
    rawFile=None
    rawFileName=None
    pidfile=None
    debug=False
    errors=0
    tl500=None

    def __init__(self, rawFileName, pidfile, debug=False):
        self.rawFile = open(rawFileName, "a")
        self.rawFileName=rawFileName
        self.pidfile=pidfile
        
        
    def logRaw(self, rawData):
        if self.rawFile==None:
            raise Exception("No log file open")
        self.rawFile.write("%15f" % time.time())
        for d in rawData:
            self.rawFile.write(" %02X" % d)
        self.rawFile.write("\n")
        self.rawFile.flush()

    def startLogging(self, interval=30):
        fp = open(self.pidfile, 'w')
        self.errors=0
        try:
            fcntl.lockf(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except  IOError:
            if self.debug:
                print "TL500: another instance is running\n"
            sys.exit(0)
        
        self.errors=0
        fp.write( str(os.getpid())+"\n")
        fp.flush()
        self.tl500=TL500(rawAction=self.logRaw, debug=self.debug)
        # start logging
        while self.tl500.errors <= 50:
            try:
                self.tl500.loopCollect(interval)
            except Exception, e:
                etype,emsg,tb = sys.exc_info()
                print datetime.datetime.now(),"ETL500: rror (",self.tl500.errors,")(Line ",tb.tb_lineno,") : " , e
                self.tl500.errors += 1
                if self.debug:
                    print datetime.datetime.now() ,"TL500: Outer Loop",self.tl500.errors
            #print datetime.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S") ,"Outer Loop",errors
        print "Exit because I had too many Errors"
        

class ThreadedLogger(Thread):

    def __init__(self, pidfile, cosmqueue=None, debug=False, textlog=None, interval=5, upperlimit=50, lowerlimit=-20):
        Thread.__init__(self)
        self.queue=cosmqueue
        self.pidfile=pidfile
        self.debug=debug
        self.rawFile=None
        self.upperlimit=upperlimit
        self.lowerlimit=lowerlimit
        self.interval=interval
        if textlog!=None:
            self.rawFile=open(textlog,"w")
        if self.debug==True:
            print "TL500 Logger thread"
        self.running=0
        
    def run(self):
        '''overide threading superclass'''
        fp = open(self.pidfile, 'w')
        self.errors=0
        if self.debug==True:
            print "Started TL500 Logging"
        try:
            fcntl.lockf(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except  IOError:
            if self.debug:
                print "TL500: another instance is running\n"
            sys.exit(0)
        self.errors=0
        fp.write( str(os.getpid())+"\n")
        fp.flush()
        self.running=1
        while self.running==1:
            try:
                self.tl500=TL500(rawAction=self.processRaw, debug=self.debug)
                self.tl500.loopCollect(self.interval)
            except Exception, e:
                etype,emsg,tb = sys.exc_info()
                print datetime.datetime.now(),"Error (",self.tl500.errors,")(Line ",tb.tb_lineno,") : " , e
                #self.tl500.errors += 1
                if self.debug:
                    print datetime.datetime.now() ,"TL500: Outer Loop",self.tl500.errors
        if self.debug==True:
            print "AREXX: thread stopped"
    def stop(self):
        if self.debug==True:
            print "AREXX: thread stopping"
        self.running=0
        self.tl500.running=0
        
    def logRaw(self, rawData):
        if self.rawFile==None:
            print "No log file open"
            return
        
        self.rawFile.write("%15f" % time.time())
        for d in rawData:
            self.rawFile.write(" %02X" % d)
        self.rawFile.write("\n")
        self.rawFile.flush()
   
    def processRaw(self,binData):
        p=1
        if self.rawFile !=None:
            self.logRaw(binData)
        rawData = unpack("64B",binData)
        if self.debug==True:
            print "TL500: processing raw data length %s"%len(rawData)
            
        #while p<len(rawData)-10:
        #    slice=rawData[p:p+10]
        #if self.debug==True:
        #        print "%s %s"%(len(slice), ",".join(["%02X"%d for d in slice]))
        try:
            parmlist=self.processDataSlice(rawData)
            if self.debug==True:
                print "TL500: Parsed raw data as %s"%parmlist
            if parmlist !=None: 
                for parms in parmlist:            
                    if parms['value']> self.lowerlimit and parms['value'] <self.upperlimit: 
                        self.queue.put({"at": datetime.datetime.now(), "id":parms['SensorName'], "value":parms['value']})
                        if self.debug:
                            print "TL500: added datapoint to the COSM queue: %s"%{"at":datetime.datetime.now(), "id":parms['SensorName'], "value":parms['value']}
        except Exception, e:
            print "TL500: Error processing raw data: %s"%e
    #        p=p+10

    def time_as_str(self):
        return datetime.datetime.fromtimestamp(self.time).strftime("%Y-%m-%d %H:%M:%S")
   
        # start logging
    def processDataSlice(self,rawSlice):
        #print "processDataSlice(): ",rawSlice
        parmlist=[]
        p=0
        
        #while p<len(rawSlice)-10:
        while p==0:
            parms={}
            if rawSlice[p+1]==0:
                return parmlist
                #raise Exception("No data to process")
            parms['len'] = rawSlice[p+1] # Maybe this indicates the type of Data too
            #if not ( parms['len'] == 10 ):
            #    if self.debug ==True:
            #        print "TL500: Length is not 10 it is " , parms['len']
            #if 1:
            #        raise Exception('zero length slice') 
            #    if parms['len'] == 0 : # This seems the last slice in a line which has no content
            #    if parms['len'] > 10 : # Mostly i saw FF. This means to ignore this dataset
            #        raise Exception("overlarge slice") 
            #    if parms['len'] < 9 :
            #        raise Exception('short slice') 
    
    
    
            # -------------------------------------------------------
            # combine the multibyte values
            try:
                if self.debug==True:
                    print "reading sensor"
                parms['sensor']     = int(rawSlice[p+2]) + int(rawSlice[p+3])*256
                if self.debug==True:
                    print "reading valueRaw"
                parms['valueRaw']   = int(rawSlice[p+5]) + int(rawSlice[p+4]*256)
                if self.debug==True:
                    print "reading clock"
                parms['clock']      = rawSlice[p+6] + rawSlice[p+7]*256 + \
                              rawSlice[p+8]*65536 
                if self.debug==True:
                    print "reading other"
                parms['other']      = rawSlice[p+9]
                if self.debug==True:
                    print "reading signal"
                parms['signal']     = int(rawSlice[p+10])
                if self.debug==True:
                    print "reading rawslice"
                parms['rawSlice']   = rawSlice 
                parms['SensorName']=str(parms['sensor'])
            # I would still like values like battery status to show up here
            except:
                print "TL500: Error parsing data"
                return False
    #        if parms['other']>0:
    #            print  self.time_as_str(),self.sensor,"saw in the 'Other'-Byte the Value " , self.other
    
            if self.debug ==True:
                print  parms['sensor'],"Signal:" , parms['signal']
            p=p+parms['len']
    
            '''
            #Ignore clock issues - all signals are immediate and now.
            if self.clockinfo:
                # --------------------------------------------
                # Compare the Receiver internal clock with the PC clock 
                # They will differ if the receiver got reset or had to buffer values
                if self.LastClock.has_key(self.sensor):
                    lastclock=self.LastClock[self.sensor]
                else:
                    lastclock=-1
    
                if ( self.clock < 100 ) and ( self.clock < lastclock):
                    # Check if clock-counter went backwards
                    # then we assume the receiver got reset or got an overflow
                    print self.time_as_str(),self.sensor,"Clock reset from ",  lastclock , "to" , self.clock 
                    if lastclock > self.maxclock:
                        self.maxclock=lastclock
                        self.clockoffset = self.time - self.clock
    
                if ( self.clock >= 100 ) and ( self.clock < lastclock):
                    print self.time_as_str(),self.sensor,"Clock walks backward from ",  lastclock  , "to" , self.clock 
                
                if (self.clock - lastclock)>400:
                    if lastclock < 0:
                        print self.time_as_str(),self.sensor,"Clock set to " , self.clock 
                    else:
                        print self.time_as_str(),self.sensor,"Clock jump from ",  lastclock , "to" , self.clock 
    
                internal_time = (self.clock + self.clockoffset)
                if ( internal_time - self.time ) >2:
                    if self.debug:
                        print self.time_as_str(),self.sensor,"Times differ: \tinternal: ",internal_time ,"\tPC:",self.time, \
                            "\tdiff:",( internal_time - self.time ) ,"\tclock:",self.clock 
                # TODO:
                # This is probably due to the Receiver buffering Data. 
                # So we have to find out how the two clocks refer to each other and 
                # guess the right time the data occured
                self.LastClock[self.sensor]=self.clock
    
            # --------------------------------------------
            # get the real sensor name
            if self.sensors.has_key(self.sensor):
                self.SensorName = self.sensors[ self.sensor ]
            else:
                print self.time_as_str(),"Unknown Sensors:    " ,self.sensor
    
                self.SensorName = str(self.sensor)
                try:
                    self.SensorUnknown[self.sensor] += 1
                except:
                    self.SensorUnknown[self.sensor] = 1
                #return False 
    
            '''
    
            # FIXME: this should changed for other sensor types
            # values taken from 
            # http://www.algorithm-forge.com/techblog/2010/01/linux-usb-driver-for-the-arexx-tl-500-
            # * We assume that all TSN-TH70E sensors have ids bigger than 10000.
            # * For  TSN-TH70E with odd IDs we have the humidity sensor-part.
            # * Has anyone more information about this?
            #        print "Sensor: '",self.sensor,"'"
            if parms['sensor'] > 16384: #  # Sensor with Humidity or Simple Temperature-Sensor
                parms['SensorWithHummidity'] = True
            else:
                parms['SensorWithHummidity'] = False
    
            if parms['valueRaw'] > 32767: 
                # These look like negative Values
                # This should be improved!
                # But as a  start it's better than jumping to >500 Degrees Celcius
                parms['valueRaw']= parms['valueRaw'] - 65535
    
            parms['unit']='degC'
            if parms['SensorWithHummidity'] : # Sensor with Humidity
                if 0 == ( parms['sensor'] % 2 ):     #  TSN-TH70E with even Sensor-number (Temperature)
                    parms['value'] = -39.58 + int(parms['valueRaw']) * 0.01;
                    parms['unit']='degC'
                else: # TSN-TH70E with Odd Sensor-number (Humidity)
                    parms['value'] = 0.6 + parms['valueRaw'] * 0.03328;
                    parms['unit']="%RH"
                parms['SensorName']=str(parms['sensor'])+"_"+parms['unit']
            else:                          # Simple Temperature-Sensor
                parms['value'] = parms['valueRaw'] * 0.0078;
            #value    = 0.0078 * self.valueRaw 
    
            parmlist.append(parms)
        return parmlist


if __name__=="__main__":
    p = optparse.OptionParser()
    p.add_option( '--debug', '-d', action ='store_true', default=False , 
              help='be more verbose for debugging')
    p.add_option( '--verbose', '-v', action ='store_true', default=False , 
              help='be more verbose')
    p.add_option('--logdir', '-l', default='/var/log/tl500', help='Directory for logging files')
    OPT, arguments = p.parse_args()  
    
    pidfile=OPT.logdir+'/tl500.pid'
    rawLogFile=OPT.logdir+'/tl500.raw'
    
    logger=Logger(rawLogFile, pidfile, debug=OPT.debug)
    logger.startLogging()
         
