from threading import Thread
from pyCOSM.COSM import COSM,DataPoint
from tl500 import ThreadedLogger
from Queue import Queue
from time import sleep
import os, re
import datetime
import optparse




class ThreadedCOSM(Thread):
	feedid=None
	apikey=None
	queue=None
	debug=False
	running=0
	sleeptime=60
	idlist={}
	
	def __init__(self, apikey=None, feedid=None, cosmqueue=None, debug=False, idfile=None, html=None):
		Thread.__init__(self)
		self.debug=debug
		self.apikey=apikey
		self.feedid=feedid
		self.queue=cosmqueue
		self.html=html
		self.cosm=None
		if idfile:
			try:
				fh=open(idfile)
				line=fh.readline()
				while line:
					(key, name)=line.split(None,1)
					self.idlist[key]=name.replace("\n","").replace(" ",".")
					if self.debug==True:
						print "adding id %s for source %s"%(name.replace("\n","").replace(" ","."), key)
					line=fh.readline()
				fh.close()
			except:
				pass
		if self.debug==True:
			print "Initialised COSM handler"

	def update(self):
		if self.cosm != None:
			self.cosm.update()
			if self.debug==True:
				print "COSM updated"
			if self.html !=None:
				self.write_html(self.cosm.current_values())
				
	def write_html(self, currentvals):
		if self.html:
			try:
				fh=open(self.html, "w")
				for p in currentvals:
					if self.idlist.has_key(p['id']):
					 	fh.write("%s\t%s\t%s\n"%(p["id"], p['value'],p['at']))
				fh.close()
				
								
			except Exception, e:
				print "Error writing HTML file: %s"%e
		
	def stop(self):
		if self.debug==True:
			print "COSM: thread stopping"
		self.running=0
					
	def run(self):
		if self.apikey==None or self.feedid==None:
			raise Exception("No apikey or feedid set")
		self.cosm=COSM(apikey=self.apikey, feedid=self.feedid, debug=self.debug)
		self.cosm.get()
		self.running=1
		if self.debug==True:
			print "Started COSM handler"
		while self.running==1:
			if self.debug==True:
				print "Checking queue"
			
			try:
				val=self.queue.get()
				if self.debug==True:
					print "Work to do"
				if self.debug==True:
					print "processing %s"%val
				if val.has_key('at') and val.has_key('value') and val.has_key('id'):
					streamid=self.idlist.get(val['id'],val['id'])	
					self.cosm.addDatapoint(DataPoint(round(float(val['value']),1), val['at']), streamid)
					if self.debug:
						print "Datapoint added :%s"%val
				self.queue.task_done()
			except Exception, e:	
				if self.debug==True:
					print "Queue error - %s."%e
				#sleep(self.sleeptime)
		if self.debug==True:
			print "TC: thread stopped"
			
class OneWireLog(Thread):
	path="/sys/devices/w1_bus_master1/"
	
	def __init__(self, cosmqueue=None, path="/sys/devices/w1_bus_master1/", interval=60, debug=False):
		Thread.__init__(self)
		self.cosmqueue=cosmqueue
		self.path=path
		self.running=0
		self.interval=interval
		self.debug=debug
		
		
	def run(self):
		if os.path.exists(self.path):
			self.running=1
		while self.running==1:			
			for p in os.listdir(self.path):
				m=re.match('10-\d+', p)
				if m:
					try:
						fh=open(os.sep.join((self.path,p,"w1_slave")))
						check=fh.readline()
						assert check.split()[-1][:3]=='YES'
						value=float(fh.readline().split()[-1][2:])/1000
						fh.close()
						self.cosmqueue.put({'at':datetime.datetime.now(), 'id': p, 'value':value})
					except:
						if fh !=None:
							fh.close()
							
			sleep(self.interval)
		if self.debug==True:
			print "OWL: thread stopped"

	def stop(self):
		if self.debug==True:
			print "OWL: thread stopping"
		self.running=0
		
