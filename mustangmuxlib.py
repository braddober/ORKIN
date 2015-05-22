#
import sys, os, random, math, array, fractions, StringIO
from sys import argv
import matplotlib, corr, time, struct
#from tables import *
from scipy import optimize
#from numpy import *
#from datetime import date
import datetime as dt
from scipy.io import *
import scipy.signal as sps
#from numpy import *
import pylab as pl
import numpy as np
##from pylab import *

#sys.path.append('/export/home/egret/monctrl/umux')
# TO DO:
# fix the RFswitch code so that you can actually switch between ext and int LO and CLK, doesn't work now
# add turn off LO & CLK:  toggleLO() and toggleCLK()
# optimize tune.py atten setting by signal to noise
# flatten by transferring power to tones further from LO (tune.py too?)
# distribute IQ loop rotations randomly about 0 and 180 to preserve power
# add Q extraction code here
#
# Add toggleHEMT() code using telenet server on the iboot
# Implement re-try on timeout erros (perhaps in firmware rather than software)

# Modification History:
#   May2014 - ahy 
#      - added findRes definition to umuxlib so it would follow
#          the user manual
#      - added "polyorder" keyword to vna() 
#      - added definition for toggleHEMT(), but isn't workng yet
#      - added a "polyorder" keyword to findRes()
#      - added saveSweep() for writing out fdat, mags
#      - added stitchSweep() for better rough resonance detection
#      - added toggleFluxRamp() for turning on/off the flux ramp
#          with default values
#      - added saveFreqs() for simpler saving of default_freqs.txt
#      - added rootdir keyword to __init__ so that you don't need to
#          hardcode the tuning or roach directories back and forth when
#          switching between roaches
#   July2014 - ahy
#      - added some lines to set dmd_num_frames register under setNreadoutCh
#      - changed defaultNchRead from 64 to 36.
class util:
    def __init__(self,parent=None,rootdir="/data/raw"):
        # items user may need to configure
        ########################################################################################
        ########################################################################################
        self.rootdir='%s/'%rootdir #make sure theres a slash (double is okay)
        # these values depend on the firmware (bof) of interest
        self.bof="mba15_obs2d_2014_Jan_31_1052.bof"
        #self.bof="umux_demod_v18d_2013_Dec_17_0925.bof"
        #self.bof="umux_demod_v18b_2013_Dec_09_1203.bof"
        #self.bof="umux_demod_v14a_2013_Sep_05_1921.bof"
        self.swreg="startDAC"
        self.ddsShift = 154
        self.nFIRtaps = 26
        # these values depend on BW of the ADC/DAC and number of channels in firmware
        self.Nch=256
        self.sampleRate = 512e6
        self.chSampleRate = 1e6
        # these values depend on the version of umux chip, current values are for umux10b
        self.defaultNchRead=36     # this number must be divisible by 4 for QDR demod data
        #self.frmAmp=0.97           # default flux ramp amplitude that gives self.Nphi0 quanta
