import datetime
import httplib
import json
from urlparse import urlparse

class DataStream:
    '''A COSM datafeed'''
    streamid=None
    min_value=None
    max_value=None
    currentvalue=None
    currenttime=None
    updated=None
    timeformat='%Y-%m-%dT%H:%M:%S.%fZ'
    datapoints=[]
    debug=False
    tags=[]
    unit={}
    id=None
        
    def __init__(self, streamid, **kwargs):
        self.streamid=streamid
        if kwargs.has_key('debug'):
            self.debug=kwargs['debug']
        if kwargs.has_key('json'):
            if self.debug>0:
                print "parsing Datastream from %s"%kwargs['json'] 
            self.update(kwargs['json'])
            
    def addDatapoint(self, dp):    
        self.datapoints.append(dp)
        self.currentvalue=dp.value
        self.currenttime=dp.timestamp
        if dp.value>self.max_value:
            self.max_value=dp.value
        if dp.value<self.min_value:
            self.min_value=dp.value
        if self.debug:
            print "adding datapoint time: %s value: %s"%(dp.timestamp, dp.value)
            
            
            
    def update(self, data):
        if self.debug >0 :
            print "Parsing DataStream"
            print "%s"%data
        try:
            for k in data.keys():
                if self.debug>0:
                    print "setting DataStream value %s to %s"%(k,data[k])
                if k=='at':
                    dt=datetime.datetime.strptime(data[k],self.timeformat)
                    self.addDatapoint(DataPoint(data['current_value'], dt))
                elif k=='current_value':
                    continue #already added under at
                else:
                    setattr(self,k, data[k])
        except Exception,e:
            raise Exception("Error parsing datastream: %s"%e)       
            
    def current_value(self ):    
        return { "at": self.currenttime.strftime(self.timeformat), "id": self.streamid, "current_value":self.currentvalue }
      
            
class DataPoint:
    '''A COSM datapoint'''
    value=None
    timestamp=None
    
    def __init__(self, value, time=None):
        self.value=value
        if time==None:
            self.timestamp=datetime.datetime.now()
        else:       
            self.timestamp=time
            
class COSM:
    '''Wrapper for a COSM feed environment. '''
    serverhost='api.cosm.com'
    serverpath='/v2/feeds'
    feedid=None
    debug=False
    apikey=None
    datastreams={}
    title=None
    description=""
    feed=None
    id=None
    status="frozen"
    website=None
    updated=None
    created=None 
    version=None 
    private=False
    creator=None
    location={}
    timeformat='%Y-%m-%dT%H:%M:%S.%fZ'
    #{
    # "disposition":"fixed",
    #"ele":"23.0",
    #"name":"office",
    #"lat":51.5235375648154,
    #"exposure":"indoor",
    #"domain":"physical"
    #"lon":-0.0807666778564453,
    #}
    tags=[]
    def __init__(self, **kwargs):
        ''' key args are feedid, apikey '''
        if kwargs.has_key("feedid"):
            self.feedid=kwargs['feedid']
        if kwargs.has_key('apikey'):
            self.apikey=kwargs['apikey']
        if kwargs.has_key('debug'):
            self.debug=kwargs['debug']
    
    def addDatastream(self, datastream):
        if datastream.streamid in self.datastreams.keys():
            raise Exception("Datastream %s already exists"%datastream.streamid)
        if self.debug:
            print "Adding datastream %s"%datastream.streamid
        self.datastreams[datastream.streamid]=datastream
        
    def get(self):
        if self.feedid !=None:
            self.rest_call('GET')
            if self.debug:
                print "retrieved data for feed %s (%s)"%(self.feedid, self.title)
        else:
            raise Exception("No feed id specified")
    
    def create(self):
        if self.id !=None or self.feedid !=None:
            raise Exception("Not a new feed - cannot create an existing feed")
        if self.title==None:
            raise Exception("No title set - not created")
        data={"version":"1.0.0", "title":self.title}
        if self.description !=None:
            data['description']=self.description
        self.rest_call('POST', data)
    
    def update(self):    
        if self.id==None:
            raise Exception("No feed id set")
        cv=self.current_values()
        if self.debug:
            print "Updating feed %s with values %s - previous update %s"%(self.feedid, cv, self.updated)
        newvals=[]
        for v in cv:
            if self.debug:
                print "checking value %s updated %s"%(v['current_value'], v['at'])
            if self.updated==None or v['at'] > self.updated:
                if self.debug:
                    print "New datapoint"

                newvals.append({"id": v['id'], 'current_value': v['current_value'], 'at': v['at']})
        self.updated=datetime.datetime.now().strftime(self.timeformat)
        if len(newvals)>0:
            data={
                  "version":"1.0.0",
                  "datastreams": newvals    
                  }
            if self.debug:
                print "updating with %s"%data
            self.rest_call('PUT', data)
            
            
    def current_values(self):
        cv=[]
        for d in self.datastreams.keys():
            cv.append(self.datastreams[d].current_value())
        return cv
    
    def addDatapoint(self, datapoint, streamid):
        if self.datastreams.has_key(streamid):
            self.datastreams[streamid].addDatapoint(datapoint)
        else:
            self.addDatastream(DataStream(streamid))
            self.datastreams[streamid].addDatapoint(datapoint)
            
    def rest_call(self, method, data=None):
        path=self.serverpath
        if self.apikey==None:
            raise Exception("No API key set")
        headers={'X-ApiKey': self.apikey}
        
        successcode=201
        jsondata=None
        if data !=None:
            jsondata=json.dumps(data)
        if method=='GET':
            successcode=200
            path="%s/%s"%(path, self.feedid)
        elif method=='PUT':
            successcode=200
            path="%s/%s"%(path, self.feedid)
        elif method=='POST':
            pass
        conn=httplib.HTTPConnection(self.serverhost)
        conn.request(method,path,jsondata,headers)
        resp=conn.getresponse()
        if resp.status != successcode:
            raise Exception("Error in COSM http request to %s [%s]: [%s] %s"%(path, resp.status,jsondata, resp.reason))
        jsontxt=resp.read()
        if self.debug>0:
            print "COSM response:"
            print jsontxt
        if method=='GET':
            self._parsejson(jsontxt)
        elif method=='POST':
            self._postcreate(resp.getheaders())            
        
          
    def _parsejson(self, jsontext):
        try:
            info=json.loads(jsontext)
        except Exception, e:
            raise Exception("Exception %s when decoding: %s"%(e, jsontext))
        for k in info.keys():
            if k in ('datastreams'):
                continue
            setattr(self,k, info[k])
        try:
            if self.debug>0:    
                print "Processing DataStreams"
            for d in info['datastreams']:  
                if self.debug>0:
                    print "Datastream %s"%d['id']
                if self.datastreams.has_key(d['id']):
                    if self.debug>0:
                        print "updating datastream with %s"%d
                    self.datastreams[d['id']].update(d)
                else:
                    if self.debug>0:
                        print "creating datastream with %s"%d
                    self.datastreams[d['id']]=DataStream(d['id'],json=d, debug=self.debug) 
                       
        except Exception, e:
            raise Exception("Error parsing datastream: %s"%e)
                        
            
    def _postcreate(self,headers):
        '''post feed creation parsing'''
        if headers.has_key('Location'):
            loc=headers['Location']
            o=urlparse(loc)
            fid=o.path.split("/")[-1]
            self.id=fid
            self.feedid=fid
            
        
        
        
