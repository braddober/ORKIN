import matplotlib, corr, time, struct, numpy, math
import sys, os
from datetime import datetime
from ConfigParser   import ConfigParser

class TestPingPong:

    def __init__(self):

        self.numCounters = 2
        self.counterBytes = 4 #8
        self.counterCode = 'L' # 'Q'
        self.dataBytes = 2 #4
        self.dataCode = 'H' #'L'
        self.bram_size = 8160 # can only read 4080 at a time

        self.clk = 256000000 # Hz
        self.turnOverSeconds = 2**32 / self.clk # for 32-bit counter
        self.armTime = None
        self.maxCntr = None
        self.prevFrameCntr = None
        self.prevClockCntr = None
        self.prevResetTime = None
        self.checkForArm = False

        sub = 'dmd_'

        # input
        self.ttl_rate_reg = 'sim_flux_ttl_ttl_rate'
        self.num_packets_reg = '%snum_frames' % sub
        self.num_channels_reg = '%schannel_select' % sub #'num_chans'
        self.arm_reg = 'arm'

        # output
        self.bram0 = '%sPingPong_Shared_BRAM' % sub #'PingPong_Shared_BRAM'
        self.bram1 = '%sPingPong_Shared_BRAM1' % sub #'PingPong_Shared_BRAM1'
        self.switch_reg = '%sPingPong_switch_reg' % sub #'PingPong_switch_reg'
        self.switch_cnt_reg = '%sPingPong_switch_cnt_reg' % sub #'PingPong_switch_cnt_reg'
        self.sync_cntr = 'sync_cntr'

    def openClient(self, roachIP=None, roachPort=None):
        """ create FpgaClient connection to ROACH board """
        if roachIP is None:
            roachIP = self.roachIP
        if roachPort is None:
            roachPort = self.roachPort
        print "Connecting to roach", roachIP, "on port", roachPort
        self.roach = corr.katcp_wrapper.FpgaClient(roachIP, roachPort, timeout=60)
        time.sleep(2)
        self.is_connected = self.roach.is_connected()
        if not self.is_connected:
            print "Not connected to roach"

    def setup(self, nchans, nframes, bof = None):
        if bof is not None:
            self.roach.progdev(bof)
            time.sleep(1)
            print "Roach programmed.  Num devs: ", len(self.roach.listdev())
        self.setNumChannels(nchans)
        self.roach.write_int(self.num_channels_reg, nchans)
        self.roach.write_int(self.num_packets_reg, nframes)

        time.sleep(1)

        print "PingPong swithc in 1 sec: ", self.checkPingPongCntr()

    def checkPingPongCntr(self):

        r = self.switch_cnt_reg
        s = self.roach.read_uint(r)
        time.sleep(1)
        e = self.roach.read_uint(r)
        return s, e, e - s


    def computeReadSize(self):
        self.readBytes = self.numPackets * self.packetBytes


    def readPingPong(self):

        switch = self.roach.read_int(self.switch_reg)
        
        bram = self.bram1 if switch else self.bram0
        self.readBram(bram)

    
    def readBram(self, bram):
        zcntr = 25;
        self.computeReadSize()
        bs = self.roach.read(bram, self.readBytes)
        print "bs[:10]", bs[:10]
        print self.packetBytes
        offset = self.packetBytes
        cntrs = []
        frames = []
        prevFrame = None
        # parse each packet
        for i in range(self.numPackets):
            # read this packet's header and data
            start = i * offset
            c = self.counterBytes
            cntrBs = bs[start:start+c]
            frameCntr = struct.unpack('>%s' % self.counterCode, cntrBs)[0]
            frames.append(frameCntr)
            cntrBs = bs[start+c:start+c+c]
            clockCntr = struct.unpack('>%s' % self.counterCode, cntrBs)[0]
            cntrs.append(clockCntr)
            dataBs = bs[start+c+c:start+c+c+(self.numChannels*self.dataBytes)]
            data = struct.unpack('>%d%s' % (self.numChannels, self.dataCode), dataBs)
            print "  i: %d; frame: %e; clk: %e" % (i, frameCntr, clockCntr), data[:2], "..", data[-2:], zcntr, data[zcntr]

            # check for zero frame counter
            if prevFrame is not None:
                if abs(frameCntr - prevFrame) != 1:
                    print "\n***Frames jump by: %d" %  abs(frameCntr - prevFrame)
            prevFrame = frameCntr        
            if self.prevFrameCntr is None:
                self.prevFrameCntr = frameCntr
            if frameCntr < self.prevFrameCntr or frameCntr == 0:
                print "\n*** Frame Counter Reset: %d ***\n" % frameCntr

            # now look at the clock counter in the header and check
            # for roll overs and resets via arm
            if self.prevClockCntr is None:
                self.prevClockCntr = clockCntr
            if clockCntr < self.prevClockCntr:
                if self.prevResetTime is None:
                    self.prevResetTime = time.time()
                t = time.time()    
                print ""
                print "Clock Counter Reset: %e < %e, elapsed secs: %f" % (clockCntr, self.prevClockCntr, t - self.prevResetTime)
                print ""
                self.prevResetTime = t
                if self.checkForArm:
                    print "\nCHECK FOR ARM!!!!!!!\n"
                    self.checkForArm = False
                    elapsed = time.time() - self.armTime
                    print "elapsed secs since arm detected: %f" % elapsed
                    if elapsed < (self.turnOverSeconds/2):
                        # this must be a turnover due to the arm
                        ts0 = math.floor(self.armTime) + 1
                        print ts0
                        print  float(clockCntr)/self.clk
                        ts1 = ts0 + float(clockCntr)/self.clk
                        print "Arm at %f; This counter at time: %f" % (self.armTime, ts1)
                #if self.armTime is not None:
                    # how much time since the last arm?
                #    elapsed = time.time() - self.armTime
                #    if elapsed < 1:
                #        print "first packet since arm: ", cntr
            self.prevFrameCntr = frameCntr            
            self.prevClockCntr = clockCntr            
        diffFrames = numpy.diff(frames)
        print "frames diff by: ", set(sorted(diffFrames))
        diffCntrs = numpy.diff(cntrs)
        print "counters diff by: ", set(sorted(diffCntrs))

    def getNumChannels(self):
        ch = self.roach.read_uint(self.num_channels_reg)
        self.setNumChannels(ch)
        return ch

    def setNumChannels(self, numChannels):
        self.numChannels = numChannels
        self.packetBytes = (self.counterBytes * self.numCounters) + (self.numChannels * self.dataBytes)
        self.numPackets = int(math.floor(self.bram_size/self.packetBytes))

if __name__ == '__main__':

    rn1 = sys.argv[1] #'roach1.astro.upenn.edu'
    port = 7147
    #nchan = 36
    nchan=36

    pp = TestPingPong()
    pp.openClient(roachIP = rn1, roachPort=port)

    pp.setNumChannels(nchan)
    #print 'num chans: ', pp.getNumChannels()

    pp.setup(nchan,pp.numPackets)
    #pp.readPingPong()
    #pp.setup(64, 60, bof = 'mba15_obs2d_2014_Jan_31_1052.bof')
    pp.readPingPong()
    print pp.roach.read_int('dmd_num_frames')
    print pp.roach.read_int('dmd_channel_select')
    print pp.checkPingPongCntr()
    print 'est brd clk: ', pp.roach.est_brd_clk()