#        self.frmAmp=0.139          # for 1077ohm bias resistors
        self.frmAmp=0.5          # for no warm res, 1077ohm cold resistor
        self.nPhi0=7.02              
        self.blankPeriod=0         # default samples to blank off in demod
        self.Minput=88e-12         # mutual inductance (H) of input coil and SQUID, umux10b
        self.Mfr=24e-12            # mutual inductance (H) of flux ramp and SQUID, umux10b 
        self.fluxRamp=[1000.,0.249,0,'ramp','on'] # default FR freq,amp,offset,wave,state
        self.atten_in=0.0 #set these to stop things crashing later
        self.atten_out=0.0
        ########################################################################################
        ########################################################################################
        # values unlikely to change
        self.LUTbuffer = 2**16
        self.freqRes = self.sampleRate/self.LUTbuffer
        self.f_offset = 0 # same as below?
        self.offset = 0
        self.dacStatus = 'off'
        self.dramStatus = 'off'
        self.RFset = '10110'
        self.attens = np.zeros([self.Nch])
        self.iq_rad=[0.]*self.Nch
        self.iq_centers=[0.j]*self.Nch

        # load in IP address of roach and set up katcp connection
        self.loadRoachIP()
        self.openClient(self.roachIP)

        # program the FPGA/DAC/ADC clock on the IF board
        print "programming clock..."
        self.progCLK()

        # program the firmware
        print "loading firmware..."
        self.loadCheckFirmware(self.bof)

    # begin definitions
    def loadRoachIP(self):
        'loadRoachIP()'

        f=open('%s/roachIP.txt'%self.rootdir)
        f.readline()
        f.readline()
        ipstr=f.readline()
        out=np.genfromtxt(StringIO.StringIO(ipstr),dtype=None,names=['roachNum','roachIP'],delimiter=' ')
        self.roachIP=out.tolist()[1]

    def openClient(self,roachIP):
        'openClient(roachIP)'
        'connect to roach via katcp'

        print 'connecting to roach: %s'%str(roachIP)
        self.roachIP=roachIP
        self.roach=corr.katcp_wrapper.FpgaClient(roachIP,7147,timeout=60)
        time.sleep(2)
        if self.roach.is_connected() == True:
            print "roach is connected"
        else:
            print "roach is not connected!"
        
    def loadCheckFirmware(self,bof):
        'loadCheckFirmware(bof)'
        'load bof file and check it is loaded in'

        # check to see if bof file exists on the roach
        bofs=self.roach.listbof()
        if str.find(str(bofs),bof) == -1:
            print "%s file does not exist in roach:/boffiles"%bof

        # check for an expected software register in main firmware program
        # if software reg is not there attempt to load in bof file
        regs=self.roach.listdev()
        if str.find(str(regs),self.swreg) == -1:
            self.roach.progdev(bof)
        # check to see it got loaded in
        regs = self.roach.listdev()
        if str.find(str(regs),self.swreg) == -1:
            print "%s firmware exists but is not loading. check file permissions "%bof

    def progRFswitches(self, regStr = '10010'):
        'progRFswitches(regStr[opt])'
        'default regStr = 10010'
        '5 bit word: LO_int/ext, RF_loop, LO_source(doubler), BB_loop, Ck_int/ext'
        'LOsrc:     0=ext, 1=int'
        'RFloop:    0=off, 1=on'
        'LOdbler:   0=on,  1=off'
        'BBloop:    0=on,  1=off'
        'CLKsrc:    0=int, 1=ext'

        # update self.RFset 
        self.RFset = regStr

        self.roach.write_int('regs', (1<<4)+(1<<3)+(0<<2)+(0<<1)+(0<<0))
        self.roach.write_int('if_switch', 1)
        
        self.roach.write_int('regs', (1<<4)+(1<<3)+(int(regStr[0])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(int(regStr[0])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(int(regStr[0])<<2)+(0<<1)+(0<<0))
        
        self.roach.write_int('regs', (1<<4)+(1<<3)+(int(regStr[1])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(int(regStr[1])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(int(regStr[1])<<2)+(0<<1)+(0<<0))
        
        self.roach.write_int('regs', (1<<4)+(1<<3)+(int(regStr[2])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(int(regStr[2])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(int(regStr[2])<<2)+(0<<1)+(0<<0))
        
        self.roach.write_int('regs', (1<<4)+(1<<3)+(int(regStr[3])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(int(regStr[3])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(int(regStr[3])<<2)+(0<<1)+(0<<0))        
        self.roach.write_int('regs', (1<<4)+(1<<3)+(int(regStr[4])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(int(regStr[4])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(int(regStr[4])<<2)+(0<<1)+(0<<0))

        # Now clock out the data written to the reg.
        self.roach.write_int('regs', (1<<4)+(1<<3)+(0<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(0<<2)+(0<<1)+(1<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(0<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(0<<2)+(0<<1)+(1<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(0<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(0<<2)+(0<<1)+(1<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(0<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(0<<2)+(0<<1)+(1<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(0<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(0<<2)+(0<<1)+(1<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(0<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(0<<2)+(0<<1)+(1<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(0<<2)+(0<<1)+(0<<0))
        self.roach.write_int('if_switch', 0)

    def progAttens(self, atten_in_desired, atten_out_desired):
        'progAttens(atten_in_desired,atten_out_desired)'
        'There are six attenuators in each chip with values of:'
        '-0.5, -1, -2, -4, -8, and -16  turned on/off with a 6 bit number'
        '"1"=off, "0"=on; there are two chips on the IF out and one on the IF in'

        if atten_in_desired > 31.5:
            atten_in_desired = 31.5
            print("WARNING: requested attenuation in greater than 31.5dB - defaulting to 31.5dB")
        atten_in = 63 - int(atten_in_desired*2)        
        self.atten_in = int(atten_in_desired*2)/2.0 #set atten_in to what is sent
        if atten_out_desired > 63 :
            atten_out_desired = 63
            print("WARNING: requested attenuation out greater than 63dB - defaulting to 63")
        if atten_out_desired <= 31.5:
            atten_out0 = 63
            atten_out1 = 63 - int(atten_out_desired*2)
        else:
            atten_out0 = 63 - int((atten_out_desired-31.5)*2)
            atten_out1 = 0
        self.atten_out = int(atten_out_desired*2)/2.0
        print(atten_in,atten_out0,atten_out1)
        reg = np.binary_repr((atten_in<<12)+(atten_out0<<6)+(atten_out1<<0))
        b = '0'*(18-len(reg)) + reg
        print(reg)
        self.roach.write_int('regs', (0<<4)+(1<<3)+(0<<2)+(0<<1)+(0<<0))
        self.roach.write_int('if_switch', 1)
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[0])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[0])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[0])<<2)+(0<<1)+(0<<0))

        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[1])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[1])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[1])<<2)+(0<<1)+(0<<0))
        
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[2])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[2])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[2])<<2)+(0<<1)+(0<<0))

        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[3])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[3])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[3])<<2)+(0<<1)+(0<<0))

        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[4])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[4])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[4])<<2)+(0<<1)+(0<<0))
        
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[5])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[5])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[5])<<2)+(0<<1)+(0<<0))
        
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[6])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[6])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[6])<<2)+(0<<1)+(0<<0))
        
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[7])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[7])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[7])<<2)+(0<<1)+(0<<0))
        
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[8])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[8])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[8])<<2)+(0<<1)+(0<<0))
        
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[9])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[9])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[9])<<2)+(0<<1)+(0<<0))
        
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[10])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[10])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[10])<<2)+(0<<1)+(0<<0))
        
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[11])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[11])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[11])<<2)+(0<<1)+(0<<0))
        
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[12])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[12])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[12])<<2)+(0<<1)+(0<<0))
        
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[13])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[13])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[13])<<2)+(0<<1)+(0<<0))
        
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[14])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[14])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[14])<<2)+(0<<1)+(0<<0))
        
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[15])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[15])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[15])<<2)+(0<<1)+(0<<0))
        
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[16])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[16])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[16])<<2)+(0<<1)+(0<<0))
        
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[17])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[17])<<2)+(1<<1)+(0<<0))
        self.roach.write_int('regs', (0<<4)+(1<<3)+(int(b[17])<<2)+(0<<1)+(0<<0))
        self.roach.write_int('regs', (1<<4)+(1<<3)+(0<<2)+(0<<1)+(0<<0))
        self.roach.write_int('if_switch', 0)

    def progCLK(self):
        'progCLK()'
        'program FPGA/DAC/ADC clock on IF board'

        self.roach.progdev('if_setup.bof')
        time.sleep(1)
        freq = self.sampleRate
        sweep_freq=0
        ref_division_factor=8
        f_pfd = 10e6/ref_division_factor
        f = freq
	
        INT = int(f)/int(f_pfd)
        MOD = 2000
        FRAC = int(round(MOD*(f/f_pfd-INT)))
        if FRAC != 0:
            gcd = fractions.gcd(MOD,FRAC)
            if gcd != 1:
		MOD = MOD/gcd
		FRAC = int(FRAC/gcd)

        PHASE = 1
        R = 1
        power = 3
        aux_power = 3
        MUX = 0
        LOCK_DETECT = 1
        PRESCALAR = 1 #4/5 mode f<3GHz
        CHARGE_PUMP_CURRENT_SETTING=7
        LDP=1 # 6 ns
        POLARITY=1 #positive
        ENABLE_RF_OUTPUT = 1
        ENABLE_AUX_OUTPUT = 1
        BAND_SELECT_CLOCK_DIVIDER=80
        FEEDBACK_SELECT=1  #fundamental
        DIVIDER_SELECT=3  # div factor = 8
        CLOCK_DIVIDER_VALUE=150
        DBB=1
        CTRL_BITS = [0,1,2,3,4,5]
        reg5 = (LOCK_DETECT<<22) + CTRL_BITS[5]
        reg4 = (FEEDBACK_SELECT<<23) +(DIVIDER_SELECT<<20)+ (BAND_SELECT_CLOCK_DIVIDER<<12) + (ENABLE_AUX_OUTPUT<<8) + (aux_power<<6) + (ENABLE_RF_OUTPUT<<5) + (power<<3) + CTRL_BITS[4]
        reg3 = (CLOCK_DIVIDER_VALUE<<3) + CTRL_BITS[3]
        reg2 = (MUX<<26) + (R<<14) + (CHARGE_PUMP_CURRENT_SETTING<<9) + (LDP<<7) + (POLARITY<<6) + CTRL_BITS[2]
        reg1 = (PRESCALAR<<27) + (PHASE<<15) + (MOD<<3) + CTRL_BITS[1]
        reg0 = (INT<<15) + (FRAC<<3)+CTRL_BITS[0]
        regs = [reg5, reg4, reg3, reg2, reg1, reg0]

        self.roach.write_int('CK_SLE', 1)
        self.roach.write_int('SER_DI', regs[0])
        self.roach.write_int('start', 1)
        time.sleep(.5)
        self.roach.write_int('start', 0)
        self.roach.write_int('CK_SLE', 0)
        
        self.roach.write_int('CK_SLE', 1)
        self.roach.write_int('SER_DI', regs[1])
        self.roach.write_int('start', 1)
        time.sleep(.5)
        self.roach.write_int('start', 0)
        self.roach.write_int('CK_SLE', 0)

        self.roach.write_int('CK_SLE', 1)
        self.roach.write_int('SER_DI', regs[2])
        self.roach.write_int('start', 1)
        time.sleep(.5)
        self.roach.write_int('start', 0)
        self.roach.write_int('CK_SLE', 0)

        self.roach.write_int('CK_SLE', 1)
        self.roach.write_int('SER_DI', regs[3])
        self.roach.write_int('start', 1)
        time.sleep(.5)
        self.roach.write_int('start', 0)
        self.roach.write_int('CK_SLE', 0)
        
        self.roach.write_int('CK_SLE', 1)
        self.roach.write_int('SER_DI', regs[4])
        self.roach.write_int('start', 1)
        time.sleep(.5)
        self.roach.write_int('start', 0)
        self.roach.write_int('CK_SLE', 0)

        self.roach.write_int('CK_SLE', 1)
        self.roach.write_int('SER_DI', regs[5])
        self.roach.write_int('start', 1)
        time.sleep(.5)
        self.roach.write_int('start', 0)
        self.roach.write_int('CK_SLE', 0)

    def progLO(self,loFreq):
        'progLO(loFreq)'
        'program LO on IF board'

        # determine if a RF doubling is in order
        if loFreq >= 4.4e9:
            # half the loFreq set point
            loFreq = loFreq/2
            # the 3rd value is the doubler, 0 = on
            if self.RFset[2] != '0':
                RFuse = self.RFset[0] + self.RFset[1] + '0' + self.RFset[3] + self.RFset[4]
                print "doubling LO"
                self.progRFswitches(RFuse)

        #print "setting LO to = %1.4f Hz" % loFreq
        f_pfd = 10e6
        INT = int(loFreq)/int(f_pfd)
        MOD = 2000
        FRAC = int(round(MOD*(loFreq/f_pfd-INT)))
        if FRAC != 0:
            gcd = fractions.gcd(MOD,FRAC)
            if gcd != 1:
                MOD = MOD/gcd
                FRAC = int(FRAC/gcd)
        PHASE = 1
        R = 1
        power = 3
        aux_power = 3
        MUX = 3
        LOCK_DETECT = 1
        reg5 = (LOCK_DETECT<<22) + (1<<2) + (1<<0)
        reg4 = (1<<23) + (1<<18) + (1<<16) + (1<<8) + (aux_power<<6) + (1<<5) + (power<<3) + (1<<2)
        reg3 = (1<<10) + (1<<7) + (1<<5) + (1<<4) + (1<<1) + (1<<0)
        reg2 = (MUX<<26) + (R<<14) + (1<<11) + (1<<10) + (1<<9) + (1<<7) + (1<<6) + (1<<1)
        reg1 = (1<<27) + (PHASE<<15) + (MOD<<3) + (1<<0)
        reg0 = (INT<<15) + (FRAC<<3)
        
        regs = [reg5, reg4, reg3, reg2, reg1, reg0]
        
        for r in regs:
            self.roach.write_int('SER_DI', r)
            self.roach.write_int('LO_SLE', 1)
            self.roach.write_int('start', 1)
            self.roach.write_int('start', 0)
            self.roach.write_int('LO_SLE', 0)

    def defineLUTs(self):
        'defineLUTs()'

        if hasattr(self,'roach'):
            if hasattr(self,'freqs'):
                print 'Defining LUTs...'
                self.iq_centers = np.array([0.+0j]*self.Nch)
                self.define_DAC_LUT(self.freqs,self.loFreq)
                self.define_DDS_LUT(self.freqs,self.loFreq,self.ddsShift)
                binaryData=self.createLUTs()
                self.writeLUTs(binaryData)
                #if hasattr(self,'saveDir'):
                #    self.saveLUTs(binaryData,self.saveDir)
                #self.autoAdcRange()
                print "luts defined and loaded."
            else:
                print "Need to load Freq/Atten first"
        else:
            print "Need to connect to roach first"
    
    def autoAdcRange(self,ADC_max=1950,ADC_min=1000):
        'autoAdcRange() - adjusts the IF card input attenuator to'
        'attempt to get ADC count within a reasonable range'

        d_attens = 1.0 #step size to ramp attenuation in must be > 0.5
        print('Adjusting atten_in to bring ADC counts between '+str(ADC_min)+' and '+str(ADC_max))
        n_itter = 0
        while True :
            #self.progAttens(0,0)
            #print (self.atten_in,self.atten_out)
            self.progAttens(self.atten_in,self.atten_out)
            i,q = self.getSnapAdc()
            print 'got here'
            maxval = max(max(i),max(q),np.abs(min(i)),np.abs(min(q)))
            n_itter += 1
            if maxval > ADC_max :
                #print "over value"
                self.atten_in += d_attens
                if self.atten_in > 31.5:
                    self.atten_in = 31.5
                    #raise Exception('ERROR - power in is too great for attenuator to control')                    
                break
            if maxval < ADC_min:
                #print "under value"
                if self.atten_in < d_attens :
                    print('WARNING minimum input attenuation set and ADC counts are still low - extra power into the IF card may be needed')
                    break
                self.atten_in -= d_attens
                continue
            break
        if n_itter > 1 :
            print('Atten_in adjusted to :'+str(self.atten_in)+'dB')
        print('I,Q max = '+str(maxval))
            
        

    def freqCombLUT(self, freq, sampleRate, resolution, amplitude=[1.]*256, offset=0, phase=[0.]*256, random_phase = 'yes'):
        'freqCombLUT(freq,sampleRate,resolution,amplitude[opt],offset[opt],phase[opt],random_phase[opt])'

        amp_full_scale = 2**15-1
        size = int(sampleRate/resolution)
        I, Q = np.array([0.]*size), np.array([0.]*size)
        single_I, single_Q = np.array([0.]*size), np.array([0.]*size)
        #random.seed(1000)
        random.seed()
        for n in range(len(freq)):
            if random_phase == 'yes':
                phase[n] = random.uniform(0, 2*np.pi)

            x = [2*np.pi*freq[n]*(t+offset)/sampleRate+phase[n] for t in range(size)]
            y = [2*np.pi*freq[n]*t/sampleRate+phase[n] for t in range(size)]
            
            single_I = amplitude[n]*np.cos(x)
            single_Q = amplitude[n]*np.sin(y)

            I = I + single_I
            Q = Q + single_Q
        
        a = np.array([abs(I).max(), abs(Q).max()])
        I = np.array([int(i*amp_full_scale/a.max()) for i in I])
        Q = np.array([int(q*amp_full_scale/a.max()) for q in Q])
        return I, Q

    def reorderFreqs(self,freqs,loFreq):
        'reorderFreqs(freqs,loFreq)'

        freqsOut=list(freqs)
        for n in range(len(freqsOut)):
            if freqsOut[n] < loFreq:
                freqsOut[n] = freqsOut[n] + self.sampleRate
        return freqsOut
        
    def define_DAC_LUT(self,freqs,loFreq):
        'define_DAC_LUT(freqs,loFreq)'

        freqsOut=self.reorderFreqs(freqs,loFreq)
        self.freqs_dac = [round((f-loFreq)/self.freqRes)*self.freqRes for f in freqsOut]
        amplitudes = [10**(+(self.attens.min()-a)/20.) for a in self.attens]
        self.I_dac, self.Q_dac = self.freqCombLUT(self.freqs_dac, self.sampleRate, self.freqRes, amplitudes, self.offset)
        print 'done defining DAC freqs.'
        
    def define_DDS_LUT(self,freqs,loFreq,ddsShift,phase=[0.]*256):
        'define_DDS_LUT(freqs,loFreq,ddsShift,phase[opt])'

        fft_len=2**9
        freqsOut=self.reorderFreqs(freqs,loFreq)
        # this is pretty redundant with freqs_dac code block above
        # consider combining them
        freqs_dds = [0 for j in range(self.Nch)]
        for n in range(len(freqsOut)):
            freqs_dds[n] = round((freqsOut[n]-loFreq)/self.freqRes)*self.freqRes

        freq_residuals = self.select_bins(freqs_dds)

        L = int(self.sampleRate/self.freqRes)
        self.I_dds, self.Q_dds = [0.]*L, [0.]*L
        for m in range(self.Nch):
            I, Q = self.freqCombLUT([freq_residuals[m]], self.sampleRate/fft_len*2, self.freqRes, [1.], self.offset, [phase[m]], 'no')
            for j in range(len(I)/2):
                self.I_dds[j*512+2*((m+ddsShift)%self.Nch)] = I[2*j]
                self.I_dds[j*512+2*((m+ddsShift)%self.Nch)+1] = I[2*j+1]
                self.Q_dds[j*512+2*((m+ddsShift)%self.Nch)] = Q[2*j]
                self.Q_dds[j*512+2*((m+ddsShift)%self.Nch)+1] = Q[2*j+1]
        print "done defining dds freqs. "

    def select_bins(self,readout_freqs):
        'select_bins(readout_freqs)'

        fft_len = 2**9
        bins = ''
        i = 0
        residuals = []
        for f in readout_freqs:
            fft_bin = int(round(f*fft_len/self.sampleRate))
            fft_freq = fft_bin*self.sampleRate/fft_len
            freq_residual = round((f - fft_freq)/self.freqRes)*self.freqRes
            residuals.append(freq_residual)
            bins = bins + struct.pack('>l', fft_bin)
            self.roach.write_int('bins', fft_bin)
            self.roach.write_int('load_bins', (i<<1) + (1<<0))
            self.roach.write_int('load_bins', (i<<1) + (0<<0))
            i = i + 1
        return residuals

    def createLUTs(self):
        'createLUTs()'

        binaryData = ''
        for n in range(len(self.I_dac)/2):
            i_dac_0 = struct.pack('>h', self.I_dac[2*n])
            i_dac_1 = struct.pack('>h', self.I_dac[2*n+1])
            i_dds_0 = struct.pack('>h', self.I_dds[2*n])
            i_dds_1 = struct.pack('>h', self.I_dds[2*n+1])
            q_dac_0 = struct.pack('>h', self.Q_dac[2*n])
            q_dac_1 = struct.pack('>h', self.Q_dac[2*n+1])
            q_dds_0 = struct.pack('>h', self.Q_dds[2*n])
            q_dds_1 = struct.pack('>h', self.Q_dds[2*n+1])
            binaryData = binaryData + q_dds_1 + q_dds_0 + q_dac_1 + q_dac_0 + i_dds_1 + i_dds_0 + i_dac_1 + i_dac_0
        return binaryData

    def writeLUTs(self,binaryData):
        'writeLUTs(binaryData)'

        if self.dacStatus == 'off':
            # turn it off first
            self.roach.write_int('startDAC', 0)
        else:
            self.toggleDAC()
        self.roach.write('dram_memory', binaryData)
        # turn DAC back on
        self.toggleDAC()

    def saveLUTs(self,binaryData,saveDir):
        'saveLUTs(binaryData,saveDir)'

        # Write LUTs to file.
        fn=saveDir+'luts.dat'
        f = open(fn, 'w')        
        f.write(binaryData)
        f.close()
        os.chmod(fn, 0777)
        print 'LUTs saved in: ',saveDir

    def readLUTs(self,saveDir):
        'readLUTs(saveDir)'

        fn=saveDir+'luts.dat'
        f = open(fn, 'r')
        binaryData = f.read()
        f.close()
        return binaryData

    def translateLoops(self):
        if not hasattr(self,'iq_centers'):
            print 'Need to load Freq/Atten first'
            print "AttributeError: 'AppForm' object has no attribute 'iq_centers'"
        elif not hasattr(self,'roach'):
            print 'Need to connect to roach first'
            print "AttributeError: 'AppForm' object has no attribute 'roach'"
        else:
            print "Starting loop translation"
            centers=self.writeIQcenters()
            #if hasattr(self,'saveDir'):
            #    self.saveIQcenters(centers,self.saveDir)
            print "Done loop translations"

    def writeIQcenters(self):
        centers_for_file = [[0., 0.]]*self.Nch
        for ch in range(self.Nch):
            I_c = int(self.iq_centers[ch].real/2**2)
            Q_c = int(self.iq_centers[ch].imag/2**2)
            center = (I_c<<16) + (Q_c<<0)
            self.roach.write_int('centerIQ_centers', center)
            self.roach.write_int('centerIQ_load_centers', (ch<<1)+(1<<0))
            self.roach.write_int('centerIQ_load_centers', 0)
        
            centers_for_file[ch] = [self.iq_centers[ch].real, self.iq_centers[ch].imag]

        return centers_for_file

    def saveIQcenters(self,centers,saveDir):
        # get rid of this and save all center data in the freqs.txt file and load from that
        fn=saveDir+'centers.dat'
        savetxt(fn, centers)
        os.chmod(fn, 0777)

    def loadIQcenters(self,saveDir):
        fn=saveDir+'centers.dat'
        dat=loadtxt(fn)
        for ch in range(self.Nch):
            self.iq_centers[ch] = complex(dat[ch,0], dat[ch,1])

    def calcRcirc(pp,xx):
        # calculate the distance of each 2D points from the center (xc, yc)
        # pp = [xc,yc]  xx=[xdata,ydata]

        return ((xx[0]-pp[0])**2 + (xx[1]-pp[1])**2)**0.5

    def calcRerr(pp,xx):
        rr=self.calcRcirc(pp,xx)
        return rr-rr.mean()

    def findIQcenters(self, I, Q):
        # I, Q to center fitting for a single channel / IQ loop
        # fit circles to the IQ loops
        # initial guess for the circle centers
        fitfunc = lambda pp,xx:  ((xx[0]-pp[0])**2 + (xx[1]-pp[1])**2)**0.5
        errfunc = lambda pp,xx:  fitfunc(pp,xx)-np.mean(fitfunc(pp,xx))
        I,Q=np.squeeze(I),np.squeeze(Q)
        pp0=[np.mean(I),np.mean(Q)]
        xx=[I,Q]
        ppOut, success = optimize.leastsq(errfunc, pp0[:], args=(xx)) 
        Ic,Qc = ppOut
        rOut=fitfunc(ppOut,xx)
        R=rOut.mean()

        return complex(Ic, Qc), R

    def CalcRotateLoops(self):
        print "Calculating loop rotations..."
        phase = [0.]*self.Nch

        i,q = self.IQread()
        for n in range(self.Nfreqs):
            I = i[n] - self.iq_centers[n].real
            Q = q[n] - self.iq_centers[n].imag
            phase[n] = np.arctan2(Q, I)

        self.define_DDS_LUT(self.freqs,self.loFreq,self.ddsShift,phase)
        binaryData = self.createLUTs()
        self.writeLUTs(binaryData)
        #if hasattr(self,'saveDir'):
        #    self.saveLUTs(binaryData,self.saveDir)
        self.sweepLO(self.freqs,self.loFreq,self.loSpan,self.atten_in,self.atten_out)

    def rotateLoops(self,phase):
        print "Rotating IQ loops using given phase..."

        self.define_DDS_LUT(self.freqs,self.loFreq,self.ddsShift,phase)
        binaryData = self.createLUTs()
        self.writeLUTs(binaryData)
        #if hasattr(self,'saveDir'):
        #    self.saveLUTs(binaryData,self.saveDir)

    def checkDACstatus(self):
        if self.dacStatus == 'off':
            self.toggleDAC()

    def sweepLO(self,freqs,loFreq,loSpan,atten_in,atten_out,df=1e4):
        self.df = df
        steps = int(loSpan/df)
        #print "LO steps: ", steps
        lo_freqs = [loFreq+i*df-0.5*steps*df for i in range(steps)]

        #print(type(atten_out))
        if not isinstance(atten_out,(tuple,list)):
            atten_out = (atten_out,)
            #print("python is fucking stupid")
        attens = np.sort(atten_out)
        self.attens = attens
        #print(type(atten_out))

        self.I = np.zeros([self.Nfreqs,steps,len(attens)])
        self.Q = np.zeros([self.Nfreqs,steps,len(attens)])
        for jj in range(len(attens)):
            #print "output atten = ",attens[jj]
            self.progAttens(atten_in,attens[jj])
            time.sleep(0.5)
            f_span = []
            l = 0
            self.f_span = [[0]*steps]*self.Nfreqs
            for f in freqs:
                f_span = f_span + [f-0.5*steps*df+n*df for n in range(steps)]
                self.f_span[l] = [f-0.5*steps*df+n*df for n in range(steps)]
                l = l + 1
            for ii in range(steps):
                self.progLO(lo_freqs[ii])
                time.sleep(0.01)
                self.I[:,ii,jj],self.Q[:,ii,jj] = self.IQread()

            # reset to original LO freq
            self.progLO(loFreq)

            # find IQ on resonance
            self.I_on_res, self.Q_on_res = [0.]*self.Nfreqs, [0.]*self.Nfreqs
            self.I_on_res, self.Q_on_res = self.IQread()
            # Find IQ centers, unless it's a power sweep
            for ii in range(self.Nfreqs):
                self.iq_centers[ii],self.iq_rad[ii] = self.findIQcenters(self.I[ii,:],self.Q[ii,:])
	
    def IQread(self):
        I = np.zeros(self.Nfreqs)
        Q = np.zeros(self.Nfreqs)
        self.roach.write_int('startAccumulator', 0)
        self.roach.write_int('avgIQ_ctrl', 1)
        self.roach.write_int('avgIQ_ctrl', 0)
        self.roach.write_int('startAccumulator', 1)
        data = self.roach.read('avgIQ_bram', 4*2*self.Nch)
        for j in range(self.Nfreqs):
            I[j] = struct.unpack('>l', data[4*j:4*j+4])[0]
            Q[j] = struct.unpack('>l', data[4*(j+self.Nch):4*(j+self.Nch)+4])[0]
        return I,Q
              
    def iq2phase(self,I,Q):
        phase=np.arctan2(Q,I)
        phase=np.unwrap(phase)
        return phase

    def iq2mag(self,I,Q):
        mag=(I**2+Q**2)**0.5
        return mag
      
    def toggleDAC(self):
        if self.dacStatus == 'off':
            if hasattr(self,'roach'):
                print "Starting DAC...",
                self.roach.write_int('startDAC', 1)
                time.sleep(1)
                ii=0
                dacIsOn=1
                while self.roach.read_int('DRAM_LUT_rd_valid') != 0:
                    self.roach.write_int('startDAC', 0)
                    time.sleep(0.5) #was 0.25
                    self.roach.write_int('startDAC', 1)
                    time.sleep(1)
                    print ".",
                    ii=ii+1
                    if(ii>100):
                        dacIsOn = 0
                        print "error trying to turn on DAC... DRAM_LUT_rd_valid not 0"
                        break #was exit changed by SS 2014-05-06
                print "done."
                if (dacIsOn):
                    self.dacStatus = 'on'
                    print 'DAC turned on'
            else:
                print 'Need to connect to roach first'
                print "AttributeError: 'AppForm' object has no attribute 'roach'"
        else:
            self.roach.write_int('startDAC', 0)
            self.dacStatus = 'off'
            print 'DAC turned off'

    def loadFreqsAttens(self,freqFile):
        'loadFreqsAttens(freqFile)'

        try:
            x=np.loadtxt(freqFile)
            self.Nfreqs=len(x)-1
            self.loFreq=x[0,0]*1.e9
            self.freqs=x[1:self.Nfreqs+1,1]*1.e9
            self.attens=x[1:self.Nfreqs+1,2]
        except IOError:
            print 'No such file or directory:',freqFile

    def saveFreqsAttens(self,loFreq,freqs,attens,freqFile):
        'saveFreqsAttens(loFreq,freqs,attens,freqFile)' 
        if loFreq >= min(freqs):
            loFreq = min(freqs)-1.0e7
        f=open(freqFile,'w')
        f.write('#lofreq(GHz) dummy dummy \n')
        f.write('%2.9f \t 0 \t 0 \n' %(loFreq/1.e9))
        f.write('#res freq(GHz)    relAtten \n')