if __name__=='__main__':
	
	#parse command line options to 
	p = optparse.OptionParser()
	p.add_option( '--daemon', '-d', action ='store_true', default=False,
              help='run as daemon (debug==False)')
	p.add_option( '--apikey', '-k', 
              help='COSM Api key')
	p.add_option( '--debug', '-v', action ='store_true', default=False , 
              help='be more verbose for debugging')
	p.add_option( '--feedid', '-f', help='COSM feed id')
	p.add_option('--runfile', '-r', help='file for storing process pid')
	p.add_option("--rawlog", "-l", help="File to log raw TL500 data to")
	p.add_option("--idfile",'-i', help="File containing list of IDs and names")
	p.add_option("--webpage", '-w', help='html file to write with details.')
	OPT, arguments = p.parse_args()
	params={}
	try:
		COSMDIR=os.environ['COSMDIR']
		fh=open("/".join([COSMDIR,"settings"]), "r")
		for line in fh.readlines():
			if line[0]=='#':
				continue
			else:
				try:
					(par, val)=line.split(' ',1)
					params[par]=val
				except: 
					pass
		fh.close()
	except:
		pass
	debug=None
	if params.has_key('debug'):
		debug=bool(params['debug'])
	debug=OPT.debug
	apikey=None
	if params.has_key('apikey'):
		apikey=params['apikey']
	if OPT.apikey:
		apikey=OPT.apikey
	
	feedid=None
	if params.has_key('feedid'):
		feedid=params['feedid']
	if OPT.feedid:
		feedid=OPT.feedid	
	if apikey ==None or feedid == None:
		print "API key and feed id must be set."
		exit(1)
	pidfile=None
	if params.has_key('runfile'):
		pidfile=params['runfile']
	if OPT.runfile:
		pidfile=OPT.runfile
	if pidfile==None:
		pidfile='/var/log/tl500.pid'
	
	htmlfile=None
	if params.has_key('webpage'):
		htmlfile=params['webpage']	
	if OPT.webpage:
		htmlfile=OPT.webpage
	
	daemon=False
	if params.has_key('daemon'):
		daemon=bool(params['daemon'])
	if OPT.daemon==True:
		daemon=True
	if daemon:
		debug=False
		pid=os.fork()
		if pid >0:
			exit(0)
		else:
			pid=os.fork()
			if pid >0:
				exit(0)
	idfile=None
	if params.has_key('idfile'):
		idfile=params['idfile']
	if OPT.idfile:
		idfile=OPT.idfile
	rawlog=None
	if params.has_key('rawlog'):
		rawlog=params['rawlog']
	if OPT.rawlog:
		rawlog=OPT.rawlog					
	cq=Queue()
	owl=OneWireLog(cosmqueue=cq, debug=debug)
	tc=ThreadedCOSM(apikey=apikey,feedid=feedid, debug=debug, cosmqueue=cq , idfile=idfile, html=htmlfile)
	arex=ThreadedLogger(pidfile, cosmqueue=cq, debug=debug, textlog=rawlog)
	
	tc.setDaemon(True)
	tc.start()
	owl.setDaemon(True)
	owl.start()
	arex.setDaemon(True)
	arex.start()
	
	sleep(2) # to give the threads a chance to initialise fully.
	#owl.join()
	#tc.join()
	#arex.join()
	while os.path.exists(pidfile):
		if daemon==False:
			print "Logging"
			print "%s"%tc.cosm.current_values()
		sleep(60)
		tc.update()
		if arex==None:
			arex=ThreadedLogger(pidfile, cosmqueue=cq, debug=debug, textlog=OPT.rawlog)
			print "Restarting TL-500 logger"
			sleep(2)
	print "Stopping."
	arex.stop()
	owl.stop()
	tc.stop()
	#arex.join()
	#owl.join()
	#tc.join()
	