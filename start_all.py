import umuxlib_demod as umuxlib
from numpy import *

out="/export/home/egret/monctrl/roachtests/"
freqFile="/data/raw/roach1/20140523_ch2/tuned_freqs.txt" #use old tunning file

#### START ROACH1 ######
r1=umuxlib.util(rootdir=out+"r1/",roach="mustangr1-1.gbt.nrao.edu")

r1.loadFreqsAttens(freqFile) 
r1.progLO(r1.loFreq)
r1.progAttens(0.0,0.0)
r1.defineLUTs()

r1.setNreadoutCh(36)
#r1.setupFG(1000,0.249,0,'ramp','on')
cfreq=zeros(r1.Nch) + 5000.0
r1.getRawPhase(3)
r1.setupDemod(1000,0.25,carFreqs=cfreq)

demod=r1.readDemodQDR()

#### START ROACH2 ########
r2=umuxlib.util(rootdir=out+"r2/",roach="mustangr1-2.gbt.nrao.edu")

r2.loadFreqsAttens(freqFile)
r2.progLO(r1.loFreq)
r2.progAttens(0.0,0.0)
r2.defineLUTs()

r2.setNreadoutCh(36)
#r1.setupFG(1000,0.249,0,'ramp','on')
cfreq=zeros(r2.Nch) + 5000.0
r2.getRawPhase(3)
r2.setupDemod(1000,0.25,carFreqs=cfreq)

####### START ROACH3 ###########

r3=umuxlib.util(rootdir=out+"r3/",roach="mustangr1-3.gbt.nrao.edu")

r3.loadFreqsAttens(freqFile)
r3.progLO(r3.loFreq)
r3.progAttens(0.0,0.0)
r3.defineLUTs()

r3.setNreadoutCh(36)
#r1.setupFG(1000,0.249,0,'ramp','on')
cfreq=zeros(r3.Nch) + 5000.0
r3.getRawPhase(3)
r3.setupDemod(1000,0.25,carFreqs=cfreq)

demod=r3.readDemodQDR()

####### START ROACH4 ##########

r4=umuxlib.util(rootdir=out+"r4/",roach="mustangr1-4.gbt.nrao.edu")

r4.loadFreqsAttens(freqFile)
r4.progLO(r1.loFreq)
r4.progAttens(0.0,0.0)
r4.defineLUTs()

r4.setNreadoutCh(36)
#r1.setupFG(1000,0.249,0,'ramp','on')
cfreq=zeros(r4.Nch) + 5000.0
r4.getRawPhase(3)
r4.setupDemod(1000,0.25,carFreqs=cfreq)

demod=r4.readDemodQDR()



demod=r1.readDemodQDR()