#        for ii in range(self.Nfreqs): <- findRes() doesn't change Nfreqs
        for ii in range(len(freqs)):
            f.write('%i \t %2.9f \t %2.2f \n' %(ii,freqs[ii]/1.e9,attens[ii]))
        f.close()
        os.chmod(freqFile, 0777)

    def saveFreqs(self, freqs, freqFile=None,loFreq=None):
        if freqFile is None:
            freqFile=self.rootdir+'default_freqs.txt'
        if loFreq is None:
            self.loFreq=min(freqs)-10.e6
        f=open(freqFile,'w')
        f.write('#lofreq(GHz) dummy dummy \n')
        f.write('%2.9f \t 0 \t 0 \n' %(self.loFreq/1.e9))
        f.write('#res freq(GHz)    relAtten \n')
        for ii in range(len(freqs)):
            f.write('%i \t %2.9f \t %2.2f \n' %(ii,freqs[ii]/1.e9,0.0))
        f.close()
        os.chmod(freqFile, 0777)    
        
    def getRawPhase(self,ch):
        'rawPh=getRawPhase(ch)'
        'rawPh in radians'
        'record 2**11 samples of raw phase data for channel ch from BRAM'

        self.roach.write_int('ch_we', ch)
        L = 2**10
        self.roach.write_int('startSnap', 0)
        self.roach.write_int('snapPhase_ctrl', 1)
        self.roach.write_int('snapPhase_ctrl', 0)
        self.roach.write_int('startSnap', 1)
        time.sleep(0.001)
        bin_data_phase = self.roach.read('snapPhase_bram', 4*L)    
            
        phase = []
        for m in range(L):
            phase.append(struct.unpack('>h', bin_data_phase[m*4+2:m*4+4])[0])
            phase.append(struct.unpack('>h', bin_data_phase[m*4+0:m*4+2])[0])
        phase = np.array(phase)/2.**16*8.
        return phase

    def getRawPhaseLong(self,ch):
        'rawPh=getRawPhaseLong(ch)'
        'rawPh in radians'
        'record ?? samples of raw phase data for channel ch from QDR'

        self.roach.write_int('ch_we', ch)
        L = 2**10
        numQDRSamples=2**19
        numBytesPerSample=4
        nLongsnapSamples = numQDRSamples*2 # 2 16-bit samples per 32-bit QDR word
        self.roach.write_int('snapqdr_ctrl',0)
        self.roach.write_int('snapqdr_ctrl',1)
        addr=self.roach.read_int('snapqdr_addr')
        while (addr < 2**19-1):
            addr=self.roach.read_int('snapqdr_addr')
        self.roach.write_int('snapqdr_ctrl',0)
        qdr_data_str = self.roach.read('qdr1_memory',numQDRSamples*numBytesPerSample)            
        qdr_values = struct.unpack('>%dh'%(nLongsnapSamples),qdr_data_str)
        qdr_phase = np.array(qdr_values,dtype=np.float32)/2.**16*8.
        return qdr_phase

    def readDemodQDR(self):        
        "demodData=readDemodQDR()"
        "return demodulated data from QDR in radians"
        "data returned in Npt x Nch array"

        # warn if NchRead is not divisible by 4... data will be scrambled
        Nch=self.NchRead
        if(np.mod(Nch,4)!=0):
            print "NchRead is not divisible by 4! Data from QDR will be scrambled"

        numQDRSamples=2**19
        numBytesPerSample=4
        nLongsnapSamples = numQDRSamples*2 # 2 16-bit samples per 32-bit QDR word
        self.roach.write_int('dmd_demodqdr_ctrl',0)
        self.roach.write_int('dmd_demodqdr_ctrl',1)
        addr=self.roach.read_int('dmd_demodqdr_addr')
        while (addr < 2**19-1):
            addr=self.roach.read_int('dmd_demodqdr_addr')
        self.roach.write_int('dmd_demodqdr_ctrl',0)
        qdr_data_str = self.roach.read('qdr0_memory',numQDRSamples*numBytesPerSample)            
        qdr_values = struct.unpack('>%dh'%(nLongsnapSamples),qdr_data_str)
        Npt = int(np.floor(np.shape(qdr_values)[0]/Nch))
        qdr_array = np.reshape(qdr_values[0:Npt*Nch],[Npt,Nch])
        demodData = qdr_array / 2.**14 # fix_16_14 16b signed phase timestream in radians, i.e. +/-2**14 = +/-1rad
        return demodData

    def startDemod(self):
        'startDemod()'
        'send signal high to startDemod software registers'

        self.roach.write_int('dmd_startDemod',0)
        self.roach.write_int('dmd_startDemod',1)

    def genFIR(self,cutoffFreq):
        "generate FIR taps for demod block, keep stop band wide to minimize in-band ripple"
        from scipy import signal
        passEnd=cutoffFreq/self.chSampleRate/2.
        stopStart=0.45
        self.fir=signal.remez(self.nFIRtaps,[0,passEnd,stopStart,0.5],[1,0])

    def loadFIRdemod(self,lpfstr):
        Ntaps = self.nFIRtaps

        if(lpfstr == "self"):
            lpf = np.array(self.fir)*(2**11-1)
        elif(lpfstr == "none"):
            lpf = np.array([1.]+[0]*(Ntaps-1))*(2**11-1)
        elif(lpfstr == "250kHz"):
            # 26 tap, lpf, 250 kHz
            lpf = np.array([-0 , 0.000166959420533 , 0.00173811663844 , 0.00420937801998 , 0.00333739357391 , \
                         -0.0056305703275 , -0.0212738104942 , -0.0318529375832 , -0.0193635986879 , \
                          0.0285916612022 , 0.106763943766 , 0.18981814328 , 0.243495321192 , 0.243495321192 , \
                          0.18981814328 , 0.106763943766 , 0.0285916612022 , -0.0193635986879 , -0.0318529375832 , \
                          -0.0212738104942 , -0.0056305703275 , 0.00333739357391 , 0.00420937801998 , 0.00173811663844 , 0.000166959420533 , -0])*(2**11-1)
        elif(lpfstr == "125kHz"):
            # 26 tap, lpf, 125 kHz.
            lpf = np.array([0 , -0.000431898216436 , -0.00157886921107 , -0.00255492263971 , -0.00171727439076 , \
                         0.00289724121972 , 0.0129123447233 , 0.0289345497995 , 0.0500906370566 , 0.0739622085341 , \
                         0.0969821586979 , 0.115211955161 , 0.125291869266 , 0.125291869266 , 0.115211955161 , \
                         0.0969821586979 , 0.0739622085341 , 0.0500906370566 , 0.0289345497995 , 0.0129123447233 , \
                         0.00289724121972 , -0.00171727439076 , -0.00255492263971 , -0.00157886921107 , -0.000431898216436 , -0])*(2**11-1)
        elif(lpfstr == "5kHz"):
            # 25 tap, lpf, 5 kHz
            lpf = np.array([ 0.00569801,  0.00665005,  0.00945087,  0.01393768,  0.01984973, 0.02684343,  0.03451233,  \
                          0.04241075,  0.05007965,  0.05707335, 0.06298539,  0.06747221,  0.07027302,  0.07122507,  \
                          0.07027302, 0.06747221,  0.06298539,  0.05707335,  0.05007965,  0.04241075,  0.03451233,  \
                          0.02684343,  0.01984973,  0.01393768,  0.00945087, 0.00665005])*(2**11-1)

        for ch in range(self.Nfreqs):            
            for n in range(Ntaps/2):
                coeff0 = int(lpf[2*n])
                coeff1 = int(lpf[2*n+1])
                coeff0 = np.binary_repr(int(lpf[2*n]), 12)
                coeff1 = np.binary_repr(int(lpf[2*n+1]), 12)
                coeffs = int(coeff1+coeff0, 2)
                coeffs_bin = struct.pack('>l', coeffs)
                #register_name = 'FIR_b' + str(2*n) + 'b' + str(2*n+1)
                register_name = 'dmd_sincos_fir_bram_FIR_b' + str(2*n) + 'b' + str(2*n+1)
                self.roach.write(register_name, coeffs_bin)
                self.roach.write_int('dmd_sincos_fir_bram_FIR_load_coeff', (ch<<1) + (1<<0))
                self.roach.write_int('dmd_sincos_fir_bram_FIR_load_coeff', (ch<<1) + (0<<0))
                register_name1 = 'dmd_sincos_fir_bram_FIR1_b' + str(2*n) + 'b' + str(2*n+1)
                self.roach.write(register_name1, coeffs_bin)
                self.roach.write_int('dmd_sincos_fir_bram_FIR1_load_coeff', (ch<<1) + (1<<0))
                self.roach.write_int('dmd_sincos_fir_bram_FIR1_load_coeff', (ch<<1) + (0<<0))
                
        self.lpfTaps=lpf
        print 'done loading FIR filter'

    def setupFG(self,freq,amp,off,wave,out):
        'setupFG(frequency,amplitude,offset,waveform,output)'
        'frequency=in Hz (e.g. 10000.0)'
        'amplitude=in Vpp (e.g. 1.64)'
        'offset=in V (e.g. 0.0)'
        'waveform=[ramp,sine,dc,squ]'
        'output=[on,off]'
        os.system('/opt/local/bin/python2.7 setupFG.py %s %s %s %s %s'%(freq,amp,off,wave,out));

    def toggleFluxRamp(self,switch=0):
        if switch:
            print "Turning Flux Ramp ON"
            freq,amp,off,wave,out=self.fluxRamp
            self.setupFG(freq,amp,off,wave,out)
        else:
            print "Turning Flux Ramp OFF"
            self.setupFG(0,0,0,'ramp','off')
            
    def tune(self,plot2screen=True,saveplot=True):
        'tune(tunedir)'
        maxv = 0.4
        loSpanShort=1e6
        loSpanLong=2e6
        freqoff = 0.0
        f_num = 1
	voff=[i*maxv/10. for i in range(10)]
        rootdir=self.rootdir
        freqFile=self.rootdir + 'default_freqs.txt'
	t=dt.datetime.today()
    	saveDir="/home/scratch/sstanchf/M2_tunings/" + self.roachIP +"/" + t.strftime("%Y%m%d_%H:%M:%S") + "/"
	
	# if it doesn't exist create it   
	try:
    		os.stat(saveDir)
	except:
    		os.mkdir(saveDir)
                os.chmod(saveDir,0777)
                print "created new save directory " + saveDir 
	"""if(len(argv)<4):
    		plot2screen=0
	else:
    		plot2screen=argv[3]
	if(len(argv)<5):
    		saveplot=1
	else:
    		saveplot]=argv[4]
	if(len(argv)<6):
    		f_num=1
	else:s
    		f_num=arg[5]"""
	startTime=time.time()

	self.loadFreqsAttens(freqFile)
	self.freqs=self.freqs.copy()+freqoff
	# for 35 resonator tones the power is low enough to not saturate the
        # josephson junction, and atten_out = 0 is fine.  For fewer channels
        # the power per channel is higher and it may be necessary to optimize
        '''if len(self.freqs)>5:
    		atten_out=np.array([0])
	else:
    		atten_out=np.array([0,2,4,6,8,10,12,14,16,18,20])'''
        # Feb 29: want to try always optimizing atten_out since we now have 10dB
        # less cold attenuation on mux 1 & 4.
        atten_out = np.array([0,2,4,6,8,10,12,14,16,18,20,22,24])
        #override for now
        #atten_in=0
	#atten_out=array([0])
	print "using atten_out = %d, atten_in = %d"%(self.atten_out,self.atten_in)

	self.saveDir=saveDir
	self.loSpan=loSpanLong
	#self.atten_in=atten_in
	#self.atten_out=array([0])# don't do an atten sweep for first run through
        # program the output waveform LUT with the default freqs
        self.defineLUTs()
        # before starting make sure the flux ramp is off
        self.setupFG(0,0,0,'ramp','off')
        # make sure the centers are cleared out
        print "clearing centers..."
	self.iq_centers=[0.+0.j]*256
	self.translateLoops()

	#print um.freqs                                                                                                                                                                                                                             
	# do LO sweep at atten_out_start                                                                                                                                                                                                            
	print "LO sweep for s21 vs freq for rough resonance detection..."
	self.sweepLO(self.freqs,self.loFreq,loSpanShort,self.atten_in,self.atten_out)

	pl.figure(f_num); pl.clf();  f_num += 1
	# make a mag(s21) vs freq plot:                                                                                                                                                                                                             
	print "plotting s21 vs freq..."
	for ii in range(self.Nfreqs):
    		pl.semilogy(np.array(self.f_span[ii])/1.e+9, (self.I[ii,:]**2 + self.Q[ii,:]**2)**.5,'k.-');
	pl.axis('tight');
	ax=pl.gca(); xmin,xmax=ax.get_ylim();
	pl.semilogy([self.loFreq/1.e+9,self.loFreq/1.e+9],[xmin,xmax],'r--');
	pl.xlabel('freq (GHz)'); pl.ylabel('mag(s21)'); pl.draw(); pl.draw();
	pl.title('mag(S21) vs frequency');
	if plot2screen:
    		pl.show(block=False);
	if saveplot:
    		fn='%s/S21vFreq.png' %saveDir
		pl.savefig(fn)
    		os.chmod(fn,0777)
                print "saved plot " + fn
	# center the IQ loops on the origin                                                                                                                                                                                                         
	self.translateLoops()
	print "sweeping to verify roughly centered IQ loops..."
	self.sweepLO(self.freqs,self.loFreq,loSpanShort,self.atten_in,self.atten_out)
	if plot2screen:
    		pl.figure(f_num); f_num += 1
	pl.clf()
	for ii in range(self.Nfreqs):
    		pl.plot(self.I[ii,:],self.Q[ii,:],'k.-');
    		#plot(um.iq_centers[ii].real,um.iq_centers[ii].imag,'ro');                                                                                                                                                                              
        pl.xlabel('I (adu)'); pl.ylabel('Q (adu)'); pl.title('centered IQ loops'); pl.axis('equal'); pl.draw(); pl.draw()
        if plot2screen:
            pl.show(block=False);
        if saveplot:
            fn='%s/IQloops_centered.png' %saveDir
            pl.savefig(fn)
            os.chmod(fn,0777)
            print "saved plot " + fn
	# now set up atten settings with desired values for power sweeps                                                                                                                                                                            
	#self.atten=atten_out
	Noff=len(voff)
	Natt=1 #len(self.atten_out)
	Nch=self.Nfreqs
	Nfr=int(loSpanShort/self.df)

	Iall=np.zeros([Nch,Nfr,Natt,Noff])
	Qall=np.zeros([Nch,Nfr,Natt,Noff])
	print "doing power sweeps..."
	# Step in DC voltage up to max(voff)                                                                                                                          # For each voff value, sweep the LO through loFreq +/- loSpanShort/2
        # For each voff save an Nch X Nfreq X Natt X Noff array                                                                              
	for ii in range(Noff):
    		self.setupFG(0,0,voff[ii],'dc','on')
    		time.sleep(0.1)
    		self.sweepLO(self.freqs,self.loFreq,loSpanShort,self.atten_in,self.atten_out)
    		Iall[:,:,:,ii]=self.I
    		Qall[:,:,:,ii]=self.Q

	# tuning algorithm to select probe freq and power/atten                                                                                                                                                                                     # indices of Iall/Qall:  (ch,freq,atten,voff)                                                                                                                                                                                     
	# now there should only be signal in the ph direction, none in mag direction:                                                                                                                                                               
	ph=np.arctan2(Qall,Iall)   # in radians                                                                                                                                                                                               
	ph=np.unwrap(ph)
	mag=(Iall**2+Qall**2)**0.5

	# for each ch find the frequency cut that maximizes modulation depth                                                                                                                                                                        # actually we want to maximize signal to noise, signal=mod depth, noise=std(phase_timestream)                                                                                                                                               
	print "finding optimal readout freq for each channel..."
	mod=np.zeros([Nch,Natt,Nfr])
	for ii in range(Nch):
    		for jj in range(Natt):
        		for kk in range(Nfr):
            		# may want to fit instead if really noisy                                                                                                                                                                          
                            mod[ii,jj,kk]=ph[ii,kk,jj,:].max()-ph[ii,kk,jj,:].min()
		# fit response humps and choose best probe freq and atten
                # for now just use atten out = 0.  doesn''t seem to matter
                # use a parabolic fit for now.  doesn't really fit the model well
                # come up with another expression / model in the future                                                                                                                                                                                     
	print "determining resonant frequency and attenuation..."
	freqFits=np.zeros([Nch,Natt])
	modDepth=np.zeros([Nch,Natt])
	badRes=np.zeros([Nch])
	modThresh=0.3
	# the best method is probably fit a parabola over a small span near the peak                                                                                                                                                                
	fitfunc = lambda pp,xx:  pp[0]*(xx[0]-pp[1])**2 + pp[2]
	errfunc = lambda pp,xx:  fitfunc(pp,xx)-xx[1]
	ptrng=10   # +/- number of points around the max to use for p2 fit                                                                                                                                                                          
	# set up plot stuf                                                                                                                                                                                                                          
	nrow=9
	ncol=4
	fs=8
	xlims=[-0.5,0.5]
	ylims=[0,3]
	if plot2screen:
    		pl.figure(f_num); f_num += 1
	pl.clf()
	for ii in range(Nch):
    		for jj in range(Natt):
        		mxind=np.argmax(mod[ii,jj,:])
        		if mxind<ptrng:
            			print "warning! max response near boundary of sweep!"
            			mxind=ptrng
        		xx=[np.array(self.f_span[ii]), np.transpose(mod[ii,jj,:])]
        		xxx=[xx[0][(mxind-ptrng):(mxind+ptrng)],xx[1][(mxind-ptrng):(mxind+ptrng)]]
       			 # determine if the resonator doesn't respond to the flux ramp                                                                                                                                                                       
        		if np.max(xxx[1]) < modThresh:
            			badRes[ii]=1
        		# initial guess                                                                                                                                                                                                   
			pp0=[-1.e-12,np.mean(xxx[0]),np.max(xxx[1])] #p2 fit around range of res freq                                                                                                                                         
			ppOut,success=optimize.leastsq(errfunc, pp0[:], args=(xxx),maxfev=2000)
        		freqFits[ii,jj]=ppOut[1]
        		modDepth[ii,jj]=np.max(fitfunc(ppOut,xxx))
			# show response                                                                                                                                                                                                 
			pl.subplot(nrow,ncol,ii+1).plot((xx[0]-np.mean(xx[0]))/1.e+6,xx[1],'-');
        		# show fit                                                                                                                                                                                                      
			pl.subplot(nrow,ncol,ii+1).plot((xxx[0]-np.mean(xx[0]))/1.e+6,fitfunc(ppOut,xxx),'r-');
        		# show selected tone                                                                                                                                                                                          
			pl.subplot(nrow,ncol,ii+1).plot((freqFits[ii,jj]-np.mean(xx[0]))/1.e+6,xx[1][np.argmax(xx[1])],'gx');
        		ax=pl.gca();
        		#text(0.95,0.95,str(ii),'matplotlib',horizontalalignment='center',verticalalignment='center',transform = ax.transAxes)                                                                                             
			# indicate bad resonators                                                                                                                                                                                     
			if badRes[ii]:
            			pl.subplot(nrow,ncol,ii+1).plot([xlims[0],xlims[1]],[ylims[0],ylims[1]],'r-');
           			pl.subplot(nrow,ncol,ii+1).plot([xlims[0],xlims[1]],[ylims[1],ylims[0]],'r-');
        		if (ii != 32):
            			ax.yaxis.set_ticklabels(''); ax.xaxis.set_ticklabels('');
        		else:
            			ax.xaxis.label.set_fontsize(fs); ax.yaxis.label.set_fontsize(fs)
            			for tick in ax.xaxis.get_major_ticks():
                			tick.label1.set_fontsize(fs)
            			for tick in ax.yaxis.get_major_ticks():
                			tick.label1.set_fontsize(fs)
            			pl.xlabel('delta freq (MHz)',fontsize=fs); pl.ylabel('mod depth (rad)',fontsize=fs);
        		pl.ylim((ylims[0],ylims[1]));
        		pl.xlim((xlims[0],xlims[1]));

	pl.suptitle('mod depth vs probe frequency');
	pl.draw(); pl.draw()
	if plot2screen:
    		pl.show(block=False)
	if saveplot:
    		fn='%s/frmMagfit.png' %saveDir
    		pl.savefig(fn)
    		os.chmod(fn,0777)
                print "saved plot " + fn
	# find the attenuation setting that maximizes the modulation depth                                                                                                                                                                 
	freqUse=np.zeros([Nch])
	attenUse=np.zeros([Nch])
	for ii in range(Nch):
    		induse=np.argmax(modDepth[ii,:])
    		freqUse[ii]=freqFits[ii,induse]
    		# if the resonator doesn't respond to flux ramp                                                                                                                                                                       
		# set attenuation really high unless it's a dark SQUID or res                                                                                                                                                             
		# do this to preserve the output power of DAC.  DO THIS LATER!!!!                                                                                                                                                        
		attenUse[ii]=atten_out[induse]
	# now write these to a new freqs file                                                                                                                                                                                      
	freqFile=saveDir+'/tuned_freqs.txt'
	self.saveFreqsAttens(self.loFreq,freqUse,attenUse,freqFile)
        print "saved tuned freqs"
	# program these probe frequencies                                                                                                                                                                                                           # will need to modify this if we use individ atten                                                                                                                                                                         
	self.loadFreqsAttens(freqFile)
	# setting atten_out with minimum attenuation of group                                                                                                                                                                                       # do this so that the phase centers get properly corrected                                                                                                                                                                                  
	self.atten_out=np.array([self.attens.min()])
	self.progAttens(self.atten_in,self.atten_out)
	self.defineLUTs()

	# center each channel's flux ramp response IQ loops                                                                                                                                                                       
	self.rotTransFRM() # rotate and translate loops                                                                                                                                                                                               
	# confirm the tuning with flux ramp modulation                                                                                                                                                                                              # don't ramp flux ramp, step and sample to get periodicity                                                                                                                                                                 
	vfrm=[i*maxv/100. for i in range(100)]
	Ifrm=np.zeros([Nch,len(vfrm)])
	Qfrm=np.zeros([Nch,len(vfrm)])
	for ii in range(len(vfrm)):
    		self.setupFG(0,0,vfrm[ii],'ramp','on')
    		# don't go crazy, give the fg a minute to breath                                                                                                                                                                   
		time.sleep(0.1)
    		Ifrm[:,ii],Qfrm[:,ii]=self.IQread()
	phfrm=np.unwrap(np.arctan2(Qfrm,Ifrm))
	self.setupFG(0,0,0,'ramp','off')

	# plot the flux ramp response in a subplot panel otherwise it's a mess                                                                                                                                                     
	nrow=9
	ncol=4;
	fs=8
	ylims=[-1.5,1.5]
	xlims=[vfrm[0],vfrm[len(vfrm)-1]]
	if plot2screen:
    		pl.figure(f_num); f_num += 1
	pl.clf()
	for ii in range(self.Nfreqs):
    		#subplot(nrow,ncol,ii+1).plot(vfrm,phfrm[ii,:]-mean(phfrm[ii,:]));                                                                                                                                                 
		pl.subplot(nrow,ncol,ii+1).plot(vfrm,phfrm[ii,:])
    		#xlim((xlims[0],xlims[1]));                                                                                                                                                                                       
		pl.ylim((ylims[0],ylims[1]));
    		ax=pl.gca();
    		#title(str(ii));                                                                                                                                                                                                  
		if (ii != 32):
   			ax.yaxis.set_ticklabels(''); ax.xaxis.set_ticklabels('');
    		else:
        		ax.xaxis.label.set_fontsize(fs); ax.yaxis.label.set_fontsize(fs)
        		for tick in ax.xaxis.get_major_ticks():
            			tick.label1.set_fontsize(fs)
        		for tick in ax.yaxis.get_major_ticks():
            			tick.label1.set_fontsize(fs)
        		pl.xlabel('flux (V)',fontsize=fs); pl.ylabel('phase (rad)',fontsize=fs);
    		if badRes[ii]:
        		pl.subplot(nrow,ncol,ii+1).plot([xlims[0],xlims[1]],[ylims[0],ylims[1]],'r-');
        		pl.subplot(nrow,ncol,ii+1).plot([xlims[0],xlims[1]],[ylims[1],ylims[0]],'r-');
	pl.suptitle('flux ramp response at probe tone')
	pl.draw(); pl.draw()
	if plot2screen:
    		pl.show(block=False)
	if saveplot:
    		fn='%s/frmVphi.png' %saveDir
    		pl.savefig(fn)
    		os.chmod(fn,0777)
		print "saved plot " + fn
                # plot the flux ramp IQ loops and verify they are centered:                                                                                                                                                                
	if plot2screen:
		pl.figure(f_num); f_num += 1
	pl.clf()
	for ii in range(Nch):
    		pl.plot(Ifrm[ii,:],Qfrm[ii,:]);
	pl.xlabel('I (adu)'); pl.ylabel('Q (adu)'); pl.title('IQ flux ramp response')
	pl.axis('equal')
	#xlim([-150,150]); ylim([-150,150]);       
	pl.grid('on'); pl.draw(); pl.draw()
	if plot2screen:
    		pl.show(block=False)
	if saveplot:
    		fn='%s/frmIQ.png' %saveDir
    		pl.savefig(fn)
    		os.chmod(fn,0777)
                print "saved plot " + fn
	# need to at least load a flat filter                                                                                                                                                                                      
	if(0):
    		self.loadFIRcoeffs("none")

	# save data                                                                                                                                                                                                                
	savemat(saveDir+'tunedat.mat',{'voff':voff,'vfrm':vfrm,'Ifrm':Ifrm,'Qfrm':Qfrm,'mod':mod, \
                               'Iall':Iall,'Qall':Qall,'ph':ph,'mag':mag,'modDepth':modDepth, \
                               'badRes':badRes,'freqUse':freqUse,'attenUse':attenUse});

	# print time to tune:                                                                                                                                                                                                   
	print "system tuned in %i seconds" %int(time.time() - startTime)
	#self.loadFreqsAttens(tunedir+'/'+'tuned_freqs.txt')

    def retune(self,tunedir):
        'retune(tunedir)'
        'load in tuned_freqs.txt from specified tuning directory'
        'program LO and define LUTs, and then recenter and rotate FRM response'

        freqFile='%s/tuned_freqs.txt'%tunedir
        self.loadFreqsAttens(freqFile);
        self.progLO(self.loFreq);
        self.defineLUTs()
        self.rotTransFRM()

    def setupDemod(self,frmFreq,frmAmp,carFreqs='measure',clip=True,doFG=True):
        'carFreqs=setupDemod(frmFreq,frmAmp)'
        'frmFreq=in Hz (e.g. 20000.0)'
        'frmAmp=in Vpp (e.g. 1.64)'
        'carFreqs[opt]= "measure"[default] will determine the carFreqs'
        '             = array([256]) with user-specified values' 

        # input flux signals (besides FRM) will cause the phase to change
        # from frame to frame and so the carrier frequency will not be 
        # accurately determined from the raw phase data averaged over all frames
        print "input flux signals must be turned off!!!"

        self.frameRate=frmFreq
        if doFG:
            self.setupFG(frmFreq,frmAmp,0,'ramp','on')

        # unless the carFreqs are specified
        # record the raw phase timestreams for each channel
        # find the carrier frequencies for each
        if(carFreqs == 'measure'):
            return_carFreqs = True 
            carFreqs=np.zeros([self.Nch])
            sampPerFrame=self.getSampPerFrame(frmFreq);
            for ii in range(self.Nfreqs):
                ph=self.getRawPhaseLong(ii)
                dum,dum,carFreqs[ii]=self.calcLO(ph,sampPerFrame,frmFreq)
            if clip == True :
                mcf=np.median(carFreqs[carFreqs>0])
                ptsPerPhi0=self.chSampleRate/mcf # do a cut for bad frequencies
                low_cut=mcf*(ptsPerPhi0-4)/ptsPerPhi0
                high_cut=mcf*(ptsPerPhi0+4)/ptsPerPhi0 
                print("clipping frequencies outside ",low_cut,high_cut)
                carFreqs[carFreqs < low_cut] = mcf # set these to the median
                carFreqs[carFreqs > high_cut] = mcf
        else:
            return_carFreqs = False

        # output the average measured carrier frequency
        meanCarFreq=np.mean(carFreqs[carFreqs>0])
        print "the average measured carrier frequency is %4.1f Hz"%meanCarFreq
        # program firmware with carrier frequencies
        self.writeCarrierFreqs(carFreqs)       
        
        # set the blanking period to remove transient at beginning of flux ramp period
        self.roach.write_int('dmd_blank_period',self.blankPeriod)

        # load FIR filter with cutoff 50% higher than average carrier freq
        #self.loadFIRdemod('125kHz')  # default FIR taps that work
        self.genFIR(meanCarFreq*1.5)  # generate FIR taps and pass as self.fir
        self.loadFIRdemod('self')     # load FIR taps from self.fir

        # tell the Demod QDR how many channels to read out
        self.setNreadoutCh(self.defaultNchRead)
        if return_carFreqs:
            return carFreqs

    def ph2inputFlux(self,demodPhase):
        'inputFlux=ph2inputFlux(demodPhase)'
        'inputFlux in units of Phi_0'
        'convert demoduled phase timestream to input flux in units of flux quanta'
        # ahy - 06/11/14 - I think this is input flux in Wb not Phi_0
        inputFlux=demodPhase*2.0678e-15/2./np.pi
        return inputFlux

    def ph2inputCurr(self,demodPhase):
        'inputCurr=ph2inputCurr(demodPhase)'
        'inputCurr in units of A'
        'convert demoduled phase timestream to input current in A'

        inputFlux=self.ph2inputFlux(demodPhase)
        inputCurr=inputFlux/self.Minput
        return inputCurr

    def vna(self,fstart,fstop, polyorder=2, phase='no',df=1e4):
        'fdat,mag=vna(fstart,fstop)'
        'power discontinuities between tones is corrected as is DAC rolloff'
        'mag: 2nd order poly removed and rescaled to 0-1'

        self.loSpan=4e6
        # put in logic to make sure frequency comb is within +/-256MHz of lo
        # make sure we have no more than 256 channels
        self.loFreq=fstart-10e6
        fstart=np.floor(fstart/self.loSpan)*self.loSpan
        fstop=np.floor(fstop/self.loSpan)*self.loSpan
        self.Nfreqs=int((fstop-fstart)/self.loSpan)+1
        self.freqs=np.linspace(fstart,fstop,self.Nfreqs)
        self.attens=np.zeros([self.Nfreqs])
        # remove centering
        self.iq_centers=[0.j]*self.Nch
        self.translateLoops()
        # self.atten_in=0 keep these as they are
        # self.atten_out=([0])
        self.defineLUTs()
        self.sweepLO(self.freqs,self.loFreq,self.loSpan,self.atten_in,self.atten_out,df=df)
        fdat=[]
        mag=[]
        phi=[]
        delta=0.0
        next_phase=0.0
        for ii in range(self.Nfreqs):
            fdat.append(self.f_span[ii])
            #attempt to align tone discontinuities
            magdat=(self.I[ii,:]**2+self.Q[ii,:]**2)**0.5
            if phase=='yes':
                phasedat=np.unwrap(np.arctan2(self.Q[ii,:],self.I[ii,:]),axis=0)
                 #phi.append(phasedat) # replace with below stuff
                if (ii>0) : 
                    next_phase -= float(phasedat[0])
                phi.append(phasedat+next_phase)
                next_phase = 2.0*float(phasedat[len(phasedat)-1])-float(phasedat[len(phasedat)-2])
            if(ii>0):
                magdat=(self.I[ii,:]**2+self.Q[ii,:]**2)**0.5
                magdatprev=(self.I[ii-1,:]**2+self.Q[ii-1,:]**2)**0.5-delta
                magLast=float(magdatprev[len(magdat)-1])
                magFirst=float(magdat[0])
                delta=magFirst-magLast
            mag.append(magdat-delta)
        mag=np.reshape(mag,np.prod(np.shape(mag)))
        fdat=np.reshape(fdat,np.prod(np.shape(fdat)))
        if phase=='yes':
            phi=np.reshape(phi,np.prod(np.shape(phi)))
        if polyorder >= 0:
            # remove second-order polynomial and normalize to 0-1
            pp=np.polyfit(fdat,mag,polyorder)
            yfit=np.polyval(pp,fdat)
            scl=np.max(mag-yfit)-min(mag-yfit)
            #print scl
            if math.isnan(scl):
                print "ERROR: S21 IS ALL NaNs..."
                return fdat, np.zeros(len(fdat))
            mag=((mag-yfit)-min(mag-yfit))/scl
        if phase=='yes':
            return fdat, mag, phi
        else:
            return fdat, mag

    def acqFRMdat(self,Npt=100):
        'i,q=acqFRMdat(Npt[opt,def=100])'
        'get i,q data with slow flux ramp'
        
        # turn on a slow flux ramp to acquire i,q response
        self.setupFG(1,self.frmAmp,0,'ramp','on')

        i,q=np.zeros([Npt,self.Nfreqs]),np.zeros([Npt,self.Nfreqs])
        for ii in range(Npt): i[ii,:],q[ii,:]=self.IQread()

        # turn flux ramp off
        self.setupFG(0,0,0,'ramp','off')

        return i,q

    def plotFRMdat(self,iFRM,qFRM):
        'plotFRMdat(iFRM,qFRM)'
        'plot the acqFRMdat in the i,q plane'

        for ii in range(self.Nfreqs):
            pl.plot(iFRM[:,ii],qFRM[:,ii],'.');
        pl.axis('equal');
        pl.draw();

    def rotTransFRM(self):
        'rotTransFRM()'
        'translate and rotate flux ramp IQ response based on slow ramp'
        # AI: consider distributing around both 0 and 180 rotation randomly

        Npt=100
        i,q=np.zeros([Npt,self.Nfreqs]),np.zeros([Npt,self.Nfreqs])
        phase=[0.]*self.Nch

        # turn on a slow flux ramp to acquire i,q response
        self.setupFG(1,self.frmAmp,0,'ramp','on')

        # clear out centering and rotations
        self.rotateLoops(phase)
        self.iq_centers=[0.+0.j]*self.Nch
        self.translateLoops()

        i,q=self.acqFRMdat(Npt)
        for ii in range(self.Nfreqs):
            c,r=self.findIQcenters(i[:,ii],q[:,ii])
            ph=self.iq2phase(i[:,ii]-c.real,q[:,ii]-c.imag);
            phase[ii]=np.max(ph)-(np.max(ph)-np.min(ph))/2.

        # rotate
        self.rotateLoops(phase)

        # find the centers of the rotated data, and translate
        i,q=self.acqFRMdat(Npt)
        for ii in range(self.Nfreqs): 
            self.iq_centers[ii],self.iq_rad[ii]=self.findIQcenters(i[:,ii],q[:,ii])
        self.translateLoops()

        # turn flux ramp back off
        self.setupFG(0,0,0,'ramp','off')

        print "finished rotating and translating the FRM..."

    def getCenRad(self):
        "getCenRad()"
        "fills in self.iq_centers and self.iq_rad for all ch"

        i,q=self.acqFRMdat()

        for ii in range(self.Nfreqs):
            self.iq_centers[ii],self.iq_rad[ii]=self.findIQcenters(i[:,ii],q[:,ii])

    def writeCarrierFreqs(self,carrier_freqs):
        "writeCarrFreqs(carrier_freqs)"
        "write up to 256 18b carrier_freqs to a mux for demod"

        for ch in range(len(carrier_freqs)):
            freq = int(carrier_freqs[ch])
            self.roach.write_int('dmd_carrier_freq_mux_ch_freqs',freq)
            self.roach.write_int('dmd_carrier_freq_mux_load_ch_freqs', (ch<<1)+(1<<0))
            self.roach.write_int('dmd_carrier_freq_mux_load_ch_freqs', 0)

    def setNreadoutCh(self,NchRead):
        "setNreadoutCh(NchRead)"
        "set the number of channels to readout"
        "data returned only for channels 0 to NchRead-1"
        "since the qdr memory packs 4 samples together this needs to be divisible by 4"
        # added by ahy -07/08/14
        nch=NchRead
        dataBytes=2.
        counterBytes=4.
        numCounters=2.
        bram_size=8160.
        packetBytes=(counterBytes*numCounters)+(nch*dataBytes)
        numFrames=int(np.floor(bram_size/packetBytes))
        self.roach.write_int('dmd_num_frames',numFrames)
        # -- end additions by ahy -- #
        self.NchRead=NchRead
