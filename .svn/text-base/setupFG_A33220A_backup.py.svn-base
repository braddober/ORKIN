
import time
#from numpy import *
#import arconsdefs 
import socket
#import string
#import telnetlib
import sys

############ ---------- USER INPUTS ---------- ############


# Connect to the Agilent for TES Bias (or mock TES signal) control:

class util:
    def __init__(self,freq,amp,offset=0.0,shape="RAMP",onoff="ON",IP='128.91.46.25'):
        self.shape=shape.upper()
        self.onoff=onoff.upper()
        self.IP=IP
        self.offset=float(offset)
        self.freq=float(freq)
        self.amp=float(amp)
        print "Connecting to Agilent Function Generator at "+IP
        self.fg=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.fg.settimeout(5.0)
        try:
            self.fg.connect((IP,5025))
        except:
            print("Error connecting to "+IP)
            raise 
 #       self.fg.settimeout(1.0) # make future timeouts much faster  

        #check it is a A33220A
        thisDevice=self.send("*IDN?\n")
        if thisDevice.find("33220A") == -1:
            print("ERROR: device on IP address "+IP+" does not seem to be a A33220A")
            sys.exit(1)
        #print("connected to device:)")
    
    def set(self):
        waveforms=["SIN","SQU","RAMP","PULS","NOISE"]
        if self.shape in waveforms:
            bck=self.fg.send("FUNC "+self.shape+"\n")
        else: 
            print("ERROR unknown wave form: should be one of "+waveforms)
            sys.exit(1)
        #print("FREQ "+str(self.freq) + "\n")
        bck = self.fg.send("FREQ "+str(self.freq) + "\n")
        #        self.fg.send("FREQ 100.0\n")#("FREQ "+str(self.freq) + "\n")
        chk_freq = float(self.send("FREQ?"))
        if chk_freq != self.freq:
            #print(chk_freq,self.freq)
            raise Exception("failure to set frequency")
            #sys.exit(1)
        self.fg.send("VOLT:UNIT VPP\n") #voltage is peak to peak
        bck = self.fg.send("VOLT "+str(self.amp) + "\n")
        chk_amp = float(self.send("VOLT?\n"))
        if chk_amp != self.amp :
            print("failure to set amplitude")
            sys.exit(1)
        bck = self.fg.send("VOLT:OFFS "+str(self.offset) + "\n")
        chk_offset = float(self.send("VOLT:OFFS?"))
        #print self.fg.recv(100)
        #Aprint(chk_offset, self.offset)
        if chk_offset != self.offset:
            print("failure to set offset")
            sys.exit(1)
        if self.onoff in ["ON","OFF"]:
            bck=self.fg.send("OUTP "+self.onoff+"\n")
        else: 
            print("on/off flag should be 'ON' or 'OFF'")
            sys.exit(1)
        pass

    def send(self,cmd,fail=False):
        #send a command to the instrument and return the reply.  
        # By default it will return an empty string if nothing is send back within the fg.timeout, set fail=True to throw exception
        cmd0=(str(cmd)).upper() + "\n"
        bytes_sent = self.fg.send(cmd0)
        try:
            back=self.fg.recv(256)
        except socket.timeout:
            if fail == True:
                print("Error no response recived from 33220A within timeout")   
                raise
            else:
                return ""
        return back

    def __del__(self):
        self.fg.close()

def showhelp():
    print("usage from command line:python setupFG_A3322A.py 200 30 .25 RAMP ON)")
    print("gives a 200Hz wave of peak to peak amplitude 30V , an offset of .25V and a RAMP shape")
if __name__ == "__main__":
    import setupFG_A33220A
    print(sys.argv)
    if (len(sys.argv) < 3):
        showhelp()
    else:
        freq=sys.argv[1]
        amp=sys.argv[2]
        if len(sys.argv) > 3:
            offset=sys.argv[3]
        else:
            offset="0.0"
        if len(sys.argv) > 4:
            shape=sys.argv[4]
        else:
            shape="SIN"
        if len(sys.argv) > 5:
            onoff=sys.argv[5]
        else:
            onoff="ON"

        fg=setupFG_A33220A.util(freq,amp,offset=offset,shape=shape,onoff=onoff)
        fg.set()


