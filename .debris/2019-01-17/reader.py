'''For reading file'''
from numpy import ones, convolve, log10, sqrt, arctan2
from scipy.fftpack import rfft, rfftfreq, irfft
from datetime import datetime
from operator import itemgetter

# moving average
def smooth(y, box_pts):
    box = ones(box_pts)/box_pts
    y_smooth = convolve(y, box, mode='same')
    return y_smooth

def FFT_deNoise(y, dx, noise_level, noise_filter=0.1):
    w = rfft(y)
    f = rfftfreq(len(y), dx)
    spectrum = w**2
    cutoff = spectrum < (spectrum.max()*noise_level*noise_filter)
    w2 = w.copy()
    w2[cutoff] = 0
    y_clean = irfft(w2)
    return f, spectrum, y_clean

# Analytics
def IQAP(datas):
    # Slicing datas into IQ-data
    IQdata = datas.reshape(len(datas)/2, 2)
    Idata, Qdata = IQdata[:,0], IQdata[:,1]
    yI, yQ = [float(i) for i in Idata], [float(i) for i in Qdata]
    Amp, Pha = [], []
    for i in zip(yI, yQ):
        Amp.append(20*log10(sqrt(i[0]**2 + i[1]**2)))
        Pha.append(arctan2(i[1], i[0])) # -pi < phase < pi
    return yI, yQ, Amp, Pha

def search_time(dictpaths, timestamp):
    '''timestamp = Year month day'''
    tstamp0 = [i[0] for i in dictpaths]
    timestamp = datetime.strptime(timestamp, '%Y %m %d')
    tstamplist = [datetime.strptime(i, '%a %b %d %H:%M:%S %Y') for i in tstamp0]
    timedistances = [abs(timestamp - x) for x in tstamplist]
    inearest, nearest = min(enumerate(timedistances), key=itemgetter(1))
    selectedP = dictpaths[inearest]
    return nearest, selectedP

def test_reader():
    from pyqum.instrument.logger import printTree, get_data, search_allpaths, goto_siblings

    return