#        self.roach.write_int('channel_select',NchRead)
        self.roach.write_int('dmd_channel_select',NchRead)
        
        self.startDemod()

    def getSnapAdc(self):
        "i,q = getSnapAdc()"
        
        L = 2**10
        self.roach.write_int('start_snapAdc', 0)
        self.roach.write_int('snapAdc_ctrl', 1)
        self.roach.write_int('snapAdc_ctrl', 0)
        self.roach.write_int('start_snapAdc', 1)
        time.sleep(0.001)
        adc_lsb = self.roach.read('snapAdc_bram_lsb', 4*L)
        adc_msb = self.roach.read('snapAdc_bram_msb', 4*L)

        fmt='>h'
        i=[]; q=[];
        for m in range(L):
            i.append(struct.unpack(fmt,adc_msb[0+4*m:2+4*m]))
            i.append(struct.unpack(fmt,adc_msb[2+4*m:4+4*m]))
            q.append(struct.unpack(fmt,adc_lsb[0+4*m:2+4*m]))
            q.append(struct.unpack(fmt,adc_lsb[2+4*m:4+4*m]))
        return i,q

    def getSampPerFrame(self,frmFreq):
        "sampPerFrame=getSampPerFrame(frmFreq)"

        sampPerFrame=int(self.chSampleRate/frmFreq)
        return sampPerFrame

    def getNframes(self,tod,sampPerFrame):
        "nper=getNframes(tod,sampPerFrame)"

        nframes=len(tod)/sampPerFrame
        return nframes

    def stackTOD(self,tod,sampPerFrame):
        "tods=stackTOD(tod,sampPerFrame)"

        # stack tod, stop at largest divisible sampPerFrame
        nframes=self.getNframes(tod,sampPerFrame)
        tods=np.transpose(np.reshape(tod[0:nframes*sampPerFrame],[nframes,sampPerFrame]))
        return tods

    def defineLO(self,carrierFreq,sampPerFrame):
        "LOsin,LOcos=defineLO(carrierFreq,sampPerFrame)"
        "create LOsin and LOcos for demod for given carrier frequency"

        tt=np.array([ii/self.chSampleRate for ii in range(sampPerFrame)])
        LOsin=np.sin(2*np.pi*carrierFreq*tt)
        LOcos=np.cos(2*np.pi*carrierFreq*tt)
        return LOsin,LOcos

    def calcLO(self,tod,sampPerFrame,frmFreq):
        "LOsin,LOcos,carrierFreq=calcLO(tod,sampPerFrame,frmFreq)"
        "calculate LOsin, LOcos and carrier frequency from phase data"

        # input a stacked (Nperiods,sampPerFrame) tod
        tods=self.stackTOD(tod,sampPerFrame)
        toda=np.mean(tods,1)
        #new auto correlation method by srd 20140911
        ac=np.correlate(toda,toda,mode="full")
        mv=ac[0]
        for ii in np.arange(len(ac)-1):
            if mv < ac[ii]:
                max_ind = ii
                mv = ac[ii]
        first_min=max_ind
        for ii in (np.arange(len(ac)-max_ind-1)+max_ind):
            if mv > ac[ii]:
                first_min = ii
                mv = ac[ii]
        second_max=first_min
        for ii in (np.arange(len(ac)-first_min-1)+first_min):
            if mv < ac[ii]:
               second_max = ii
               mv = ac[ii]
        second_min=second_max
        for ii in (np.arange(len(ac)-second_max-1)+second_max):
            if mv > ac[ii]:
                second_min = ii
                mv = ac[ii]
        dt=[first_min-max_ind,second_max-first_min,second_min-second_max]
        carrierFreq=0.5/(np.mean(dt))*self.chSampleRate
        LOsin = (max(toda)-min(toda))/2.0*np.sin(2.0*np.pi*np.arange(len(toda))*carrierFreq/self.chSampleRate)+ np.mean(toda)
        LOcos = (max(toda)-min(toda))/2.0*np.cos(2.0*np.pi*np.arange(len(toda))*carrierFreq/self.chSampleRate)+ np.mean(toda)
        '''# method 0: fit a sine, extract only at fundamental
        fitfunc = lambda pp,tt:  pp[0]*sin(2*pi*pp[1]*tt+pp[2])+pp[3]
        errfunc = lambda pp,tt,yy:  fitfunc(pp,tt)-yy
        pp0=[max(toda)-min(toda),self.nPhi0*frmFreq,0,mean(toda)]
        tt=array([ii/self.chSampleRate for ii in range(len(toda))])
        ppOut, success = optimize.leastsq(errfunc, pp0[:], args=(tt,toda))
        # now create the sin and cos components
        ppOut[2]=0
        LOsin=fitfunc(ppOut,tt)
        ppOut[2]=pi/2
        LOcos=fitfunc(ppOut,tt)
        carrierFreq=ppOut[1]
        # calculate the mixing matrix
        mix=[sum(sinOut.*loA.sin) sum(loA.sin.*loA.cos); sum(loA.sin.*loA.cos) sum(loA.cos.*loA.cos)];'''
        return LOsin,LOcos,carrierFreq

    def demodTOD(self,tod,LOsin,LOcos):
        "phi=demodTOD(tod,LOsin,LOcos)"
        "phi in radians"
        sampPerFrame=len(LOsin)
        tods=self.stackTOD(tod,sampPerFrame)
        #V=[sum(repmat(LOsin,1,size(tods,2)).*tods);sum(repmat(LOcos,1,size(tods,2)).*tods)];
        phi=np.zeros([np.shape(tods)[1]])
        for ii in range(np.shape(tods)[1]):
            phi[ii]=np.arctan2(sum(LOsin*tods[:,ii]),sum(LOcos*tods[:,ii]))
        return phi

    def demodTODfilt(self,tod,LOsin,LOcos,lpfcutoff):
        "phi=demodTOD(tod,LOsin,LOcos,lpfcutoff)"
        # multiply, filter then blank transient (filter/res) and then sum
        #tods=self.stackTOD(tod,sampper)
        sampPerFrame=len(LOsin)
        nframes=getNframes(tod,sampPerFrame)
        losinall=repeat(LOsin,nframes)
        locosall=repeat(LOcos,nframes)

        phi=np.zeros([np.shape(tods)[1]])
        for ii in range(np.shape(tods)[1]):
            phi[ii]=np.arctan2(sum(LOsin*tods[:,ii]),sum(LOcos*tods[:,ii]))
        return phi

    #def findRes(self,freqs,mags, width=6e6,minsep=3e6, resband=3e5, hwhmcut=3, ampcut=0.5, polyorder=5):
    def findRes(self,freqs,mags, width=6e6,minsep=3e6, resband=3e5, hwhmcut=3, ampcut=0.5, polyorder=5, mfwid=3e6):
        """
        Calling sequence:
        freqs,mgoods=findRes(freqs,mags,width=6e6,minsep=3e6, resband=3e5, hwhmcut=3, ampcut=0.5)

        Finds resonances and then cuts out the bad ones

        Keywords:
        width = width of sliding window used to find local minima
        minsep = minimum separation demanded between resonators
        mfwid = median filtering width in Hz
        resband = expected maximum resonator bandwidth 
        hwhmcut = demanded cutoff for resonator hwhm -- NOT USED
        ampcut = demanded cutoff for resonator amplitude -- NOT USED
        polyorder = order of polynomial to subract before looking for resonances -- NOT USED
        """
        if (mfwid > 0.0):
            mfwchans=mfwid/(freqs[2]-freqs[1])
            # median filter requires an odd number of data points in the boxcar-
            if (mfwchans % 2 == 0):
                mfwchans += 1
            mfilt=sps.medfilt(mags,mfwchans)
            yvals=mags - mfilt
        else:
            yvals=mags
        ws=width/(freqs[2]-freqs[1])
        sepsamp=minsep/(freqs[2]-freqs[1]) 
        inds=[] 
        for i in np.linspace(1,len(mags)-2,len(mags)-2):
            if i < ws/2:
                max_sig=-np.std(yvals[0:i+ws/2])
            elif i > (len(mags)-ws/2):
                max_sig=-np.std(yvals[i-ws/2:len(mags)-1])
            else:
                max_sig=-np.std(yvals[i-ws/2:i+ws/2])
            if yvals[i] > max_sig: 
                continue
            if (yvals[i] < yvals[i-1] and yvals[i] < yvals[i+1]):
                if len(inds) >= 1:
                    if i-inds[-1] < sepsamp:
                        miny=min([yvals[i],yvals[inds[-1]]])
                        w=np.where(yvals==miny)[0]
                        inds[-1]=w
                        continue
                inds=np.r_[inds,i]
        inds=np.int64(inds)
        print "Found %s POTENTIAL resonances" %str(len(freqs[inds]))
        # preselect on 5sigma negative spikes
        z=yvals[inds]/self.mad(yvals)
        print " MAD ",self.mad(yvals)
        strongneg = ( z < -5.0)

        # step through pre-selected and fit lorentzians to each
        hwhmarr=np.zeros(len(inds))
        amparr=np.zeros(len(inds))
        for ii in range(len(inds)):
            strongneg[ii]
            if not strongneg[ii]:
                continue
            fc=freqs[inds[ii]]

            #print width.shape
            wtot=np.where((freqs > (fc-width/2)) & (freqs < (fc +width/2)))
            freg=freqs[wtot]; dat=mags[wtot];
            # determine background level from region outside fc+/-resband/2
            wbg=np.where((freg < (fc - resband/2)) | (freg > (fc + resband/2)))
            fbg=freg[wbg]; dbg=dat[wbg]
            m,c=np.polyfit(fbg,dbg,1)
            datsub=dat-(m*freg+c) # background subtracted data
            pbest=optimize.leastsq(self.lorentzianres,[100000.,-500.],args=(datsub,freg,fc),full_output=1)
            bestpar=pbest[0]
            hwhmarr[ii]=bestpar[0]
            amparr[ii]=bestpar[1]
        # select resonances with widths within roughly an order of magnitude of the median
        #  resonance width
        #wgood2=where( (hwhmarr > 0.3 * median(hwhmarr)) & (hwhmarr < 3.0*median(hwhmarr)))
        #wgood2=where((hwhmarr/std(hwhmarr) <= hwhmcut) & (abs((amparr))/std(amparr) >= ampcut))

        wgood = ( (hwhmarr > 0.3*np.median(hwhmarr)) & (hwhmarr < 3.0*np.median(hwhmarr)) &
                  strongneg)

        #pl.plot(freqs,yvals/self.mad(yvals))

        #pl.plot(freqs[inds[wgood]],z[wgood],'r*')
        #pl.plot(freqs[wgood],yvals[wgood],'r*')

        fgood=freqs[inds[wgood]]
        mgood=mags[inds[wgood]]
        #pl.plot(fgood,mgood,'r*')
        print "Found %s GOOD resonances" %str(len(fgood))
        return fgood, mgood
    
    def lorentzianres(self,p,data,x,cen): # fixed center
        numerator=(p[0]**2)
        denom=(x-cen)**2 +p[0]**2
        y=p[1]*(numerator/denom)
        err=data-y
        return err
    
    def mad(self,x,axis=None):
        # ignore precisely zero-deviation points for the case
        xm=np.median(x,axis)
        z=x-xm
        gi=np.where(z != 0.0)
        return np.median(np.absolute(z[gi]-xm),axis)

    def toggleHEMT(self,ipaddress="128.91.46.24",port=23):
        # needs to be finished, telnet isn't working (01may2014)
        # ipaddress = iBootBar IP address
        # port = 23
        tn=telnetlib.Telnet(ipaddress,port)
        tn.read_until("User Name:")
        tn.write("mustangboot\n")
        tn.read_until("Password:")
        tn.write("b00tb@r!\n")
        
    def saveSweep(self, freqs,mags,outfile="sweep.dat"):
        """
        saveSweep(freqs,mags,outfile="sweep.dat")
           Include path in outfile or else it will save to current
           working directory
        """
        f=open(outfile,'w')
        f.write('# Freqs (GHz)   S21 (norm\'d)')
        for ii in range(len(freqs)):
            f.write('%2.9f \t %2.5f \n' %(freqs[ii]/1e9,mags[ii]))
        f.close()

    def saveDemodData(self, demodData, outfile='tods.dat'):
            #f=open(outfile,'w')
            #for ii in range(len(demodData[:,0])):
            #    f.write('%2.5f \n'%,))
            #f.close()
        savetxt(outfile,demodData)

    def stitchSweep(self,fstart,fstop,saveraw=0):
        '''
        Examples:
        freqs,mgood=um.stitchSweep(5.3e9,5.7e9)
        freqs,mgood,fdat,mags=um.stitchSweep(5.3e9,5.7e9,saveraw=1)
        '''
        f1=fstart
        f2=np.mean([fstart,fstop])
        f3=fstop
        fdat1,mag1=self.vna(f1,f2)
        fdat2,mag2=self.vna(f2,f3)
        fr1,mg1=self.findRes(fdat1,mag1)
        fr2,mg2=self.findRes(fdat2,mag2)
        fr1=fr1[fr1<min(fr2)-2e6]
        mg1=mg1[0:len(fr1)]
        freqs=np.concatenate([fr1,fr2])
        mags=np.concatenate([mg1,mg2])
        print "Stitched and found %s resonances"%str(len(freqs))
        if saveraw!=0:
            fdat1=fdat1[fdat1<min(fdat2)]
            mag1=mag1[0:len(fdat1)]
            fraw=np.concatenate([fdat1,fdat2])
            mraw=np.concatenate([mag1,mag2])
            return freqs, mags, fraw, mraw
        else:
            return freqs,mags

    def checkTOD(self, fr=1e3,amp=0.25,res=3,offs=0):
        self.setupFG(fr,amp,offs,'ramp','on')
        nsamp=self.chSampleRate/fr
        ph=self.getRawPhaseLong(res)
        tods=self.stackTOD(ph,nsamp)
        return tods
       