'''

POST /v2/feeds
First let's create an empty feed template. We'll just give it a 'title' and 'version' for now and specify the rest later.

{"title":"My feed", "version":"1.0.0"}

An example using curl is:

curl --request POST \
     --data '{"title":"My feed", "version":"1.0.0"}' \
     --header "X-ApiKey: YOUR_API_KEY_HERE" \
     --verbose \
     http://api.cosm.com/v2/feeds

In the response we should see a status code of 201 (Created) and a location header which tells us the location (including the assigned id) of the newly created feed. We'll need this id when referring to the feed in future.

Update your feed
PUT /v2/feeds/YOUR_FEED_ID
Now let's update your feed and its datastreams. We'll set up three datastreams with unique datastream ids.

{
  "version":"1.0.0",
  "datastreams":[
      {"id":"0", "current_value":"100"},
      {"id":"two", "current_value":"500"},
      {"id":"3.0", "current_value":"300"}
  ]
}

Let's save this to a file called cosm.json.

We can get the id of your feed (referred to as YOUR_FEED_ID below) from your 'my feeds' page in Cosm or in the response header from curl above.

To update the feed using curl is:

curl --request PUT \
     --data-binary @cosm.json \
     --header "X-ApiKey: YOUR_API_KEY_HERE" \
     --verbose \
     http://api.cosm.com/v2/feeds/YOUR_FEED_ID

We can now update the values and repeat this request whenever required.

Retrieve your feed
GET /v2/feeds/YOUR_FEED_ID
Let's take a look at the current state of our feed.

curl --request GET \
     --header "X-ApiKey: YOUR_API_KEY_HERE" \
     http://api.cosm.com/v2/feeds/YOUR_FEED_ID

Now we'll see a whole bunch of information about our feed and its datastreams.

{
    "status": "live",
    "title": "My feed",
    "feed": "http://api.cosm.com/v2/feeds/YOUR_FEED_ID",
    "version": "1.0.0",
    "updated": "2011-02-11T16:12:45.936847Z",
    "datastreams": [{
        "at": "2011-02-11T16:12:45.936847Z",
        "max_value": "100.0",
        "min_value": "100.0",
        "id": "0",
        "current_value": "100"
    },
    {
        "at": "2011-02-11T16:12:45.936847Z",
        "max_value": "500.0",
        "min_value": "500.0",
        "id": "two",
        "current_value": "500"
    },
    {
        "at": "2011-02-11T16:12:45.936847Z",
        "max_value": "300.0",
        "min_value": "300.0",
        "id": "3.0",
        "current_value": "300"
    }],
    "private": "false",
    "id": YOUR_FEED_ID
}
'''
