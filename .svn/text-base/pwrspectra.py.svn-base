from numpy import *
from matplotlib.pyplot import *
import os


def plot_ps(demod_data,chunks=10,chan=-1,showPlot=True,savePlot="",frequency=1000.0,returnFreq=True,removeDC=True,plot_title="",scale=1.0):
    """
    routine for plotting power sepctra of demod data.
    takes data 
    """
    #self.d=demod_data
    if isinstance(demod_data,str) :
        demod = loadtxt(demod_data) #read in saved data
    else:
            #print "we got data again"
        demod=demod_data
        #print demod
    print "using a frequency of ",frequency," Hz for the sync signal"
    ndata=demod.shape[0]
    nchan=demod.shape[1]
    chunkpts=floor(ndata/chunks)-1
    if ((chunkpts % 2) != 0):
        nspecpts=(chunkpts+1)/2.0
    else:
        nspecpts=chunkpts/2 + 1
    freq = arange(nspecpts)/(chunkpts/frequency)
    print "Time stream is ",(ndata/frequency)," seconds (",ndata," points) long"
    print "dividing into chunks of ",(chunkpts/frequency), " seconds (",chunkpts,"points ) long"
    print "frequency resolution will be ",freq[1]," Hz"
    #print ndata,nchan,nspecpts,chunkpts
    #
    if chan < 0 :
        chan2plot=arange(nchan)
    else :
        chan2plot=chan
    print chan2plot
    if (showPlot == True) or (savePlot != ""):
        doPlot=True
        nXplot=2
        nYplot=ceil(len(chan2plot)/2.0)
        ii=1
        clf()
    else:
        doPlot=False
        
    pwrSpec = zeros((nspecpts,nchan))
    for cc in chan2plot:#main plotting loop
        if cc >= nchan:
            print("given channel number is greater than the number of channels in data")
            continue
        if removeDC :
            demod[:,cc] -= mean(demod[:,cc])
        onePS = zeros(nspecpts)
        low = 0
        high = chunkpts 
        for ccc in arange(chunks):
            #print "chunk",ccc," on det",cc
            onePS += abs(fft.rfft(demod[low:high,cc]))**2 * 2.0 #extra factor of 2 for sqrt Hz
            low += chunkpts + 1
            high += chunkpts + 1
        pwrSpec[:,cc] = sqrt( onePS/chunkpts/frequency/chunks ) * scale 
        if doPlot: 
            if (max(pwrSpec[1:-1,cc]) > 0.0):
            #print "plotting",ii,nXplot,nYplot
                subplot(nYplot,nXplot,ii).plot(freq[1:-1],pwrSpec[1:-1,cc])
                yscale("log")
                xscale("log")
                xlim([freq[1],freq[-1]])
                title( plot_title+" det %s" % cc)
            #ylabel("uphi_o/sqrt(Hz)")
            #xlabel("frequency")
            else:
                subplot(nYplot,nXplot,ii).plot([0,1],[0,1])
                title( plot_title+" det %s" % cc)
            ii += 1           
        if showPlot :
            show(block=False)
        if savePlot:
            savefig(savePlot)
            os.chmod(savePlot,0777)
    if returnFreq:
        return pwrSpec, freq
    else:
        return pwrSpec

if __name__ == "__main__":
    print("command line operation not yet suported") 