# slightly modified to work stand-alone:
#  parses the roach "IP" from rootdir/roachIP.txt -
# BSM 11dec2014
def loadRoachIPstandAlone(rootdir):

    f=open('%s/roachIP.txt'%rootdir)
    f.readline()
    f.readline()
    ipstr=f.readline()
    out=np.genfromtxt(StringIO.StringIO(ipstr),dtype=None,names=['roachNum','roachIP'],delimiter=' ')
    roachIP=out.tolist()[1]
    
    return roachIP
 
def setupFGStandAlone(freq,amp,off,wave,out):
        'setupFG(frequency,amplitude,offset,waveform,output)'
        'frequency=in Hz (e.g. 10000.0)'
        'amplitude=in Vpp (e.g. 1.64)'
        'offset=in V (e.g. 0.0)'
        'waveform=[ramp,sine,dc,squ]'
        'output=[on,off]'
        os.system('/opt/local/bin/python2.7 setupFG.py %s %s %s %s %s'%(freq,amp,off,wave,out));

# start of stand-alone version of retune() 
def retuneSA(u,tunedir): 
    'retune(tunedir)'
    'load in tuned_freqs.txt from specified tuning directory'
    'program LO and define LUTs, and then recenter and rotate FRM response'

    freqFile='%s/tuned_freqs.txt'%tunedir
    u.loadFreqsAttens(freqFile);
    u.progLO(u.loFreq);
    u.defineLUTs()
    #self.rotTransFRM()
