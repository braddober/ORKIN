
#
# Configure multiple ROACHes in parallel
#
#  Desired improvements:
#   -better error catching/handling
#  
# v1 11dec2014 bsm
#

import mustangmuxlib as umuxlib
from Queue import Queue
from threading import Thread
import corr
import time

def initroaches(rootlist):
    """
initroaches(rootlist) - set up multiple ROACHes in parallel.

INPUT: 
  rootlist = list of strings. Each string is a full path to a directory that
   contains a file called roachIP.txt that has an IP or hostname of a ROACH
   in the required format (eg, in gb ['/home/scratch/bmason/m2scr/roach1/']
OUTPUT:
  a list of umuxlib.util() instances, one for each ROACH that was successfully
  connected to.
CAVEATS:
  the output list may not be in the same order as the input "roachroot" list,
  depending on the contingencies of threading.
"""
    # the worker-bee function for each thread
    def do_roach_init(inqueue,outqueue):
        # infinite loop. gets killed at end of main program-
        while True:
            roachfilename=inqueue.get()
            um=umuxlib.util(rootdir=roachfilename)
            outqueue.put(um)
            inqueue.task_done()
        
    # general-purpose queue structure: a mechanism
    #  for communicating data to and from threads.
    #  maxsize 0 means infinite max size.
    inqueue = Queue(maxsize=0)
    outqueue= Queue(maxsize=0)

    nroaches=len(rootlist)
    # check that we can connect to all ROACHes. make a list
    #  of the good ones we can. (poor man's error handling)
    roach_is_good=[]
    roach_names=[]
    n_good_roaches=0
    for r in rootlist:
        rname=umuxlib.loadRoachIPstandAlone(r)
        roach_names.append(rname)
        roach=corr.katcp_wrapper.FpgaClient(rname,7147,timeout=60)
        # this sleep appears to be needed or else the 
        #  roach.is_connected() call returns 0
        time.sleep(0.5)
        this_roach_good=roach.is_connected()
        n_good_roaches += this_roach_good
        roach_is_good.append(this_roach_good)
        print this_roach_good,n_good_roaches,rname

    # start worker threads which will sit there waiting for data
    for ii in range(n_good_roaches):
        if (roach_is_good[ii]):
            myroot=rootlist[ii]
            initOneRoach = Thread(target=do_roach_init,args=(inqueue,outqueue,))
            # set threads to be "daemons" which means they get killed
            #  when the main program is done-
            initOneRoach.setDaemon(True)
            # this sleep helpds guide you to same-ordered output
            time.sleep(0.25)
            initOneRoach.start()

    # push data (list of roach root dirs) onto input queue
    for ii in range(n_good_roaches):
        if (roach_is_good[ii]):
            # this sleep helpds guide you to same-ordered output
            time.sleep(0.25)
            inqueue.put(rootlist[ii])

    # wait for all the threads to signal they have
    #  done their job, which is done via inqueue.task_done()
    inqueue.join()

    # define an empty list to contain the umux objects
    ums=[]
    # get the data from the output queue
    #  and print a test statement-
    print "is connected? --> "
    for ii in range(n_good_roaches):
        ums.append(outqueue.get())
        print ums[ii].roach.is_connected()
    print "Finished configuring ROACHes"
    for ii in range(len(ums)):
        print "ums[%s]"%str(ii) + " is " + ums[ii].roachIP
    return ums


def multitune(ums):
    print 'starting tuning'
    for ii in range(len(ums)):
        um=ums[ii]
        print 'tuning ROACH ' + um.roachIP
        um.tune()
    return

def startDemod(ums,frmFreq,frmAmp):
    print 'starting Demod data'
    ums[0].setupFG(frmFreq,frmAmp,0,'ramp','on')
    for ii in range(len(ums)):
        um=ums[ii]
        print 'finding car freqs for ROACH ' + um.roachIP
        um.getRawPhase(3)
        um.setupDemod(frmFreq,frmAmp,clip=False,doFG=False)
    return
