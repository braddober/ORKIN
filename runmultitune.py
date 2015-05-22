
# demo program illustrating how to run the multi-threaded
#  initroaches() routine.
# 11dec2014 bsm

# this is a list of "root directories", one for each ROACH. it is assumed
#  that each directory has a file called roachIP.txt with accurate information.
rootlist=['/home/scratch/bmason/m2scr/roach1/','/home/scratch/bmason/m2scr/roach2/','/home/scratch/bmason/m2scr/roach3/','/home/scratch/bmason/m2scr/roach4/']

# bsm 13feb15 - the following does not work from ~lmonctrl/umuxsvn
#  b/c there is no umuxlib_demod
from multitune import initroaches

# initialize the clock and load firmware for each one.
#  routine returns a list 
ums=initroaches(rootlist)

# ums[0], ums[1] etc. now should act just like the instance of umux that
#  is returned by umuxlib.util().

