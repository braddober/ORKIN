
# non-interactive plotting example

from astropy.io import fits
import pylab as pl
import numpy as np
import sys

def showhelp():
   print "USAGE:"
   print "python makefitsplots.py /home/my/dir/myfilename.fits"
   print "makes a bunch of png plots in current working directory"
   print "called myfilename*png"

def doplots(fitsfile='./filea.fits'):


    # strip out the file name without path or suffix-
    fileroot=((fitsfile.split('/')[-1]).split('.fits'))[0]

    hdulist=fits.open(fitsfile)
    hdulist.info()
    hdr0=hdulist[0].header
    hdr1=hdulist[1].header

    print hdr0
    print hdr1

    # print out column names
    hdulist[1].columns

    fc=hdulist[1].data['frameCntr']
    cc=hdulist[1].data['clkCntr']
    mjd=hdulist[1].data['DMJD']
    dd=hdulist[1].data['data']

    # show dims of data array
    dd.shape

    pl.close()
    pl.figure(num=7,figsize=(4,5))
    pl.plot(fc,'.')
    pl.xlabel('Integration #')
    pl.ylabel('Frame Counter')
    pl.title(fileroot)
    pl.savefig(fileroot+'FC.png')

    pl.close()
    pl.plot(cc,'.')
    pl.xlabel('Integration #')
    pl.ylabel('Clock Counter')
    pl.title(fileroot)
    pl.savefig(fileroot+'CC.png')

    pl.close()
    pl.plot((mjd-np.min(mjd))*24.0*3600.0,'.')
    pl.xlabel('Integration #')
    pl.ylabel('MJD-min(MJD) [sec.]')
    pl.title(fileroot)
    pl.savefig(fileroot+'MJD.png')

    pl.close()

    nc=round((dd.shape[1])**(0.5))
    nr=np.ceil(float(dd.shape[1])/float(nc))
    nc=int(nc)
    nr=int(nr)

    pl.figure(num=9,figsize=(14,12))
    pl.subplot(nr,nc,1)
    pl.tight_layout(pad=1.25)
    for i in range(dd.shape[1]):
        pl.subplot(nr,nc,i+1)
        pl.plot(dd[:,i],'.')
        pl.xlabel('Integ#')
        pl.title('Ch'+str(i))
        # pl.ylabel('Ch'+str(i))
    pl.savefig(fileroot+'Data.png',pad_inches=0.75)
    pl.close()

    pl.figure(num=10,figsize=(14,12))
    pl.subplot(1,1,1)
    #pl.tight_layout(pad=1.25)
    for i in range(dd.shape[1]):
        pl.plot(dd[:,i],'.')
        pl.xlabel('Integ#')
        pl.title('Ch'+str(i))
       # pl.ylabel('Ch'+str(i))
        pl.savefig(fileroot+'Ch'+str(i)+'.png')
        pl.close()

if __name__=='__main__':
  if (len(sys.argv)==1):
      showhelp()
  else:
    doplots(fitsfile=sys.argv[1])

          
