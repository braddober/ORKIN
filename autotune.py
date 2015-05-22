#!/usr/bin/env python2.7

from sys import argv
import sys, time
sys.path.append('/export/home/egret/monctrl/umux')
import umuxlib, os
from matplotlib.pyplot import *
from numpy import *

################################################## CONFIGURE AUTOTUNE  #######################################################

rootdir = '/export/home/egret/monctrl/dark_run'
vnaUpper = 5.6e9 #vna sweep upper bound
vnaLower = 5.35e9 #vna sweep lower bound
#REMOVE LINE saveraw = 1 #0 to find good resonances only, 1 saves raw vna sweep
plot2screen = 1 #0  save plots only to subdirectory, 1 to display plots as they are created
frFreq = 1000 #flux ramp frequency
frAmp = 0.249 #flux ramp amplitude
ch = 3
############################################### DO NOT EDIT BELOW THIS LINE #################################################

if (len(argv)>1):
	subDir = argv[1]
else:
	t=date.today()
	subDir = "tuning" + t.strftime("%Y%m%d")

saveDir = rootdir + "/" + subDir + "/" 

#if saveDir doens't exist, create it:
try:
	os.stat(saveDir)
except:
	os.mkdir(saveDir)
#print "save directory is set to: ", saveDir

if plot2screen:
	plot_win=10 # start with higher numbers so things don't get overwritten
#do VNA sweep
print "starting VNA sweep"
fdat, mag = self.vna(vnaLower,vnaUpper)
freqs,mgood = self.findRes(fdat,mag)
if plot2screen:
	pl.figure(plot_win)
	pl.clf()
	plot_win += 1
pl.plot (fdat,mag);
pl.plot(freqs,mgood,'*')
pl.xlabel('Frequency')
pl.ylabel('Magnitude(S21)')
pl.title('Resonant Frequencies')
if plot2screen:
	pl.show(block=False)
fn = '%s/van_sweep.png' %saveDir
pl.savefig(fn)

#save default frequencies
fn = '%s/found_freqs.txt' %rootdir
self.saveFreqsAttens(self.loFreq,freqs,zeros([len(freqs)]),fn)
print "found freqs saved"

#tune the umux
print "starting tuning"
self.tune(saveDir)
print "finished tuning"

#turn on flux ramp
print "turning on function generator at ", frFreq,"Hz ", frAmp,"V"
self.setupFG(frFreq,frAmp,0,'ramp','on')
#print "function generator is on"

#now get raw phase

print "getting raw phase"
ph=self.getRawPhase(ch)
#now get raw phase long
#print "now getting raw phase long"
phL=self.getRawPhaseLong(ch)
if plot2screen:
	pl.figure(plot_win)
	plot_win += 1
pl.plot (ph)
pl.plot (mean(self.stackTOD(phL, 1000*(1000/frFreq)),axis=1))
pl.xlabel('1MHz sample #')
pl.ylabel('raw phase (radians)')
pl.title('raw phase data (blue=raw phase, red=stacked average')
fn= '%s/rawphase' %saveDir
pl.savefig(fn)
if plot2screen:
	pl.show(block=False);

print "starting Demod"
self.setNreadoutCh(36)
c_freq_array = self.setupDemod(frFreq,frAmp)
print,c_freq_array

print "done!"



