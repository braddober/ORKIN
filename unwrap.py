import numpy as np

def phaseunwrap(data):
	'''unwraps the phase of one column of demodulated data'''
	previous = 0
	pi_addition = 0
	for ii,ph in enumerate(data):
		difference = abs(previous - ph)
		if difference > 1.:
			if previous < 0 and ph > 0:
				pi_addition -= np.pi
			if previous > 0 and ph < 0:
				pi_addition += np.pi
		data[ii] += pi_addition
		previous = ph
	return(data)

