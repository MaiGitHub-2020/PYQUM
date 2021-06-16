# region: Loading Modules
from colorama import init, Back, Fore
init(autoreset=True) #to convert termcolor to wins color
from os.path import basename as bs
from os.path import getmtime
myname = bs(__file__).split('.')[0] # This py-script's name

import requests, json, ast
from sqlite3 import IntegrityError
from flask import Flask, request, render_template, Response, redirect, Blueprint, jsonify, stream_with_context, g, session, abort
from werkzeug.security import check_password_hash
from numpy import array, unwrap, mean, trunc, sqrt, zeros, ones, shape, arctan2, int64, concatenate, transpose, arange, ndindex
from time import sleep, strptime, mktime 
from datetime import timedelta, datetime
from random import random
import numba as nb

from pyqum import get_db
from pyqum.instrument.dilution import bluefors
from pyqum.instrument.logger import address, get_status, set_status, set_mat, set_csv, clocker, mac_for_ip, lisqueue, lisjob, measurement, qout, jobsearch, set_json_measurementinfo
from pyqum.instrument.toolbox import cdatasearch, gotocdata, waveform
from pyqum.instrument.analyzer import IQAP, UnwraPhase, pulseresp_sampler, IQAParray
from pyqum.directive.characterize import F_Response, CW_Sweep, SQE_Pulse
from pyqum.directive.manipulate import Single_Qubit

# Memory handling
import concurrent.futures
executor = concurrent.futures.ProcessPoolExecutor(max_workers=1)

# Error handling
from contextlib import suppress

# Scientific Constants
from scipy import constants as cnst

# subprocess to cmd
from multiprocessing import Pool
from subprocess import Popen, PIPE, STDOUT
import os, signal

# endregion

__author__ = "Teik-Hui Lee"
__copyright__ = "Copyright 2019, The Pyqum Project"
__credits__ = ["Chii-Dong Chen"]
__license__ = "GPL"
__version__ = "beta3"
__email__ = "teikhui@phys.sinica.edu.tw"
__status__ = "development"

encryp = '/' + 'ghhgjad'
bp = Blueprint(myname, __name__, url_prefix=encryp+'/mssn')

# region: PENDING: Some Tools for Fast Parallel Calculations:
def scanner(a, b):
    for i in a:
        for j in b:
            yield i, j
def worker(y_count,x_count,char_name="sqepulse"):		
    pool = Pool()
    IQ = pool.map(eval("assembler_%s" %(char_name)), scanner(range(y_count),range(x_count)), max(x_count,y_count))
    pool.close(); pool.join()
    rI, rQ, rA, rP = [], [], [], []
    for i,j,k,l in IQ:
        rI.append(i); rQ.append(j); rA.append(k); rP.append(l)
    rI, rQ, rA, rP = array(rI).reshape(y_count,x_count).tolist(), array(rQ).reshape(y_count,x_count).tolist(),\
                     array(rA).reshape(y_count,x_count).tolist(), array(rP).reshape(y_count,x_count).tolist()
    return {'rI': rI, 'rQ': rQ, 'rA': rA, 'rP': rP}
# endregion
    
# region: Main
@bp.route('/')
def show(status="Mission started"):
    # Filter out Stranger:
    with suppress(KeyError):
        print(Fore.LIGHTBLUE_EX + "USER " + Fore.YELLOW + "%s [%s] from %s "%(session['user_name'], session['user_id'], request.remote_addr) + Fore.LIGHTBLUE_EX + "is trying to access MISSION" )
        # Check User's Clearances: (Analysis is merged into measurement level-1)
        if not g.user['measurement']: # TOTAL NULL
            print(Fore.RED + "Please check %s's Clearances for measurement!"%session['user_name'])
            abort(404)
        else: print(Fore.LIGHTBLUE_EX + "USER " + Fore.YELLOW + "%s [%s] "%(session['user_name'], session['user_id']) + Fore.LIGHTBLUE_EX + "has entered MISSION" )
        return render_template("blog/msson/mission.html", status=status)
    return("<h3>WHO ARE YOU?</h3><h3>Please Kindly Login!</h3><h3>Courtesy from <a href='http://qum.phys.sinica.edu.tw:%s/auth/login'>HoDoR</a></h3>" %get_status("WEB")["port"])
# endregion

# region: ALL
@bp.route('/all', methods=['GET'])
def all(): 
    global systemlist
    systemlist = [x['system'] for x in get_db().execute('SELECT system FROM queue').fetchall()]
    if g.user:
        if int(g.user['measurement']): # 0: Preview, 1: Analysis, 2: Running, 3: SOP
            try: 
                queue = get_status("MSSN")[session['user_name']]['queue']
            except: 
                queue = '' # For first-time user to pick a queue to begin with
            print(Fore.GREEN + "Queue '%s' was selected previously" %queue)
        else:
            print(Fore.RED + "User %s has ZERO Measurement Clearance" %g.user['username'])
            abort(404)
    else:
        return("<h3>WHO ARE YOU?</h3><h3>Please Kindly Login!</h3><h3>Courtesy from <a href='http://qum.phys.sinica.edu.tw:%s/auth/login'>HoDoR</a></h3>" %get_status("WEB")["port"])
    return render_template("blog/msson/all.html", systemlist=systemlist, queue=queue)
@bp.route('/all/job', methods=['GET']) # PENDING: horizontal tabs for different Quantum Universal Machines in the future
def all_job():
    g.jobidlist = {}
    try: 
        for q in systemlist: g.jobidlist[q] = []
    except: 
        return("<h3>SERVER HAS BEEN REFRESHED</h3><h3>Please press F5 to reload.</h3><h3 style='color:blue;'>Courtesy from HoDoR</h3>")
        
    queue = request.args.get('queue')
    try: missioname = get_db().execute( "SELECT mission FROM queue WHERE system = ?", (queue,) ).fetchone()['mission']
    except: missioname = None
    # print("mission: %s" %missioname)
    owner, samplename = session['people'], get_status("MSSN")[session['user_name']]['sample']
    
    maxlist = 88
    joblist = lisjob(samplename, queue, maxlist) # job is listed based on sample & queue only

    # LOG Calculated Progress interactively into SQL-Database for fast retrieval
    for j in joblist:
        # print("Progress: %s" %j['progress'])
        # print("j.tag: %s" %j['tag'])
        if (j['tag'] == "") and (j['id'] not in g.jobidlist[queue]) and (j['progress'] is None or j['progress'] < 100): # not allowing queued-job to be accessed to avoid database locks
            try:
                meas = measurement(mission=missioname, task=j['task'], owner=owner, sample=samplename) # but data is stored according to the owner of the sample
                meas.selectday(meas.daylist.index(j['dateday']))
                meas.selectmoment(j['wmoment'])
                meas.accesstructure()
                j['progress'] = meas.data_progress
                db = get_db()
                db.execute('UPDATE job SET progress = ? WHERE id = ?', (j['progress'],j['id']))
                db.commit()
            except(ValueError): j['progress'] = 0 # for job w/o its bag yet
            except(TypeError): return("<h3>RE-LOGIN DETECTED</h3><h3>Please press <USERNAME> on TOP-RIGHT to proceed.</h3><h3 style='color:blue;'>Courtesy from HoDoR</h3>")

    # Security:
    try: print(Fore.GREEN + "User %s is accessing the jobs" %g.user['username'])
    except: abort(404)
    return jsonify(loginuser=session['user_name'], joblist=joblist, samplename=samplename)
@bp.route('/all/queue', methods=['GET']) # PENDING: horizontal tabs for different Quantum Universal Machines in the future
def all_queue():
    queue = request.args.get('queue')
    set_status("MSSN", {session['user_name']: dict(sample=get_status("MSSN")[session['user_name']]['sample'], queue=queue)})
    lisqueue(queue)

    # TO QUEUE-IN, the assigned sample for that queue-system (by admin) MUST be aligned with the sample chosen (MEAL):
    try: asample = get_db().execute( '''SELECT samplename FROM queue WHERE system = ?''', (queue,) ).fetchone()['samplename'] # assigned sample by admin
    except(TypeError): asample = ''
    session['run_clearance'] = bool( asample==get_status("MSSN")[session['user_name']]['sample'] and int(g.user['measurement'])>1 )

    # Security:
    try: print(Fore.YELLOW + "CHECKING OUT QUEUE for %s: %s" %(queue,g.Queue[queue]))
    except: abort(404)
    return jsonify(QUEUE=g.Queue[queue], loginuser=session['user_name'])
@bp.route('/all/queue/out', methods=['GET'])
def all_queue_out():
    '''THIS IS ALSO PURPOSED TO STOP THE MEASUREMENT, EFFECTIVELY REPLACING THE PAUSE BUTTON & PAUSE-LOG FOR CERTAIN TASK!'''
    queue = request.args.get('queue')
    JID = request.args.get('JID')
    message = qout(queue,JID,g.user['username'])
    # Prevent unsolicited visit:
    if queue is None: abort(404)
    return jsonify(message=message)
@bp.route('/all/access/job', methods=['GET'])
def all_access_job():
    jobid = request.args.get('jobid')
    tdmpack = jobsearch(jobid, mode='tdm')
    # Prevent unsolicited visit:
    if jobid is None: abort(404)
    return jsonify(tdmpack=dict(tdmpack))
@bp.route('/all/requeue/job', methods=['GET'])
def all_requeue_job():
    if session['run_clearance']:
        jobid = request.args.get('jobid')
        requeue = jobsearch(jobid, mode='requeue')
        if requeue['task'] == "F_Response":
            print(Fore.YELLOW + "Requeue F_Response for JOB#%s" %jobid)
            F_Response(session['people'], corder=ast.literal_eval(requeue['parameter']), comment=requeue['comment'], tag=requeue['tag'], dayindex=-1, perimeter=ast.literal_eval(requeue['perimeter']))
        elif requeue['task'] == "CW_Sweep":
            print(Fore.YELLOW + "Requeue CW_Sweep for JOB#%s" %jobid)
            CW_Sweep(session['people'], corder=ast.literal_eval(requeue['parameter']), comment=requeue['comment'], tag=requeue['tag'], dayindex=-1, perimeter=ast.literal_eval(requeue['perimeter']))
        elif requeue['task'] == "Single_Qubit":
            print(Fore.YELLOW + "Requeue Single_Qubit for JOB#%s" %jobid)
            Single_Qubit(session['people'], corder=ast.literal_eval(requeue['parameter']), comment=requeue['comment'], tag=requeue['tag'], dayindex=-1, perimeter=ast.literal_eval(requeue['perimeter']))

        else: print(Fore.RED + "UNKNOWN TASK: %s" %requeue['task'])
        clearance = True
    else: 
        requeue = {}
        clearance = False
    return jsonify(requeue=requeue, clearance=clearance)
# endregion

# region: CHAR:
@bp.route('/char', methods=['GET'])
def char(): 
    print(Fore.BLUE + 'User %s is allowed to run measurement: %s'%(g.user['username'],session['run_clearance']))
    samplename = get_status("MSSN")[session['user_name']]['sample']
    print(Fore.YELLOW + "sample %s is managed by %s" %(samplename, session['people']))
    return render_template("blog/msson/char.html", samplename=samplename, people=session['people'])
# endregion

# region: CHAR -> 1. F-Response ============================================================================================================================================
# FRESP Security layer:
frespcryption = 'hfhajfjkafh'

@bp.route('/char/' + frespcryption + '/', methods=['GET'])
def char_fresp(): 
    return render_template("blog/msson/char/fresp.html")
# Initialize and list days specific to task
@bp.route('/char/' + frespcryption + '/init', methods=['GET'])
def char_fresp_init(): 
    global M_fresp, fresp_1Ddata, fresp_2Ddata
    try: print(Fore.GREEN + "Connected F-Resp M-USER(s): %s" %M_fresp.keys())
    except: M_fresp = {}
    M_fresp[session['user_name']] = F_Response(session['people']) # Allowing Measurement and Access (Analysis) to be conducted independently
    print(Fore.BLUE + Back.WHITE + "User %s is looking at %s's data" %(session['user_name'],session['people']))
    
    # Initialize 1D Data-Holder:
    try: print(Fore.CYAN + "Connected M-USER(s) holding F-Response's 1D-DATA: %s" %fresp_1Ddata.keys())
    except: fresp_1Ddata = {}
    # Initialize 2D Data-Holder:
    try: print(Fore.CYAN + "Connected M-USER(s) holding F-Response's 2D-DATA: %s" %fresp_2Ddata.keys())
    except: fresp_2Ddata = {}

    return jsonify(daylist=M_fresp[session['user_name']].daylist, run_permission=session['run_clearance'])
# list task entries based on day picked
@bp.route('/char/' + frespcryption + '/time', methods=['GET'])
def char_fresp_time():
    wday = int(request.args.get('wday'))
    M_fresp[session['user_name']].selectday(wday)
    return jsonify(taskentries=M_fresp[session['user_name']].taskentries)

# NEW measurement setup
@bp.route('/char/' + frespcryption + '/new', methods=['GET'])
def char_fresp_new():
    # Check user's current queue status:
    if session['run_clearance']:
        # set_status("F_Response", dict(pause=False)) # PENDING: is this the right place???
        global Run_fresp, TOKEN # need to be removed in the future for security sake
        Run_fresp = {}
        wday = int(request.args.get('wday'))
        print("wday: %s" %wday)
        fluxbias = request.args.get('fluxbias')
        sparam = request.args.get('sparam')
        ifb = request.args.get('ifb')
        powa = request.args.get('powa')
        freq = request.args.get('freq')
        comment = request.args.get('comment').replace("\"","")
        simulate = bool(int(request.args.get('simulate')))
        CORDER = {'Flux-Bias':fluxbias, 'S-Parameter':sparam, 'IF-Bandwidth':ifb, 'Power':powa, 'Frequency':freq}
        TOKEN = 'TOKEN%s' %random()
        Run_fresp[TOKEN] = F_Response(session['people'], corder=CORDER, comment=comment, tag='', dayindex=wday)
        return jsonify(testeach=simulate, status=Run_fresp[TOKEN].status)
    else: return show()


@bp.route('/char/' + frespcryption + '/search', methods=['GET'])
def char_fresp_search():
    keyword = request.args.get('keyword')
    print("Searching for %s" %keyword)
    return jsonify()
# export to mat
@bp.route('/char/' + frespcryption + '/export/2dmat', methods=['GET'])
def char_fresp_export_2dmat():
    ifreq = request.args.get('ifreq') # merely for security reason to block out unsolicited visits by return None from this request
    print("ifreq: %s" %ifreq)
    status = None
    if ifreq is not None:
        set_mat(fresp_2Ddata[session['user_name']], '2Dfresp[%s].mat'%session['user_name'])
        status = "mat written"
        print(Fore.GREEN + "User %s has setup MAT-FILE" %session['user_name'])
    return jsonify(status=status, user_name=session['user_name'], qumport=int(get_status("WEB")['port']))
# export to csv
@bp.route('/char/' + frespcryption + '/export/1dcsv', methods=['GET'])
def char_fresp_export_1dcsv():
    ifreq = request.args.get('ifreq') # merely for security reason to block out unsolicited visits by return None from this request
    print("ifreq: %s" %ifreq)
    status = None
    if ifreq is not None:
        set_csv(fresp_1Ddata[session['user_name']], '1Dfresp[%s].csv'%session['user_name'])
        status = "csv written"
        print(Fore.GREEN + "User %s has setup CSV-FILE" %session['user_name'])
    return jsonify(status=status, user_name=session['user_name'], qumport=int(get_status("WEB")['port']))
# list set-parameters based on selected task-entry
@bp.route('/char/' + frespcryption + '/access', methods=['GET'])
def char_fresp_access():
    wmoment = int(request.args.get('wmoment'))
    try: JOBID = jobsearch(dict(samplename=get_status("MSSN")[session['user_name']]['sample'], task="F_Response", dateday=M_fresp[session['user_name']].day, wmoment=wmoment))
    except: JOBID = 0 # Old version of data before job-queue implementation
    M_fresp[session['user_name']].selectmoment(wmoment)
    M_fresp[session['user_name']].accesstructure()
    data_progress = M_fresp[session['user_name']].data_progress

    # Measurement time:
    filetime = getmtime(M_fresp[session['user_name']].pqfile) # in seconds
    startmeasure = mktime(strptime(M_fresp[session['user_name']].day + " " + M_fresp[session['user_name']].startime(), "%Y-%m-%d(%a) %H:%M")) # made into seconds
    
    if data_progress==0: measureacheta=0
    else: measureacheta = str(timedelta(seconds=(filetime-startmeasure)/data_progress*(trunc(data_progress/100+1)*100-data_progress))) # flexible eta or completion time

    try: cfluxbias = waveform(M_fresp[session['user_name']].corder['Flux-Bias'])
    except(KeyError): cfluxbias = waveform('opt,')
    csparam = waveform(M_fresp[session['user_name']].corder['S-Parameter'])
    cifb = waveform(M_fresp[session['user_name']].corder['IF-Bandwidth'])
    cpowa = waveform(M_fresp[session['user_name']].corder['Power'])
    cfreq = waveform(M_fresp[session['user_name']].corder['Frequency'])
    session['c_fresp_structure'] = [cfluxbias.count,csparam.count,cifb.count,cpowa.count,cfreq.count*M_fresp[session['user_name']].datadensity]
    session['c_fresp_address'] = cdatasearch(M_fresp[session['user_name']].resumepoint-1, session['c_fresp_structure'])
    
    # list each parameter range based on data-progress:
    cfluxbias_data = cfluxbias.data[0:session['c_fresp_address'][0]+1]
    csparam_data = csparam.data[0:session['c_fresp_address'][1]+1]
    cifb_data = cifb.data[0:session['c_fresp_address'][2]+1]
    cpowa_data = cpowa.data[0:session['c_fresp_address'][3]+1]
    cfreq_data = cfreq.data # within buffer

    return jsonify(JOBID=JOBID,
        data_progress=data_progress, measureacheta=measureacheta, corder=M_fresp[session['user_name']].corder, comment=M_fresp[session['user_name']].comment,
        perimeter=M_fresp[session['user_name']].perimeter, 
        cfluxbias_data=cfluxbias_data,csparam_data=csparam_data, cifb_data=cifb_data, cpowa_data=cpowa_data, cfreq_data=cfreq_data)
# Resume the unfinished measurement
@bp.route('/char/' + frespcryption + '/resume', methods=['GET'])
def char_fresp_resume():
    if session['run_clearance']: 
        # set_status("F_Response", dict(pause=False))
        wday = int(request.args.get('wday'))
        wmoment = int(request.args.get('wmoment'))
        fluxbias = request.args.get('fluxbias')
        sparam = request.args.get('sparam')
        ifb = request.args.get('ifb')
        powa = request.args.get('powa')
        freq = request.args.get('freq')
        CORDER = {'Flux-Bias':fluxbias, 'S-Parameter':sparam, 'IF-Bandwidth':ifb, 'Power':powa, 'Frequency':freq}
        M_fresp[session['user_name']].accesstructure()
        TOKEN = 'TOKEN%s' %random()
        Run_fresp[TOKEN] = F_Response(session['people'], corder=CORDER, dayindex=wday, taskentry=wmoment, resumepoint=M_fresp[session['user_name']].resumepoint)
        return jsonify(resumepoint=str(M_fresp[session['user_name']].resumepoint), datasize=str(M_fresp[session['user_name']].datasize), status=Run_fresp[TOKEN].status)
    else: return show()

@bp.route('/char/' + frespcryption + '/trackdata', methods=['GET'])
def char_fresp_trackdata():
    fixed = request.args.get('fixed')
    fixedvalue = request.args.get('fixedvalue')
    cparam = ['fluxbias','sparam','ifb','powa','freq']
    # list data position in file:
    try:
        try:
            fixed_caddress = array(session['c_fresp_structure'],dtype=int64)-1
            fixed_caddress[cparam.index(fixed)] = int(fixedvalue)
            fixed_caddress[cparam.index(fixed)+1:] = 0
        except(IndexError): raise
        data_location = int(gotocdata(fixed_caddress, session['c_fresp_structure']))
    
    # except: raise
    except(ValueError):
        data_location = None
        print(Back.RED + Fore.WHITE + "All parameters before branch must be FIXED!")
        pass

    # print("Data location: %s" %data_location)
    return jsonify(data_location=data_location)
@bp.route('/char/' + frespcryption + '/resetdata', methods=['GET'])
def char_fresp_resetdata():
    ownerpassword = request.args.get('ownerpassword')
    truncateafter = int(request.args.get('truncateafter'))
    db = get_db()
    people = db.execute( 'SELECT password FROM user WHERE username = ?', (session['people'],) ).fetchone()
    if check_password_hash(people['password'], ownerpassword): message = M_fresp[session['user_name']].resetdata(truncateafter)
    else: message = 'PASSWORD NOT VALID'

    return jsonify(message=message)

# Chart is supposedly shared by all measurements (under construction for nulti-purpose)
@bp.route('/char/' + frespcryption + '/1ddata', methods=['GET'])
def char_fresp_1ddata():
    print(Fore.GREEN + "User %s is plotting 1D-Data" %session['user_name'])
    M_fresp[session['user_name']].loadata()
    selectedata = M_fresp[session['user_name']].selectedata
    ifluxbias = request.args.get('ifluxbias')
    # if ifluxbias == "o": ifluxbias = '0' # for backward compatibility
    isparam = request.args.get('isparam')
    iifb = request.args.get('iifb')
    ipowa = request.args.get('ipowa')
    ifreq = request.args.get('ifreq')

    # selecting data
    if ifluxbias == "x":
        title = "<b>Flux-Bias(V)</b>"
        selected_sweep = M_fresp[session['user_name']].corder['Flux-Bias']
        selected_progress = waveform(selected_sweep).data[0:session['c_fresp_address'][0]+1]
        selected_I = [selectedata[gotocdata([x, int(isparam), int(iifb), int(ipowa), 2*int(ifreq)], session['c_fresp_structure'])] for x in range(session['c_fresp_address'][0]+1)]
        selected_Q = [selectedata[gotocdata([x, int(isparam), int(iifb), int(ipowa), 2*int(ifreq)+1], session['c_fresp_structure'])] for x in range(session['c_fresp_address'][0]+1)]
    elif isparam == "x":
        pass
    elif iifb == "x":
        pass
    elif ipowa == "x":
        title = "<b>Power(dBm)</b>"
        selected_sweep = M_fresp[session['user_name']].corder['Power']
        selected_progress = waveform(selected_sweep).data[0:session['c_fresp_address'][3]+1]
        selected_I = [selectedata[gotocdata([int(ifluxbias), int(isparam), int(iifb), x, 2*int(ifreq)], session['c_fresp_structure'])] for x in range(session['c_fresp_address'][3]+1)]
        selected_Q = [selectedata[gotocdata([int(ifluxbias), int(isparam), int(iifb), x, 2*int(ifreq)+1], session['c_fresp_structure'])] for x in range(session['c_fresp_address'][3]+1)]
    elif ifreq == "x":
        title = "<b>frequency(GHz)</b>"
        selected_sweep = M_fresp[session['user_name']].corder['Frequency']
        selected_progress = waveform(selected_sweep).data # Full sweep
        selected_I = [selectedata[gotocdata([int(ifluxbias), int(isparam), int(iifb), int(ipowa), 2*x], session['c_fresp_structure'])] for x in range(waveform(selected_sweep).count)]
        selected_Q = [selectedata[gotocdata([int(ifluxbias), int(isparam), int(iifb), int(ipowa), 2*x+1], session['c_fresp_structure'])] for x in range(waveform(selected_sweep).count)]
    
    # Preparing data:
    MagPha = [IQAP(x[0],x[1]) for x in zip(selected_I, selected_Q)]
    Amp, Pha = [], []
    for i,j in MagPha:
        Amp.append(i); Pha.append(j)
    x1, y1, y2 = selected_progress, Amp, list(UnwraPhase(selected_progress, Pha)) #list(unwrap(Pha)) 
    fresp_1Ddata[session['user_name']] = {title: x1, 'Amplitude': y1, 'UPhase': y2, 'I': selected_I, 'Q': selected_Q, "exported by": session['user_name']}
    
    return jsonify(x1=x1, y1=y1, y2=y2, title=title)
@nb.jit(nopython=True)
@bp.route('/char/' + frespcryption + '/2ddata', methods=['GET'])
def char_fresp_2ddata():
    print(Fore.GREEN + "User %s is plotting 2D-Data" %session['user_name'])
    M_fresp[session['user_name']].loadata()
    selectedata = M_fresp[session['user_name']].selectedata
    ifluxbias = request.args.get('ifluxbias')
    # if ifluxbias == "o": ifluxbias = '0' # for backward compatibility
    isparam = request.args.get('isparam')
    iifb = request.args.get('iifb')
    ipowa = request.args.get('ipowa')
    ifreq = request.args.get('ifreq')

    if ifluxbias == "x" and ifreq == "y":
        print("X: Flux-Bias, Y: Frequency")
        xtitle, ytitle = "<b>Flux-Bias(V/A)</b>", "<b>Frequency(GHz)</b>"
        x, y = waveform(M_fresp[session['user_name']].corder['Flux-Bias']).data[0:session['c_fresp_address'][0]+1], waveform(M_fresp[session['user_name']].corder['Frequency']).data
        x_count, y_count = session['c_fresp_address'][0]+1, waveform(M_fresp[session['user_name']].corder['Frequency']).count

        stage, prev = clocker(0)
        fresp_addresses_0 = concatenate(((ones([1,1])*arange(x_count)).T, ones([x_count,1])*array([int(isparam),int(iifb),int(ipowa)])), axis=1) # 2D stack of addresses
        IQstack, INPLANE, QUAD, Amp, Pha = zeros([x_count,2]), zeros([y_count,x_count]), zeros([y_count,x_count]), zeros([y_count,x_count]), zeros([y_count,x_count])
        for j in range(y_count):
            IQstack[:,0] = selectedata[gotocdata(concatenate((fresp_addresses_0, 2*j*ones([x_count,1])), axis=1), session['c_fresp_structure'])]
            IQstack[:,1] = selectedata[gotocdata(concatenate((fresp_addresses_0, (2*j+1)*ones([x_count,1])), axis=1), session['c_fresp_structure'])]
            INPLANE[j,:], QUAD[j,:], Amp[j,:], Pha[j,:] = IQAParray(IQstack, interlace=False)
        stage, prev = clocker(stage, prev, agenda="2D-Plot for flux-frequency") # Marking time

    elif ipowa == "x" and ifreq == "y":
        print("X: Power, Y: Frequency")
        xtitle, ytitle = "<b>Power(dBm)</b>", "<b>Frequency(GHz)</b>"
        x, y = waveform(M_fresp[session['user_name']].corder['Power']).data[0:session['c_fresp_address'][3]+1], waveform(M_fresp[session['user_name']].corder['Frequency']).data
        x_count, y_count = session['c_fresp_address'][3]+1, waveform(M_fresp[session['user_name']].corder['Frequency']).count

        stage, prev = clocker(0)
        fresp_addresses_0 = concatenate((ones([x_count,1])*array([int(ifluxbias),int(isparam),int(iifb)]), (ones([1,1])*arange(x_count)).T), axis=1) # 2D stack of addresses
        IQstack, INPLANE, QUAD, Amp, Pha = zeros([x_count,2]), zeros([y_count,x_count]), zeros([y_count,x_count]), zeros([y_count,x_count]), zeros([y_count,x_count])
        for j in range(y_count):
            IQstack[:,0] = selectedata[gotocdata(concatenate((fresp_addresses_0, 2*j*ones([x_count,1])), axis=1), session['c_fresp_structure'])]
            IQstack[:,1] = selectedata[gotocdata(concatenate((fresp_addresses_0, (2*j+1)*ones([x_count,1])), axis=1), session['c_fresp_structure'])]
            INPLANE[j,:], QUAD[j,:], Amp[j,:], Pha[j,:] = IQAParray(IQstack, interlace=False)
        stage, prev = clocker(stage, prev, agenda="2D-Plot for power-frequency") # Marking time

    elif iifb == "x":
        pass

    print("(x,y) is of length (%s,%s) and of type (%s,%s)" %(len(x),len(y),type(x),type(y)))
    print("Amp of shape %s" %str(array(Amp).shape))
    ZZI, ZZQ, ZZA, ZZP = INPLANE.tolist(), QUAD.tolist(), Amp.tolist(), Pha.tolist()
    fresp_2Ddata[session['user_name']] = dict(x=x, y=y, ZZI=ZZI, ZZQ=ZZQ, ZZA=ZZA, ZZP=ZZP, xtitle=xtitle, ytitle=ytitle)

    return jsonify(x=x, y=y, ZZA=ZZA, ZZP=ZZP, xtitle=xtitle, ytitle=ytitle)
# endregion

# region: CHAR -> 2. CW-Sweeping =============================================================================================================================================
@bp.route('/char/cwsweep', methods=['GET'])
def char_cwsweep(): 
    return render_template("blog/msson/char/cwsweep.html")
# Initialize and list days specific to task
@bp.route('/char/cwsweep/init', methods=['GET'])
def char_cwsweep_init():
    global M_cwsweep, cwsweep_1Ddata, cwsweep_2Ddata

    # check currently-connected users:
    try: print(Fore.GREEN + "Connected CW-Sweep M-USER(s): %s" %M_cwsweep.keys())
    except: M_cwsweep = {}
    
    # 'user_name' accessing 'people' data:
    M_cwsweep[session['user_name']] = CW_Sweep(session['people'])
    print(Fore.BLUE + Back.WHITE + "User %s is looking at %s's data" %(session['user_name'],session['people']))

    # Initialize 1D Data-Holder:
    try: print(Fore.CYAN + "Connected M-USER(s) holding CW-Sweep's 1D-DATA: %s" %cwsweep_1Ddata.keys())
    except: cwsweep_1Ddata = {}
    # Initialize 2D Data-Holder:
    try: print(Fore.CYAN + "Connected M-USER(s) holding CW-Sweep's 2D-DATA: %s" %cwsweep_2Ddata.keys())
    except: cwsweep_2Ddata = {}

    return jsonify(daylist=M_cwsweep[session['user_name']].daylist, run_permission=session['run_clearance'])
# list task entries based on day picked
@bp.route('/char/cwsweep/time', methods=['GET'])
def char_cwsweep_time():
    wday = int(request.args.get('wday'))
    M_cwsweep[session['user_name']].selectday(wday)
    return jsonify(taskentries=M_cwsweep[session['user_name']].taskentries)

# run NEW measurement:
@bp.route('/char/cwsweep/new', methods=['GET'])
def char_cwsweep_new():
    # Check user's current queue status:
    if session['run_clearance']:
        # set_status("CW_Sweep", dict(pause=False))
        global Run_cwsweep, TOKEN # for ETA calculation as well
        Run_cwsweep = {}
        wday = int(request.args.get('wday'))
        print("wday: %s" %wday)
        fluxbias = request.args.get('fluxbias')
        xyfreq = request.args.get('xyfreq')
        xypowa = request.args.get('xypowa')
        sparam = request.args.get('sparam')
        ifb = request.args.get('ifb')
        freq = request.args.get('freq')
        powa = request.args.get('powa')
        comment = request.args.get('comment').replace("\"","")
        simulate = bool(int(request.args.get('simulate')))
        CORDER = {'Flux-Bias':fluxbias, 'XY-Frequency':xyfreq, 'XY-Power':xypowa, 'S-Parameter':sparam, 'IF-Bandwidth':ifb, 'Frequency':freq, 'Power':powa}
        
        # Start Running:
        TOKEN = 'TOKEN%s' %random()
        Run_cwsweep[TOKEN] = CW_Sweep(session['people'], corder=CORDER, comment=comment, tag='', dayindex=wday)
        
        return jsonify(testeach=simulate, status=Run_cwsweep[TOKEN].status)
    else: return show()


@bp.route('/char/cwsweep/search', methods=['GET'])
def char_cwsweep_search():
    wday = int(request.args.get('wday'))
    filelist = M_cwsweep[session['user_name']].searchcomment()
    return jsonify(filelist=str(filelist))
# export to mat
@bp.route('/char/cwsweep/export/2dmat', methods=['GET'])
def char_cwsweep_export_2dmat():
    ifreq = request.args.get('ifreq') # merely for security reason to block out unsolicited visits by return None from this request
    print("ifreq: %s" %ifreq)
    status = None
    if ifreq is not None:
        set_mat(cwsweep_2Ddata[session['user_name']], '2Dcwsweep[%s].mat'%session['user_name'])
        status = "mat written"
        print(Fore.GREEN + "User %s has setup MAT-FILE" %session['user_name'])
    return jsonify(status=status, user_name=session['user_name'], qumport=int(get_status("WEB")['port']))
# export to csv
@bp.route('/char/cwsweep/export/1dcsv', methods=['GET'])
def char_cwsweep_export_1dcsv():
    ifreq = request.args.get('ifreq') # merely for security reason to block out unsolicited visits by return None from this request
    print("ifreq: %s" %ifreq)
    status = None
    if ifreq is not None:
        set_csv(cwsweep_1Ddata[session['user_name']], '1Dcwsweep[%s].csv'%session['user_name'])
        status = "csv written"
        print(Fore.GREEN + "User %s has setup CSV-FILE" %session['user_name'])
    return jsonify(status=status, user_name=session['user_name'], qumport=int(get_status("WEB")['port']))
# list set-parameters based on selected task-entry
@bp.route('/char/cwsweep/access', methods=['GET'])
def char_cwsweep_access():
    wmoment = int(request.args.get('wmoment'))
    try: JOBID = jobsearch(dict(samplename=get_status("MSSN")[session['user_name']]['sample'], task="CW_Sweep", dateday=M_cwsweep[session['user_name']].day, wmoment=wmoment))
    except: JOBID = 0 # Old version of data before job-queue implementation
    M_cwsweep[session['user_name']].selectmoment(wmoment)
    M_cwsweep[session['user_name']].accesstructure()
    data_progress = M_cwsweep[session['user_name']].data_progress
    data_repeat = data_progress // 100 + int(bool(data_progress % 100))

    # Measurement time:
    filetime = getmtime(M_cwsweep[session['user_name']].pqfile) # in seconds
    startmeasure = mktime(strptime(M_cwsweep[session['user_name']].day + " " + M_cwsweep[session['user_name']].startime(), "%Y-%m-%d(%a) %H:%M")) # made into seconds

    if data_progress==0: measureacheta=0
    else: measureacheta = str(timedelta(seconds=(filetime-startmeasure)/data_progress*(trunc(data_progress/100+1)*100-data_progress)))

    # Scale-up optional parameters:
    try: cfluxbias = waveform(M_cwsweep[session['user_name']].corder['Flux-Bias'])
    except(KeyError): cfluxbias = waveform('opt,') # create virtual list for the absence of this in older file
    try: cxyfreq = waveform(M_cwsweep[session['user_name']].corder['XY-Frequency'])
    except(KeyError): cxyfreq = waveform('opt,') # create virtual list for the absence of this in older file
    try: cxypowa = waveform(M_cwsweep[session['user_name']].corder['XY-Power'])
    except(KeyError): cxypowa = waveform('opt,') # create virtual list for the absence of this in older file
    csparam = waveform(M_cwsweep[session['user_name']].corder['S-Parameter'])
    cifb = waveform(M_cwsweep[session['user_name']].corder['IF-Bandwidth'])
    cfreq = waveform(M_cwsweep[session['user_name']].corder['Frequency'])
    cpowa = waveform(M_cwsweep[session['user_name']].corder['Power'])
    cpowa_repeat = cpowa.inner_repeat
    session['c_cwsweep_structure'] = [data_repeat, cfluxbias.count,cxyfreq.count,cxypowa.count,csparam.count,cifb.count,cfreq.count,cpowa.count*cpowa_repeat*M_cwsweep[session['user_name']].datadensity]
    session['c_cwsweep_address'] = cdatasearch(M_cwsweep[session['user_name']].resumepoint-1, session['c_cwsweep_structure'])
    
    # list each parameter range based on data-progress:
    cfluxbias_data = cfluxbias.data[0:session['c_cwsweep_address'][1]+1]
    cxyfreq_data = cxyfreq.data[0:session['c_cwsweep_address'][2]+1]
    cxypowa_data = cxypowa.data[0:session['c_cwsweep_address'][3]+1]
    csparam_data = csparam.data[0:session['c_cwsweep_address'][4]+1]
    cifb_data = cifb.data[0:session['c_cwsweep_address'][5]+1]
    cfreq_data = cfreq.data[0:session['c_cwsweep_address'][6]+1]
    cpowa_data = cpowa.data[0:(session['c_cwsweep_address'][7]+1)//cpowa_repeat//2]  # (to be adjusted ***)
    # print("cpowa_data: %s" %cpowa_data)
    
    return jsonify(JOBID=JOBID,
        data_progress=data_progress, measureacheta=measureacheta, corder=M_cwsweep[session['user_name']].corder, comment=M_cwsweep[session['user_name']].comment, 
        data_repeat=data_repeat, cfluxbias_data=cfluxbias_data, cxyfreq_data=cxyfreq_data, cxypowa_data=cxypowa_data,
        csparam_data=csparam_data, cifb_data=cifb_data, cfreq_data=cfreq_data, cpowa_data=cpowa_data)
# Resume the unfinished measurement
@bp.route('/char/cwsweep/resume', methods=['GET'])
def char_cwsweep_resume():
    if session['run_clearance']:
        # set_status("CW_Sweep", dict(pause=False))
        wday = int(request.args.get('wday'))
        wmoment = int(request.args.get('wmoment'))
        fluxbias = request.args.get('fluxbias')
        xyfreq = request.args.get('xyfreq')
        xypowa = request.args.get('xypowa')
        sparam = request.args.get('sparam')
        ifb = request.args.get('ifb')
        freq = request.args.get('freq')
        powa = request.args.get('powa')
        CORDER = {'Flux-Bias':fluxbias, 'XY-Frequency':xyfreq, 'XY-Power':xypowa, 'S-Parameter':sparam, 'IF-Bandwidth':ifb, 'Frequency':freq, 'Power':powa}
        M_cwsweep[session['user_name']].accesstructure()
        
        TOKEN = 'TOKEN%s' %random()
        Run_cwsweep[TOKEN] = CW_Sweep(session['people'], corder=CORDER, dayindex=wday, taskentry=wmoment, resumepoint=M_cwsweep[session['user_name']].resumepoint)
        return jsonify(resumepoint=str(M_cwsweep[session['user_name']].resumepoint), datasize=str(M_cwsweep[session['user_name']].datasize), status=Run_cwsweep[TOKEN].status)
    else: return show()

@bp.route('/char/cwsweep/trackdata', methods=['GET'])
def char_cwsweep_trackdata():
    fixed = request.args.get('fixed')
    fixedvalue = request.args.get('fixedvalue')
    cparam = ['repeat','fluxbias','xyfreq','xypowa','sparam','ifb','freq','powa']
    # list data position in file:
    try:
        try:
            fixed_caddress = array(session['c_cwsweep_structure'],dtype=int64)-1
            fixed_caddress[cparam.index(fixed)] = int(fixedvalue)
            fixed_caddress[cparam.index(fixed)+1:] = 0
        except(IndexError): raise
        data_location = int(gotocdata(fixed_caddress, session['c_cwsweep_structure']))
    
    # except: raise
    except(ValueError):
        data_location = None
        print(Back.RED + Fore.WHITE + "All parameters before branch must be FIXED!")
        pass

    # print("Data location: %s" %data_location)
    return jsonify(data_location=data_location)
@bp.route('/char/cwsweep/resetdata', methods=['GET'])
def char_cwsweep_resetdata():
    ownerpassword = request.args.get('ownerpassword')
    truncateafter = int(request.args.get('truncateafter'))

    db = get_db()
    people = db.execute(
        'SELECT password FROM user WHERE username = ?', (session['people'],)
    ).fetchone()

    if check_password_hash(people['password'], ownerpassword):
        message = M_cwsweep[session['user_name']].resetdata(truncateafter)
    else:
        message = 'PASSWORD NOT VALID'

    return jsonify(message=message)

# Chart is supposedly shared by all measurements (under construction for multi-purpose)
@bp.route('/char/cwsweep/1ddata', methods=['GET'])
def char_cwsweep_1ddata():
    print(Fore.GREEN + "User %s is plotting 1D-Data" %session['user_name'])
    M_cwsweep[session['user_name']].loadata()
    selectedata = M_cwsweep[session['user_name']].selectedata
    
    # load parameter indexes from json call:
    irepeat = request.args.get('irepeat')
    ifluxbias = request.args.get('ifluxbias')
    ixyfreq = request.args.get('ixyfreq')
    ixypowa = request.args.get('ixypowa')
    isparam = request.args.get('isparam')
    iifb = request.args.get('iifb')
    ifreq = request.args.get('ifreq')
    ipowa = request.args.get('ipowa')

    # pre-transform ipowa:
    xpowa = waveform(M_cwsweep[session['user_name']].corder['Power'])
    ipowa_repeat = xpowa.inner_repeat

    # selecting data:
    if "x" in ifluxbias:
        xtitle = "<b>Flux-Bias(V/A)</b>"
        selected_sweep = M_cwsweep[session['user_name']].corder['Flux-Bias']
        
        if int(irepeat) < session['c_cwsweep_address'][0]: # address's part before x
            # print("Well within Progress!")
            xsweep = range(session['c_cwsweep_structure'][1]) # can access full-range if selection is well within progress resume-point
        else: xsweep = range(session['c_cwsweep_address'][1]+1) # can only access until progress resume-point

        selected_Ir, selected_Qr = [], []
        for i_prepeat in range(ipowa_repeat): # PENDING: VECTORIZE the for-loop!
            r_powa = int(ipowa) * ipowa_repeat + i_prepeat # from the beginning position of repeating power
            selected_Ir += [selectedata[gotocdata([int(irepeat), x, int(ixyfreq), int(ixypowa), int(isparam), int(iifb), int(ifreq), 2*r_powa], session['c_cwsweep_structure'])] for x in xsweep]
            selected_Qr += [selectedata[gotocdata([int(irepeat), x, int(ixyfreq), int(ixypowa), int(isparam), int(iifb), int(ifreq), 2*r_powa+1], session['c_cwsweep_structure'])] for x in xsweep]
        # AVERAGE up those power repeats:
        selected_I = list(mean(array(selected_Ir).reshape(ipowa_repeat, len(xsweep)), axis=0))
        selected_Q = list(mean(array(selected_Qr).reshape(ipowa_repeat, len(xsweep)), axis=0))
    elif "x" in ixyfreq:
        xtitle = "<b>XY-Frequency(GHz)</b>"
        selected_sweep = M_cwsweep[session['user_name']].corder['XY-Frequency']
        
        if [int(irepeat), int(ifluxbias)] < session['c_cwsweep_address'][0:2]: # address's part before x
            xsweep = range(session['c_cwsweep_structure'][2]) # can access full-range if selection is well within progress resume-point
        else: xsweep = range(session['c_cwsweep_address'][2]+1) # can only access until progress resume-point
        
        selected_Ir, selected_Qr = [], []
        for i_prepeat in range(ipowa_repeat):
            r_powa = int(ipowa) * ipowa_repeat + i_prepeat # from the beginning position of repeating power
            selected_Ir += [selectedata[gotocdata([int(irepeat), int(ifluxbias), x, int(ixypowa), int(isparam), int(iifb), int(ifreq), 2*r_powa], session['c_cwsweep_structure'])] for x in xsweep]
            selected_Qr += [selectedata[gotocdata([int(irepeat), int(ifluxbias), x, int(ixypowa), int(isparam), int(iifb), int(ifreq), 2*r_powa+1], session['c_cwsweep_structure'])] for x in xsweep]
        # AVERAGE up those power repeats:
        selected_I = list(mean(array(selected_Ir).reshape(ipowa_repeat, len(xsweep)), axis=0))
        selected_Q = list(mean(array(selected_Qr).reshape(ipowa_repeat, len(xsweep)), axis=0))
    elif "x" in ixypowa:
        xtitle = "<b>XY-Power(dBm)</b>"
        selected_sweep = M_cwsweep[session['user_name']].corder['XY-Power']
        
        if [int(irepeat), int(ifluxbias), int(ixyfreq)] < session['c_cwsweep_address'][0:3]: # address's part before x
            xsweep = range(session['c_cwsweep_structure'][3]) # can access full-range if selection is well within progress resume-point
        else: xsweep = range(session['c_cwsweep_address'][3]+1) # can only access until progress resume-point
        
        selected_Ir, selected_Qr = [], []
        for i_prepeat in range(ipowa_repeat):
            r_powa = int(ipowa) * ipowa_repeat + i_prepeat # from the beginning position of repeating power
            selected_Ir += [selectedata[gotocdata([int(irepeat), int(ifluxbias), int(ixyfreq), x, int(isparam), int(iifb), int(ifreq), 2*r_powa], session['c_cwsweep_structure'])] for x in xsweep]
            selected_Qr += [selectedata[gotocdata([int(irepeat), int(ifluxbias), int(ixyfreq), x, int(isparam), int(iifb), int(ifreq), 2*r_powa+1], session['c_cwsweep_structure'])] for x in xsweep]
        # AVERAGE up those power repeats:
        selected_I = list(mean(array(selected_Ir).reshape(ipowa_repeat, len(xsweep)), axis=0))
        selected_Q = list(mean(array(selected_Qr).reshape(ipowa_repeat, len(xsweep)), axis=0))
    
    elif "x" in isparam:
        pass
    elif "x" in iifb:
        pass

    elif "x" in ifreq:
        xtitle = "<b>frequency(GHz)</b>"
        selected_sweep = M_cwsweep[session['user_name']].corder['Frequency']
        
        if [int(irepeat), int(ifluxbias), int(ixyfreq), int(ixypowa), int(isparam), int(iifb)] < session['c_cwsweep_address'][0:6]: # address's part before x
            xsweep = range(session['c_cwsweep_structure'][6]) # can access full-range if selection is well within progress resume-point
        else: xsweep = range(session['c_cwsweep_address'][6]+1) # can only access until progress resume-point
        
        selected_Ir, selected_Qr = [], []
        for i_prepeat in range(ipowa_repeat):
            r_powa = int(ipowa) * ipowa_repeat + i_prepeat # from the beginning position of repeating power
            selected_Ir += [selectedata[gotocdata([int(irepeat), int(ifluxbias), int(ixyfreq), int(ixypowa), int(isparam), int(iifb), x, 2*r_powa], session['c_cwsweep_structure'])] for x in xsweep]
            selected_Qr += [selectedata[gotocdata([int(irepeat), int(ifluxbias), int(ixyfreq), int(ixypowa), int(isparam), int(iifb), x, 2*r_powa+1], session['c_cwsweep_structure'])] for x in xsweep]
        # AVERAGE up those power repeats:
        selected_I = list(mean(array(selected_Ir).reshape(ipowa_repeat, len(xsweep)), axis=0))
        selected_Q = list(mean(array(selected_Qr).reshape(ipowa_repeat, len(xsweep)), axis=0))
    elif "x" in ipowa:
        xtitle = "<b>Power(dBm)</b>"
        xpowa_repeat = ipowa_repeat
        
        if [int(irepeat), int(ifluxbias), int(ixyfreq), int(ixypowa), int(isparam), int(iifb), int(ifreq)] < session['c_cwsweep_address'][0:7]: # address's part before x
            xsweep = range(session['c_cwsweep_structure'][7] // 2) # can access full-range if selection is well within progress resume-point
        else: xsweep = range((session['c_cwsweep_address'][7]+1) // 2) # can only access until progress resume-point
        
        selected_Ir = [selectedata[gotocdata([int(irepeat), int(ifluxbias), int(ixyfreq), int(ixypowa), int(isparam), int(iifb), int(ifreq), 2*x], session['c_cwsweep_structure'])] for x in xsweep]
        selected_Qr = [selectedata[gotocdata([int(irepeat), int(ifluxbias), int(ixyfreq), int(ixypowa), int(isparam), int(iifb), int(ifreq), 2*x+1], session['c_cwsweep_structure'])] for x in xsweep]
        # AVERAGE up those repeated IQ-pairs:
        selected_I = list(mean(array(selected_Ir).reshape(len(xsweep)//xpowa_repeat, xpowa_repeat), axis=1)) #-->
        selected_Q = list(mean(array(selected_Qr).reshape(len(xsweep)//xpowa_repeat, xpowa_repeat), axis=1)) #-->

    # preparing data:
    # assembly amplitude & phase:
    MagPha = [IQAP(x[0],x[1]) for x in zip(selected_I, selected_Q)]
    Amp, Pha = [], []
    for i,j in MagPha:
        Amp.append(i); Pha.append(j)

    # x-range:
    if "x" in ipowa: selected_progress = xpowa.data[0:(len(xsweep) // xpowa_repeat)]
    else: selected_progress = waveform(selected_sweep).data[0:len(xsweep)]

    # to avoid exception when encountering recursive parameters:
    if "c" in ixyfreq + ixypowa + ifluxbias + isparam + iifb + ifreq + ipowa:
        selected_progress = list(range(len(selected_progress)))

    x1, y1, yup, yp = selected_progress, Amp, list(UnwraPhase(selected_progress, Pha)), Pha #list(unwrap(Pha)) 
    cwsweep_1Ddata[session['user_name']] = {xtitle: x1, 'Amplitude': y1, 'UPhase': yup, 'I': selected_I, 'Q': selected_Q, "exported by": session['user_name']}
    
    return jsonify(x1=x1, y1=y1, yup=yup, yp=yp, x1title=xtitle)

# Pending renovation below:
@bp.route('/char/cwsweep/2ddata', methods=['GET'])
def char_cwsweep_2ddata():
    irepeat = request.args.get('irepeat')
    ifluxbias = request.args.get('ifluxbias')
    ixyfreq = request.args.get('ixyfreq')
    ixypowa = request.args.get('ixypowa')
    isparam = request.args.get('isparam')
    iifb = request.args.get('iifb')
    ipowa = request.args.get('ipowa')
    ifreq = request.args.get('ifreq')

    # pre-transform ipowa:
    powa_order = M_cwsweep[session['user_name']].corder['Power']

    # preparing MPW dictionary
    dict_for_MPW = {
            "pqfile": str(M_cwsweep[session['user_name']].pqfile), "datalocation": M_cwsweep[session['user_name']].datalocation, "writtensize": M_cwsweep[session['user_name']].writtensize,
            "c_cwsweep_structure": session['c_cwsweep_structure'], "irepeat": irepeat, "ifluxbias": ifluxbias, "ixyfreq": ixyfreq, "ixypowa": ixypowa, 
            "isparam": isparam, "iifb": iifb, "ifreq": ifreq, "ipowa": ipowa, "powa_order": powa_order
        }
    set_status("MPW", dict_for_MPW)

    # Check progress:
    if not M_cwsweep[session['user_name']].data_progress%100:
        offset = 1
        print(Fore.GREEN + "The data is complete: we can see the whole picture now")
    else: 
        offset = 0 # to avoid incomplete array error
        print(Back.RED + "The data is NOT YET complete!")

    # Selecting 2D options:
    # REPEAT:
    if irepeat == "x" and ifluxbias == "y":
        x_name, y_name = "repeat", "fluxbias"
        print("X: REPEAT#, Y: Flux-Bias")
        xtitle, ytitle = "<b>REPEAT#</b>", "<b>Flux-Bias(V/A)</b>"
        x, y = list(range(session['c_cwsweep_address'][0]+offset)), waveform(M_cwsweep[session['user_name']].corder['Flux-Bias']).data
        x_count, y_count = session['c_cwsweep_address'][0]+offset, waveform(M_cwsweep[session['user_name']].corder['Flux-Bias']).count
    if irepeat == "x" and ixyfreq == "y":
        x_name, y_name = "repeat", "xyfreq"
        print("X: REPEAT#, Y: XY-Frequency")
        xtitle, ytitle = "<b>REPEAT#</b>", "<b>XY-Frequency(GHz)</b>"
        x, y = list(range(session['c_cwsweep_address'][0]+offset)), waveform(M_cwsweep[session['user_name']].corder['XY-Frequency']).data
        x_count, y_count = session['c_cwsweep_address'][0]+offset, waveform(M_cwsweep[session['user_name']].corder['XY-Frequency']).count
    # ONCE:
    elif ifluxbias == "x" and ixyfreq == "y":
        x_name, y_name = "fluxbias", "xyfreq"
        print("X: Flux-Bias, Y: XY-Frequency")
        xtitle, ytitle = "<b>Flux-Bias(V/A)</b>", "<b>XY-Frequency(GHz)</b>"
        x, y = waveform(M_cwsweep[session['user_name']].corder['Flux-Bias']).data[0:session['c_cwsweep_address'][1]+offset], waveform(M_cwsweep[session['user_name']].corder['XY-Frequency']).data
        x_count, y_count = session['c_cwsweep_address'][1]+offset, waveform(M_cwsweep[session['user_name']].corder['XY-Frequency']).count
    elif ixyfreq == "x" and ixypowa == "y":
        x_name, y_name = "xyfreq", "xypowa"
        print("X: XY-Frequency, Y: XY-Power")
        xtitle, ytitle = "<b>XY-Frequency(GHz)</b>", "<b>XY-Power(dBm)</b>"
        x, y = waveform(M_cwsweep[session['user_name']].corder['XY-Frequency']).data[0:session['c_cwsweep_address'][2]+offset], waveform(M_cwsweep[session['user_name']].corder['XY-Power']).data
        x_count, y_count = session['c_cwsweep_address'][2]+offset, waveform(M_cwsweep[session['user_name']].corder['XY-Power']).count
    elif ixyfreq == "x" and ifreq == "y":
        x_name, y_name = "xyfreq", "freq"
        print("X: XY-Frequency, Y: Frequency")
        xtitle, ytitle = "<b>XY-Frequency(GHz)</b>", "<b>Probe-Frequency(GHz)</b>"
        x, y = waveform(M_cwsweep[session['user_name']].corder['XY-Frequency']).data[0:session['c_cwsweep_address'][2]+offset], waveform(M_cwsweep[session['user_name']].corder['Frequency']).data
        x_count, y_count = session['c_cwsweep_address'][2]+offset, waveform(M_cwsweep[session['user_name']].corder['Frequency']).count
    elif ixyfreq == "x" and ipowa == "y":
        x_name, y_name = "xyfreq", "powa"
        print("X: XY-Frequency, Y: Power")
        xtitle, ytitle = "<b>XY-Frequency(GHz)</b>", "<b>Probing-Power(dBm)</b>"
        x, y = waveform(M_cwsweep[session['user_name']].corder['XY-Frequency']).data[0:session['c_cwsweep_address'][2]+offset], waveform(M_cwsweep[session['user_name']].corder['Power']).data
        x_count, y_count = session['c_cwsweep_address'][2]+offset, waveform(M_cwsweep[session['user_name']].corder['Power']).count

    # fast iteration method (parallel computing):
    stage, prev = clocker(0)
    CMD = ["python", "-c", "from pyqum.directive import MP_cwsweep as mp; print(mp.worker(%s,%s,'%s','%s'))"%(y_count,x_count,y_name,x_name)]
    with Popen(CMD, stdout=PIPE, shell=True) as proc:
        doutput = proc.stdout.read().decode("utf-8")
        output = json.loads(doutput.replace("\'", "\""))
        # try: os.kill(os.getppid(), signal.SIGTERM) # terminate parent process
        # except: pass
    Amp = output['rA']
    Pha = output['rP'] # Raw Phase that is wrapped around -pi and pi
    stage, prev = clocker(stage, prev) # Marking time

    print("x is of length %s and of type %s" %(len(x),type(x)))
    print("y is of length %s and of type %s" %(len(y),type(y)))
    print("Amp of shape %s" %str(array(Amp).shape))
    ZZA, ZZP = Amp, Pha
    
    cwsweep_2Ddata[session['user_name']] = dict(x=x, y=y, ZZA=ZZA, ZZP=ZZP, xtitle=xtitle, ytitle=ytitle)

    # x = list(range(len(x))) # for repetitive data
    return jsonify(x=x, y=y, ZZA=ZZA, ZZP=ZZP, xtitle=xtitle, ytitle=ytitle)
# endregion

# region: CHAR -> 3. SQE-Pulsing =============================================================================================================================================
'''ACCESS ONLY'''
@bp.route('/char/sqepulse', methods=['GET'])
def char_sqepulse(): 
    return render_template("blog/msson/char/sqepulse.html")
# Initialize and list days specific to task
@bp.route('/char/sqepulse/init', methods=['GET'])
def char_sqepulse_init():
    global M_sqepulse, CParameters, sqepulse_1Ddata, sqepulse_2Ddata

    # check currently-connected users:
    try: print(Fore.GREEN + "Connected M-USER(s) for SQE-Pulse: %s" %M_sqepulse.keys())
    except: M_sqepulse = {}
    
    # 'user_name' accessing 'people' data:
    M_sqepulse[session['user_name']] = SQE_Pulse(session['people'])
    print(Fore.BLUE + Back.WHITE + "User %s is looking at %s's data" %(session['user_name'],session['people']))

    # PENDING: Flexible C-Structure:
    CParameters = {}
    CParameters['SQE_Pulse'] = ['repeat', 'Flux-Bias', 'XY-Frequency', 'XY-Power', 'RO-Frequency', 'RO-Power',
                'Pulse-Period', 'RO-ifLevel', 'RO-Pulse-Delay', 'RO-Pulse-Width', 'XY-ifLevel', 'XY-Pulse-Delay', 'XY-Pulse-Width', 
                'LO-Frequency', 'LO-Power', 'ADC-delay', 'Average', 'Sampling-Time']

    # Initialize 1D Data-Holder:
    try: print(Fore.CYAN + "Connected M-USER(s) holding SQE-Pulse's 1D-DATA: %s" %sqepulse_1Ddata.keys())
    except: sqepulse_1Ddata = {}
    # Initialize 2D Data-Holder:
    try: print(Fore.CYAN + "Connected M-USER(s) holding SQE-Pulse's 2D-DATA: %s" %sqepulse_2Ddata.keys())
    except: sqepulse_2Ddata = {}

    return jsonify(daylist=M_sqepulse[session['user_name']].daylist, run_permission=session['run_clearance'])
# list task entries based on day picked
@bp.route('/char/sqepulse/time', methods=['GET'])
def char_sqepulse_time():
    wday = int(request.args.get('wday'))
    M_sqepulse[session['user_name']].selectday(wday)
    return jsonify(taskentries=M_sqepulse[session['user_name']].taskentries)

# adjust settings input for certain instruments' set
@bp.route('/char/sqepulse/settings', methods=['GET'])
def char_sqepulse_settings():
    # under construction ***
    # pending: YOKO switching between V and I source
    # PSG type selection
    return jsonify()

# run NEW measurement:
@bp.route('/char/sqepulse/new', methods=['GET'])
def char_sqepulse_new():
    # Check user's current queue status:
    if session['run_clearance']:
        set_status("SQE_Pulse", dict(pause=False))
        global Run_sqepulse # for ETA calculation as well
        Run_sqepulse = {}
        wday = int(request.args.get('wday'))
        if wday < 0: print("Running New SQE-Pulse...")

        CORDER = json.loads(request.args.get('CORDER'))
        comment = request.args.get('comment').replace("\"","")
        simulate = bool(int(request.args.get('simulate')))
        
        Run_sqepulse['TOKEN'] = SQE_Pulse(session['people'], corder=CORDER, comment=comment, tag='', dayindex=wday)
        return jsonify(testeach=simulate)
    else: return show()
# search through logs of data specific to task (pending)
@bp.route('/char/sqepulse/search', methods=['GET'])
def char_sqepulse_search():
    wday = int(request.args.get('wday'))
    filelist = M_sqepulse[session['user_name']].searchcomment()
    return jsonify(filelist=str(filelist))
# export to mat
@bp.route('/char/sqepulse/export/2dmat', methods=['GET'])
def char_sqepulse_export_2dmat():
    ifreq = request.args.get('ifreq') # merely for security reason to block out unsolicited visits by return None from this request
    print("ifreq: %s" %ifreq)
    status = None
    if ifreq is not None:
        set_mat(sqepulse_2Ddata[session['user_name']], '2Dsqepulse[%s].mat'%session['user_name'])
        status = "mat written"
        print(Fore.GREEN + "User %s has setup MAT-FILE" %session['user_name'])
    return jsonify(status=status, user_name=session['user_name'], qumport=int(get_status("WEB")['port']))
# export to csv
@bp.route('/char/sqepulse/export/1dcsv', methods=['GET'])
def char_sqepulse_export_1dcsv():
    ifreq = request.args.get('ifreq') # merely for security reason to block out unsolicited visits by return None from this request
    print("ifreq: %s" %ifreq)
    status = None
    if ifreq is not None:
        set_csv(sqepulse_1Ddata[session['user_name']], '1Dsqepulse[%s].csv'%session['user_name'])
        status = "csv written"
        print(Fore.GREEN + "User %s has setup CSV-FILE" %session['user_name'])
    return jsonify(status=status, user_name=session['user_name'], qumport=int(get_status("WEB")['port']))
# list set-parameters based on selected task-entry
@bp.route('/char/sqepulse/access', methods=['GET'])
def char_sqepulse_access():
    wmoment = int(request.args.get('wmoment'))
    M_sqepulse[session['user_name']].selectmoment(wmoment)
    M_sqepulse[session['user_name']].accesstructure()
    corder = M_sqepulse[session['user_name']].corder
    data_progress = M_sqepulse[session['user_name']].data_progress
    data_repeat = data_progress // 100 + int(bool(data_progress % 100))

    global cmd_repeat
    cmd_repeat = {}
    cmd_repeat[session['user_name']] = '0 to %s * %s' %(int(data_repeat-1), int(data_repeat-1))
    corder['repeat'] = cmd_repeat[session['user_name']]

    # Measurement time:
    filetime = getmtime(M_sqepulse[session['user_name']].pqfile) # in seconds
    startmeasure = mktime(strptime(M_sqepulse[session['user_name']].day + " " + M_sqepulse[session['user_name']].startime(), "%Y-%m-%d(%a) %H:%M")) # made into seconds

    if data_progress==0: measureacheta=0
    else: measureacheta = str(timedelta(seconds=(filetime-startmeasure)/data_progress*(trunc(data_progress/100+1)*100-data_progress)))

    # Structure & Addresses:
    session['c_sqepulse_structure'] = [waveform(corder[param]).count for param in CParameters['SQE_Pulse']][:-1] \
                                        + [waveform(corder[CParameters['SQE_Pulse'][-1]]).count*M_sqepulse[session['user_name']].datadensity]
    session['c_sqepulse_progress'] = cdatasearch(M_sqepulse[session['user_name']].resumepoint-1, session['c_sqepulse_structure'])
    
    pdata = dict()
    for params in CParameters['SQE_Pulse']:
        pdata[params] = waveform(corder[params]).data[0:session['c_sqepulse_progress'][CParameters['SQE_Pulse'].index(params)]+1]
    print("repeat's parameter-data: %s" %pdata['repeat'])

    return jsonify(data_progress=data_progress, measureacheta=measureacheta, corder=corder, comment=M_sqepulse[session['user_name']].comment, pdata=pdata)
# Resume the unfinished measurement
@bp.route('/char/sqepulse/resume', methods=['GET'])
def char_sqepulse_resume():
    if session['run_clearance']:
        set_status("SQE_Pulse", dict(pause=False))
        wday = int(request.args.get('wday'))
        wmoment = int(request.args.get('wmoment'))
        CORDER = json.loads(request.args.get('CORDER'))
        M_sqepulse[session['user_name']].accesstructure()
        SQE_Pulse(session['people'], corder=CORDER, dayindex=wday, taskentry=wmoment, resumepoint=M_sqepulse[session['user_name']].resumepoint)
        return jsonify(resumepoint=str(M_sqepulse[session['user_name']].resumepoint), datasize=str(M_sqepulse[session['user_name']].datasize))
    else: return show()

@bp.route('/char/sqepulse/trackdata', methods=['GET'])
def char_sqepulse_trackdata():
    fixed = request.args.get('fixed')
    fixedvalue = request.args.get('fixedvalue')
    # list data position in file:
    try:
        data_location = None
        try:
            fixed_caddress = array(session['c_sqepulse_structure'],dtype=int64)-1
            fixed_caddress[CParameters['SQE_Pulse'].index(fixed)] = int(fixedvalue)
            fixed_caddress[CParameters['SQE_Pulse'].index(fixed)+1:] = 0
        except(IndexError): raise
        data_location = int(gotocdata(fixed_caddress, session['c_sqepulse_structure']))
    
    # except: raise
    except(ValueError):
        print(Back.RED + Fore.WHITE + "All parameters before branch must be FIXED!")
        pass

    # print("Data location: %s" %data_location)
    return jsonify(data_location=data_location)
@bp.route('/char/sqepulse/resetdata', methods=['GET'])
def char_sqepulse_resetdata():
    ownerpassword = request.args.get('ownerpassword')
    truncateafter = int(request.args.get('truncateafter'))

    db = get_db()
    people = db.execute(
        'SELECT password FROM user WHERE username = ?', (session['people'],)
    ).fetchone()

    if check_password_hash(people['password'], ownerpassword):
        message = M_sqepulse[session['user_name']].resetdata(truncateafter)
    else:
        message = 'PASSWORD NOT VALID'

    return jsonify(message=message)

# Chart is supposedly shared by all measurements (under construction for multi-purpose)
@bp.route('/char/sqepulse/1ddata', methods=['GET'])
def char_sqepulse_1ddata():
    print(Fore.GREEN + "User %s is plotting SQEPULSE 1D-Data" %session['user_name'])
    M_sqepulse[session['user_name']].loadata()
    selectedata = M_sqepulse[session['user_name']].selectedata
    print("Data length: %s" %len(selectedata))
    
    # load parameter indexes from json call:
    cselect = json.loads(request.args.get('cselect'))

    for k in cselect.keys():
        if "x" in cselect[k]:
            xtitle = "<b>" + k + "</b>"
            selected_caddress = [s for s in cselect.values()]
        
            # Sweep-command:
            if k == 'repeat':
                selected_sweep = cmd_repeat[session['user_name']]
            else:
                selected_sweep = M_sqepulse[session['user_name']].corder[k]

            # Adjusting c-parameters range for data analysis based on progress:
            parent_address = selected_caddress[:CParameters['SQE_Pulse'].index(k)] # address's part before x
            if [int(s) for s in parent_address] < session['c_sqepulse_progress'][0:len(parent_address)]:
                print(Fore.YELLOW + "selection is well within progress")
                sweepables = session['c_sqepulse_structure'][CParameters['SQE_Pulse'].index(k)]
            else: sweepables = session['c_sqepulse_progress'][CParameters['SQE_Pulse'].index(k)]+1

            # Special treatment on the last 'buffer' parameter to factor out the data-density first: 
            if CParameters['SQE_Pulse'].index(k) == len(CParameters['SQE_Pulse'])-1 :
                isweep = range(sweepables//M_sqepulse[session['user_name']].datadensity)
            else:
                isweep = range(sweepables) # flexible access until progress resume-point
            print(Back.WHITE + Fore.BLACK + "Sweeping %s points" %len(isweep))

            Idata = zeros(len(isweep))
            Qdata = zeros(len(isweep))
            Adata = zeros(len(isweep))
            Pdata = zeros(len(isweep))
            for i in isweep:
                # PENDING: VECTORIZATION OR MULTI-PROCESS
                selected_caddress[CParameters['SQE_Pulse'].index(k)] = i # register x-th position
                if [c for c in cselect.values()][-1] == "s": # sampling mode currently limited to time-range (last 'basic' parameter) only
                    srange = request.args.get('srange').split(",") # sample range
                    smode = request.args.get('smode') # sampling mode
                    Idata[i], Qdata[i], Adata[i], Pdata[i] = \
                        pulseresp_sampler(srange, selected_caddress, selectedata, session['c_sqepulse_structure'], M_sqepulse[session['user_name']].datadensity, mode=smode)
                else:
                    # Ground level Pulse shape response:
                    selected_caddress = [int(s) for s in selected_caddress]
                    Basic = selected_caddress[-1]
                    # Extracting I & Q:
                    Idata[i] = selectedata[gotocdata(selected_caddress[:-1]+[2*Basic], session['c_sqepulse_structure'])]
                    Qdata[i] = selectedata[gotocdata(selected_caddress[:-1]+[2*Basic+1], session['c_sqepulse_structure'])]
                    Adata[i] = sqrt(Idata[i]**2 + Qdata[i]**2)
                    Pdata[i] = arctan2(Qdata[i], Idata[i]) # -pi < phase < pi    
    
    # Improvisation before pending vectorization on the sampler:


    print("Structure: %s" %session['c_sqepulse_structure'])
    # x-data:
    selected_progress = waveform(selected_sweep).data[0:len(isweep)]
    # facilitate index location (or count) for range clipping:
    cselection = (",").join([s for s in cselect.values()])
    if "c" in cselection:
        selected_progress = list(range(len(selected_progress)))

    x, yI, yQ, yA, yUFNP = selected_progress, list(Idata), list(Qdata), list(Adata), list(Pdata)
    sqepulse_1Ddata[session['user_name']] = {xtitle: x, 'I': yI, 'Q': yQ, 'A(V)': yA, 'UFNP(rad/x)': yUFNP, "exported by": session['user_name']}
    
    return jsonify(x=x, yI=yI, yQ=yQ, yA=yA, yUFNP=yUFNP, xtitle=xtitle)

@bp.route('/char/sqepulse/2ddata', methods=['GET'])
def char_sqepulse_2ddata():
    print(Fore.GREEN + "User %s is plotting SQEPULSE 2D-Data using vectorization" %session['user_name'])
    M_sqepulse[session['user_name']].loadata()
    selectedata = M_sqepulse[session['user_name']].selectedata
    print("Data length: %s" %len(selectedata))
    
    # load parameter indexes from json call:
    cselect = json.loads(request.args.get('cselect'))

    try:
        x_loc = [k for k in cselect.values()].index('x')
        selected_x = [c for c in cselect.keys()][x_loc]
        y_loc = [k for k in cselect.values()].index('y')
        selected_y = [c for c in cselect.keys()][y_loc]
        xtitle = "<b>" + selected_x + "</b>"
        ytitle = "<b>" + selected_y + "</b>"
        selected_caddress = [s for s in cselect.values()]
    except: 
        print("x and y parameters not selected or not valid")
        
    # Adjusting c-parameters range for data analysis based on progress:
    parent_address = selected_caddress[:CParameters['SQE_Pulse'].index(selected_x)] # address's part before x (higher-level data)
    if [int(s) for s in parent_address] < session['c_sqepulse_progress'][0:len(parent_address)]: # must be matched with the parameter-select-range on the front-page
        print(Fore.YELLOW + "selection is well within progress")
        sweepables = [session['c_sqepulse_structure'][CParameters['SQE_Pulse'].index(selected_x)], session['c_sqepulse_structure'][CParameters['SQE_Pulse'].index(selected_y)]]
    else: 
        sweepables = [session['c_sqepulse_progress'][CParameters['SQE_Pulse'].index(selected_x)]+1, session['c_sqepulse_progress'][CParameters['SQE_Pulse'].index(selected_y)]+1]

            
    # flexible access until progress resume-point
    xsweep = range(sweepables[0])
    if CParameters['SQE_Pulse'].index(selected_y) == len(CParameters['SQE_Pulse'])-1 :
        # Special treatment on the last 'buffer' parameter to factor out the data-density first:
        ysweep = range(sweepables[1]//M_sqepulse[session['user_name']].datadensity)
    else:
        ysweep = range(sweepables[1]) 
    print(Back.WHITE + Fore.BLACK + "Sweeping %s x-points" %len(xsweep))
    print(Back.WHITE + Fore.BLACK + "Sweeping %s y-points" %len(ysweep))

    Idata = zeros([len(ysweep), len(xsweep)])
    Qdata = zeros([len(ysweep), len(xsweep)])
    for j in ysweep:
        selected_caddress[CParameters['SQE_Pulse'].index(selected_y)] = j # register y-th position
        for i in xsweep:
            selected_caddress[CParameters['SQE_Pulse'].index(selected_x)] = i # register x-th position
            if [c for c in cselect.values()][-1] == "s": # sampling mode currently limited to time-range (last 'basic' parameter) only
                srange = request.args.get('srange').split(",") # sample range

                if [int(srange[1]) , int(srange[0])] > [session['c_sqepulse_structure'][-1]//M_sqepulse[session['user_name']].datadensity] * 2:
                    print(Back.WHITE + Fore.RED + "Out of range")
                else:
                    # ACTIVE Region of the Pulse Response:
                    # FASTEST PARALLEL VECTORIZATION OF BIG DATA BY NUMPY:
                    active_len = int(srange[1]) - int(srange[0]) + 1
                    # Assemble stacks of selected c-address for this sample range:
                    selected_caddress_I = array([[int(s) for s in selected_caddress[:-1]] + [0]] * active_len)
                    selected_caddress_Q = array([[int(s) for s in selected_caddress[:-1]] + [0]] * active_len)
                    # sort-out interleaved IQ:
                    selected_caddress_I[:,-1] = 2 * array(range(int(srange[0]),int(srange[1])+1))
                    selected_caddress_Q[:,-1] = 2 * array(range(int(srange[0]),int(srange[1])+1)) + ones(active_len)
                    # Compressing I & Q of this sample range:
                    selectedata = array(selectedata)
                    Idata_active = mean(selectedata[gotocdata(selected_caddress_I, session['c_sqepulse_structure'])])
                    Qdata_active = mean(selectedata[gotocdata(selected_caddress_Q, session['c_sqepulse_structure'])]) 

                    try:
                        # RELAXED Region of the Pulse Response:
                        # FASTEST PARALLEL VECTORIZATION OF BIG DATA BY NUMPY:
                        relax_len = int(srange[3]) - int(srange[2]) + 1
                        # Assemble stacks of selected c-address for this sample range:
                        selected_caddress_I = array([[int(s) for s in selected_caddress[:-1]] + [0]] * relax_len)
                        selected_caddress_Q = array([[int(s) for s in selected_caddress[:-1]] + [0]] * relax_len)
                        # sort-out interleaved IQ:
                        selected_caddress_I[:,-1] = 2 * array(range(int(srange[2]),int(srange[3])+1))
                        selected_caddress_Q[:,-1] = 2 * array(range(int(srange[2]),int(srange[3])+1)) + ones(relax_len)
                        # Compressing I & Q of this sample range:
                        selectedata = array(selectedata)
                        Idata_relax = mean(selectedata[gotocdata(selected_caddress_I, session['c_sqepulse_structure'])])
                        Qdata_relax = mean(selectedata[gotocdata(selected_caddress_Q, session['c_sqepulse_structure'])]) 
                    except(IndexError): Idata_relax, Qdata_relax = 0, 0

                    Idata[j,i] = Idata_active - Idata_relax
                    Qdata[j,i] = Qdata_active - Qdata_relax

            else:
                # Ground level Pulse shape response:
                selected_caddress = [int(s) for s in selected_caddress]
                Basic = selected_caddress[-1]
                # Extracting I & Q:
                Idata[j,i] = selectedata[gotocdata(selected_caddress[:-1]+[2*Basic], session['c_sqepulse_structure'])]
                Qdata[j,i] = selectedata[gotocdata(selected_caddress[:-1]+[2*Basic+1], session['c_sqepulse_structure'])]  

    print("Mapping complete. Structure: %s" %session['c_sqepulse_structure'])
    
    # x-data:
    if 'repeat' in xtitle: selected_xsweep = cmd_repeat[session['user_name']]
    else: selected_xsweep = M_sqepulse[session['user_name']].corder[selected_x]
    x = waveform(selected_xsweep).data[0:len(xsweep)]

    # y-data:
    selected_ysweep = M_sqepulse[session['user_name']].corder[selected_y]
    y = waveform(selected_ysweep).data[0:len(ysweep)]
    
    # IQ-data:
    # print("I: %s" %Idata[0])
    # print("Q: %s" %Qdata[0])
    Adata = sqrt(Idata**2 + Qdata**2)
    UPdata = unwrap(arctan2(Qdata, Idata)) # -pi < phase < pi -> Unwrapped
    
    ZZI, ZZQ, ZZA, ZZUP = Idata.tolist(), Qdata.tolist(), Adata.tolist(), UPdata.tolist()

    sqepulse_2Ddata[session['user_name']] = dict(x=x, y=y, ZZI=ZZI, ZZQ=ZZQ, ZZA=ZZA, ZZUP=ZZUP, xtitle=xtitle, ytitle=ytitle)

    return jsonify(x=x, y=y, ZZI=ZZI, ZZQ=ZZQ, ZZA=ZZA, ZZUP=ZZUP, xtitle=xtitle, ytitle=ytitle)
# endregion

# region: MANI:
@bp.route('/mani', methods=['GET'])
def mani(): 
    print(Fore.BLUE + 'User %s is allowed to run measurement: %s'%(g.user['username'],session['run_clearance']))
    samplename = get_status("MSSN")[session['user_name']]['sample']
    return render_template("blog/msson/mani.html", samplename=samplename, people=session['people'])
# endregion

# region: MANI -> 1. Single-Qubit =============================================================================================================================================
'''Complete 1Q Manipulation'''
@bp.route('/mani/singleqb', methods=['GET'])
def mani_singleqb(): 
    return render_template("blog/msson/mani/singleqb.html")
# Initialize and list days specific to task
@bp.route('/mani/singleqb/init', methods=['GET'])
def mani_singleqb_init():
    global Run_singleqb, M_singleqb, SQ_CParameters, singleqb_1Ddata, singleqb_2Ddata, c_singleqb_structure, c_singleqb_progress

    # Managing / Initialize token-specific Measurement M:
    try: print(Fore.GREEN + "Connected M-TOKEN(s) for Single-Qubit: %s" %Run_singleqb.keys())
    except: Run_singleqb = {}
    
    # Managing / Initialize user-specific Measurement Access MA:
    try: print(Fore.BLUE + "Connected MA-USER(s) for Single-Qubit: %s" %M_singleqb.keys())
    except: M_singleqb = {}
    # 'user_name' accessing 'people' data:
    M_singleqb[session['user_name']] = Single_Qubit(session['people'])
    print(Fore.BLUE + Back.WHITE + "User %s is managing %s's data" %(session['user_name'],session['people']))

    # Managing / Initialize user-specific Control Parameters CP:
    try: print(Fore.CYAN + "Connected CP-USER(s) for Single-Qubit: %s" %SQ_CParameters.keys())
    except: SQ_CParameters = {}

    # Managing / Initialize user-specific 1D Data-Holder 1DH:
    try: print(Fore.CYAN + "Connected 1DH-USER(s) for Single-Qubit: %s" %singleqb_1Ddata.keys())
    except: singleqb_1Ddata = {}
    # Managing / Initialize user-specific 2D Data-Holder 2DH:
    try: print(Fore.CYAN + "Connected 2DH-USER(s) for Single-Qubit: %s" %singleqb_2Ddata.keys())
    except: singleqb_2Ddata = {}

    # Managing / Initialize user-specific SQ Structure SQS:
    try: print(Fore.CYAN + "Connected SQS-USER(s) for Single-Qubit: %s" %c_singleqb_structure.keys())
    except: c_singleqb_structure = {}

    # Managing / Initialize user-specific SQ Progress SQP:
    try: print(Fore.CYAN + "Connected SQP-USER(s) for Single-Qubit: %s" %c_singleqb_progress.keys())
    except: c_singleqb_progress = {}

    return jsonify(daylist=M_singleqb[session['user_name']].daylist, run_permission=session['run_clearance'])
# list task entries based on day picked
@bp.route('/mani/singleqb/time', methods=['GET'])
def mani_singleqb_time():
    wday = int(request.args.get('wday'))
    M_singleqb[session['user_name']].selectday(wday)
    return jsonify(taskentries=M_singleqb[session['user_name']].taskentries)
# Check DIGITIZER TIME & SUM:
@bp.route('/mani/singleqb/check/timsum', methods=['GET'])
def mani_singleqb_check_timsum():
    record_time_ns = int(request.args.get('record_time_ns'))
    record_sum = int(request.args.get('record_sum'))
    from pyqum.instrument.modular import ALZDG
    record_time_ns, record_sum = ALZDG.check_timsum(record_time_ns,record_sum)
    return jsonify(record_time_ns=record_time_ns, record_sum=record_sum)
# run NEW measurement:
@bp.route('/mani/singleqb/new', methods=['GET'])
def mani_singleqb_new():
    # Check user's current queue status:
    if session['run_clearance']:
        wday = int(request.args.get('wday'))
        if wday < 0: print("Running New Single-Qubit...")

        PERIMETER = json.loads(request.args.get('PERIMETER'))
        CORDER = json.loads(request.args.get('CORDER'))
        comment = request.args.get('comment').replace("\"","")
        
        TOKEN = 'TOKEN%s' %random()
        Run_singleqb[TOKEN] = Single_Qubit(session['people'], perimeter=PERIMETER, corder=CORDER, comment=comment, tag='', dayindex=wday)
        return jsonify(status=Run_singleqb[TOKEN].status)
    else: return show("PLEASE CHECK YOUR RUN-CLEARANCE WITH ABC")

# DATA DOWNLOAD
# export to mat
@bp.route('/mani/singleqb/export/2dmat', methods=['GET'])
def char_singleqb_export_2dmat():
    interaction = request.args.get('interaction') # merely for security reason to block out unsolicited visits by return None from this request
    print("interaction: %s" %interaction)
    status = None
    if interaction is not None:
        set_mat(singleqb_2Ddata[session['user_name']], '2Dsingleqb[%s].mat'%session['user_name'])
        status = "mat written"
        print(Fore.GREEN + "User %s has setup MAT-FILE" %session['user_name'])
    return jsonify(status=status, user_name=session['user_name'], qumport=int(get_status("WEB")['port']))
# export to csv
@bp.route('/mani/singleqb/export/1dcsv', methods=['GET'])
def mani_singleqb_export_1dcsv():
    ifreq = request.args.get('ifreq') # merely for security reason to block out unsolicited visits by return None from this request
    print("ifreq: %s" %ifreq)
    status = None
    if ifreq is not None:
        set_csv(singleqb_1Ddata[session['user_name']], '1Dsingleqb[%s].csv'%session['user_name'])
        status = "csv written"
        print(Fore.GREEN + "User %s has setup CSV-FILE" %session['user_name'])
    return jsonify(status=status, user_name=session['user_name'], qumport=int(get_status("WEB")['port']))

# DATA ACCESS
# list set-parameters based on selected task-entry
@bp.route('/mani/singleqb/access', methods=['GET'])
def mani_singleqb_access():
    wmoment = int(request.args.get('wmoment'))
    try: JOBID = jobsearch(dict(samplename=get_status("MSSN")[session['user_name']]['sample'], task="Single_Qubit", dateday=M_singleqb[session['user_name']].day, wmoment=wmoment))
    except: JOBID = 0 # Old version of data before job-queue implementation
    M_singleqb[session['user_name']].selectmoment(wmoment)
    M_singleqb[session['user_name']].accesstructure()
    corder = M_singleqb[session['user_name']].corder
    perimeter = M_singleqb[session['user_name']].perimeter
    comment = M_singleqb[session['user_name']].comment
    data_progress = M_singleqb[session['user_name']].data_progress
    data_repeat = data_progress // 100 + int(bool(data_progress % 100))

    # Measurement time:
    filetime = getmtime(M_singleqb[session['user_name']].pqfile) # in seconds
    startmeasure = mktime(strptime(M_singleqb[session['user_name']].day + " " + M_singleqb[session['user_name']].startime(), "%Y-%m-%d(%a) %H:%M")) # made into seconds

    if data_progress==0: measureacheta=0
    else: measureacheta = str(timedelta(seconds=(filetime-startmeasure)/data_progress*(trunc(data_progress/100+1)*100-data_progress)))
      
    # Integrate R-Parameters back into C-Order:
    RJSON = json.loads(perimeter['R-JSON'].replace("'",'"'))
    for k in RJSON.keys(): corder[k] = RJSON[k]
    # Recombine Buffer back into C-Order:
    if perimeter['READOUTYPE'] == 'one-shot': bufferkey = 'RECORD-SUM'
    else: bufferkey = 'RECORD_TIME_NS'
    corder[bufferkey] = "1 to %s * %s" %(perimeter[bufferkey], int(perimeter[bufferkey])-1)
    # Extend C-Structure with R-Parameters & Buffer keys:
    SQ_CParameters[session['user_name']] = corder['C-Structure'] + [k for k in RJSON.keys()] + [bufferkey] # Fixed-Structure + R-Structure + Buffer

    # Structure & Addresses:
    c_singleqb_structure[session['user_name']] = [waveform(corder[param]).count for param in SQ_CParameters[session['user_name']]][:-1] \
                                        + [waveform(corder[SQ_CParameters[session['user_name']][-1]]).count*M_singleqb[session['user_name']].datadensity]
    c_singleqb_progress[session['user_name']] = cdatasearch(M_singleqb[session['user_name']].resumepoint-1, c_singleqb_structure[session['user_name']])
    
    pdata = dict()
    for params in SQ_CParameters[session['user_name']]:
        pdata[params] = waveform(corder[params]).data[0:c_singleqb_progress[session['user_name']][SQ_CParameters[session['user_name']].index(params)]+1]
    # print("RECORD_TIME_NS's parameter-data: %s" %pdata['RECORD_TIME_NS'])

    return jsonify(JOBID=JOBID,
        data_progress=data_progress, measureacheta=measureacheta, corder=corder, perimeter=perimeter, comment=comment, 
        pdata=pdata, SQ_CParameters=SQ_CParameters[session['user_name']])
# save perimeter settings for different measurements (Fresp, Cwsweep, Rabi, T1, T2, Wigner, Fidelity, QST etc)
@bp.route('/mani/singleqb/perisettings/save', methods=['GET'])
def mani_singleqb_perisettings_save():
    scheme_name = request.args.get('scheme_name')
    presetting = { '%s'%scheme_name : M_singleqb[session['user_name']].perimeter }
    try:
        if scheme_name=="TRANSFER" or int(g.user['measurement'])>2: set_status('SCHEME', presetting)
        else: scheme_name = "Nothing"
    except(ValueError): scheme_name = "NULL" # for Those with No measurement clearance
    return jsonify(scheme_name=scheme_name)
# load perimeter settings for different measurements (Fresp, Cwsweep, Rabi, T1, T2, Wigner, Fidelity, QST etc)
@bp.route('/mani/singleqb/perisettings/load', methods=['GET'])
def mani_singleqb_perisettings_load():
    scheme_name = request.args.get('scheme_name')
    try: perimeter, status = get_status('SCHEME')[scheme_name], 'Loaded from '
    except: perimeter, status = {}, 'Not Found.'
    return jsonify(perimeter=perimeter, status=status)

# DATA MANAGEMENT
# Resume the unfinished measurement
@bp.route('/mani/singleqb/resume', methods=['GET'])
def mani_singleqb_resume():
    if session['run_clearance']:
        # retrieve from ui-selection:
        wday = int(request.args.get('wday'))
        wmoment = int(request.args.get('wmoment'))
        # retrieve from file:
        M_singleqb[session['user_name']].accesstructure()
        perimeter = M_singleqb[session['user_name']].perimeter
        corder = M_singleqb[session['user_name']].corder
        resumepoint = M_singleqb[session['user_name']].resumepoint

        TOKEN = 'TOKEN%s' %random()
        Run_singleqb[TOKEN] = Single_Qubit(session['people'], perimeter=perimeter, corder=corder, dayindex=wday, taskentry=wmoment, resumepoint=resumepoint)
        return jsonify(resumepoint=str(resumepoint), datasize=str(M_singleqb[session['user_name']].datasize), status=Run_singleqb[TOKEN].status)
    else: return show()
@bp.route('/mani/singleqb/trackdata', methods=['GET'])
def mani_singleqb_trackdata():
    fixed = request.args.get('fixed')
    fixedvalue = request.args.get('fixedvalue')
    # list data position in file:
    try:
        data_location = None
        try:
            fixed_caddress = array(c_singleqb_structure[session['user_name']],dtype=int64)-1
            fixed_caddress[SQ_CParameters[session['user_name']].index(fixed)] = int(fixedvalue)
            fixed_caddress[SQ_CParameters[session['user_name']].index(fixed)+1:] = 0
            data_location = int(gotocdata(fixed_caddress, c_singleqb_structure[session['user_name']]))
        except(IndexError): 
            data_location = None
            print(Fore.RED + "Structure not properly setup")
        except(KeyError): 
            data_location = None
            print(Fore.YELLOW + "Not yet accessed any data")
        
    # except: raise
    except(ValueError):
        print(Back.RED + Fore.WHITE + "All parameters before branch must be FIXED!")
        pass

    print("Data location: %s" %data_location)
    return jsonify(data_location=data_location)
@bp.route('/mani/singleqb/resetdata', methods=['GET'])
def mani_singleqb_resetdata():
    ownerpassword = request.args.get('ownerpassword')
    truncateafter = int(request.args.get('truncateafter'))

    db = get_db()
    people = db.execute(
        'SELECT password FROM user WHERE username = ?', (session['people'],)
    ).fetchone()

    if check_password_hash(people['password'], ownerpassword):
        message = M_singleqb[session['user_name']].resetdata(truncateafter)
    else:
        message = 'PASSWORD NOT VALID'

    return jsonify(message=message)

# DATA PRESENTATION:
# Chart is supposedly shared by all measurements (under construction for multi-purpose)
@bp.route('/mani/singleqb/1ddata', methods=['GET'])
def mani_singleqb_1ddata():
    print(Fore.GREEN + "User %s is plotting SINGLEQB 1D-Data" %session['user_name'])
    M_singleqb[session['user_name']].loadata()
    selectedata = M_singleqb[session['user_name']].selectedata
    print("Data length: %s" %len(selectedata))
    
    # load parameter indexes from json call:
    cselect = json.loads(request.args.get('cselect'))

    for k in cselect.keys():
        if "x" in cselect[k]:
            xtitle = "<b>" + k + "</b>"
            selected_caddress = [s for s in cselect.values()]
        
            # Sweep-command:
            selected_sweep = M_singleqb[session['user_name']].corder[k]

            # Adjusting c-parameters range for data analysis based on progress:
            parent_address = selected_caddress[:SQ_CParameters[session['user_name']].index(k)] # address's part before x
            if [int(s) for s in parent_address] < c_singleqb_progress[session['user_name']][0:len(parent_address)]:
                print(Fore.YELLOW + "selection is well within progress")
                sweepables = c_singleqb_structure[session['user_name']][SQ_CParameters[session['user_name']].index(k)]
            else: sweepables = c_singleqb_progress[session['user_name']][SQ_CParameters[session['user_name']].index(k)]+1

            # Special treatment on the last 'buffer' parameter to factor out the data-density first: 
            if SQ_CParameters[session['user_name']].index(k) == len(SQ_CParameters[session['user_name']])-1 :
                isweep = range(sweepables//M_singleqb[session['user_name']].datadensity)
            else:
                isweep = range(sweepables) # flexible access until progress resume-point
            print(Back.WHITE + Fore.BLACK + "Sweeping %s points" %len(isweep))

            Idata = zeros(len(isweep))
            Qdata = zeros(len(isweep))
            Adata = zeros(len(isweep))
            Pdata = zeros(len(isweep))
            for i in isweep:
                # PENDING: VECTORIZATION OR MULTI-PROCESS
                selected_caddress[SQ_CParameters[session['user_name']].index(k)] = i # register x-th position
                if [c for c in cselect.values()][-1] == "s": # sampling mode currently limited to time-range (last 'basic' parameter) only
                    srange = request.args.get('srange').split(",") # sample range
                    smode = request.args.get('smode') # sampling mode
                    Idata[i], Qdata[i], Adata[i], Pdata[i] = \
                        pulseresp_sampler(srange, selected_caddress, selectedata, c_singleqb_structure[session['user_name']], M_singleqb[session['user_name']].datadensity, mode=smode)
                else:
                    # Ground level Pulse shape response:
                    selected_caddress = [int(s) for s in selected_caddress]
                    Basic = selected_caddress[-1]
                    # Extracting I & Q:
                    Idata[i] = selectedata[gotocdata(selected_caddress[:-1]+[2*Basic], c_singleqb_structure[session['user_name']])]
                    Qdata[i] = selectedata[gotocdata(selected_caddress[:-1]+[2*Basic+1], c_singleqb_structure[session['user_name']])]
                    Adata[i] = sqrt(Idata[i]**2 + Qdata[i]**2)
                    Pdata[i] = arctan2(Qdata[i], Idata[i]) # -pi < phase < pi    

    print("Structure: %s" %c_singleqb_structure[session['user_name']])
    # x-data:
    selected_progress = waveform(selected_sweep).data[0:len(isweep)]
    # facilitate index location (or count) for range clipping:
    cselection = (",").join([s for s in cselect.values()])
    if "c" in cselection:
        selected_progress = list(range(len(selected_progress)))

    x, yI, yQ, yA, yUFNP = selected_progress, list(Idata), list(Qdata), list(Adata), list(Pdata)
    singleqb_1Ddata[session['user_name']] = {xtitle: x, 'I': yI, 'Q': yQ, 'A(V)': yA, 'UFNP(rad/x)': yUFNP, "exported by": session['user_name']}
    
    return jsonify(x=x, yI=yI, yQ=yQ, yA=yA, yUFNP=yUFNP, xtitle=xtitle)

@bp.route('/mani/singleqb/2ddata', methods=['GET'])
def mani_singleqb_2ddata():
    print(Fore.GREEN + "User %s is plotting SINGLEQB 2D-Data using vectorization" %session['user_name'])
    M_singleqb[session['user_name']].loadata()
    selectedata = M_singleqb[session['user_name']].selectedata
    print("Data length: %s" %len(selectedata))
    
    # load parameter indexes from json call:
    cselect = json.loads(request.args.get('cselect'))

    try:
        x_loc = [k for k in cselect.values()].index('x')
        selected_x = [c for c in cselect.keys()][x_loc]
        y_loc = [k for k in cselect.values()].index('y')
        selected_y = [c for c in cselect.keys()][y_loc]
        xtitle = "<b>" + selected_x + "</b>"
        ytitle = "<b>" + selected_y + "</b>"
        selected_caddress = [s for s in cselect.values()]
    except: 
        print("x and y parameters not selected or not valid")
        
    # Adjusting c-parameters range for data analysis based on progress:
    parent_address = selected_caddress[:SQ_CParameters[session['user_name']].index(selected_x)] # address's part before x (higher-level data)
    if [int(s) for s in parent_address] < c_singleqb_progress[session['user_name']][0:len(parent_address)]: # must be matched with the parameter-select-range on the front-page
        print(Fore.YELLOW + "selection is well within progress")
        sweepables = [c_singleqb_structure[session['user_name']][SQ_CParameters[session['user_name']].index(selected_x)], c_singleqb_structure[session['user_name']][SQ_CParameters[session['user_name']].index(selected_y)]]
    else: 
        sweepables = [c_singleqb_progress[session['user_name']][SQ_CParameters[session['user_name']].index(selected_x)]+1, c_singleqb_progress[session['user_name']][SQ_CParameters[session['user_name']].index(selected_y)]+1]

            
    # flexible access until progress resume-point
    xsweep = range(sweepables[0])
    if SQ_CParameters[session['user_name']].index(selected_y) == len(SQ_CParameters[session['user_name']])-1 :
        # Special treatment on the last 'buffer' parameter to factor out the data-density first:
        ysweep = range(sweepables[1]//M_singleqb[session['user_name']].datadensity)
    else:
        ysweep = range(sweepables[1]) 
    print(Back.WHITE + Fore.BLACK + "Sweeping %s x-points" %len(xsweep))
    print(Back.WHITE + Fore.BLACK + "Sweeping %s y-points" %len(ysweep))

    Idata = zeros([len(ysweep), len(xsweep)])
    Qdata = zeros([len(ysweep), len(xsweep)])
    Adata = zeros([len(ysweep), len(xsweep)])
    Pdata = zeros([len(ysweep), len(xsweep)])
    for j in ysweep:
        if not (j+1)%10: print(Fore.CYAN + "Assembling 2D-DATA, x: %s/%s, y: %s/%s" %(i+1,len(xsweep),j+1,len(ysweep)))
        selected_caddress[SQ_CParameters[session['user_name']].index(selected_y)] = j # register y-th position
        for i in xsweep:
            selected_caddress[SQ_CParameters[session['user_name']].index(selected_x)] = i # register x-th position
            if [c for c in cselect.values()][-1] == "s": # sampling mode currently limited to time-range (last 'basic' parameter) only
                srange = request.args.get('srange').split(",") # sample range
                smode = request.args.get('smode') # sampling mode
                Idata[j,i], Qdata[j,i], Adata[j,i], Pdata[j,i] = \
                    pulseresp_sampler(srange, selected_caddress, selectedata, c_singleqb_structure[session['user_name']], M_singleqb[session['user_name']].datadensity, mode=smode)

            else:
                # Ground level Pulse shape response:
                selected_caddress = [int(s) for s in selected_caddress]
                Basic = selected_caddress[-1]
                # Extracting I & Q:
                Idata[j,i] = selectedata[gotocdata(selected_caddress[:-1]+[2*Basic], c_singleqb_structure[session['user_name']])]
                Qdata[j,i] = selectedata[gotocdata(selected_caddress[:-1]+[2*Basic+1], c_singleqb_structure[session['user_name']])]  

    print("Mapping complete. Structure: %s" %c_singleqb_structure[session['user_name']])
    
    # x-data:
    selected_xsweep = M_singleqb[session['user_name']].corder[selected_x]
    x = waveform(selected_xsweep).data[0:len(xsweep)]

    # y-data:
    selected_ysweep = M_singleqb[session['user_name']].corder[selected_y]
    y = waveform(selected_ysweep).data[0:len(ysweep)]
    
    # IQ-data:
    Adata = sqrt(Idata**2 + Qdata**2)
    UPdata = unwrap(arctan2(Qdata, Idata)) # -pi < phase < pi -> Unwrapped

    # Packing data into dictionary:
    ZZI, ZZQ, ZZA, ZZUP = Idata.tolist(), Qdata.tolist(), Adata.tolist(), UPdata.tolist()
    singleqb_2Ddata[session['user_name']] = dict(x=x, y=y, ZZI=ZZI, ZZQ=ZZQ, ZZA=ZZA, ZZUP=ZZUP, xtitle=xtitle, ytitle=ytitle)

    # executor.submit(fn, args).add_done_callback(handler)

    return jsonify(x=x, y=y, ZZI=ZZI, ZZQ=ZZQ, ZZA=ZZA, ZZUP=ZZUP, xtitle=xtitle, ytitle=ytitle)



# endregion

# region: benchmark

@bp.route( '/send_datainfo', methods=['POST', 'GET'])
def send_datainfo():
    # Build the JSON file that benchmark can get the information of measurement

    measurementType = request.args.get('measurementType')
    current_usr = session['user_name']

    structurelable = ["Flux-Bias","S-Parameter", "IF-Bandwidth", "Power", "Frequency"]
    htmlId = ["FluxBias","SParameter", "IFBandwidth", "Power", "Frequency"]


    parameterInfo = []
    parameterValues = []
    c_structure = []
    c_address = []
    maxInd = 0
    for i, v in enumerate(structurelable):
        try: parameterInfo.append( waveform(M_fresp[current_usr].corder[v]) )
        except(KeyError): parameterInfo.append( waveform('opt,') )
        #parameterInfo.append( waveform(M_fresp[current_usr].corder[v]) )
        maxInd = i
        c_structure.append( parameterInfo[i].count )
        print(parameterInfo[i].count)

    #print(M_fresp[current_usr].datadensity)
    c_structure[maxInd] *= M_fresp[current_usr].datadensity
    #session['c_fresp_address'] = cdatasearch(M_fresp[current_usr].resumepoint-1, session['c_fresp_structure'])
    c_address.append( cdatasearch(M_fresp[current_usr].resumepoint-1, c_structure) )
    c_address = c_address[0]

    # list each parameter range based on data-progress:
    for i in range(maxInd):
        parameterValues.append( parameterInfo[i].data[0:c_address[i]+1] )
    parameterValues.append( parameterInfo[maxInd].data)

    parameterList = [{"lable":lable, "htmlId":hid, "length":len(values), "values":values} for lable,hid,values in zip(structurelable,htmlId,parameterValues)]
    measurement = { "type":measurementType,  "parameters": parameterList, }
    MP_BencmarkDict = {
            "pqfile": str(M_fresp[current_usr].pqfile), "datalocation": M_fresp[current_usr].datalocation, "writtensize": M_fresp[current_usr].writtensize,
            "measurement": measurement, "c_structure": c_structure, 
        }
    set_status("MP_benchmark", MP_BencmarkDict)
    print("file path: " + MP_BencmarkDict["pqfile"])
    jsonFileName = "measurement_info["+current_usr+"]"
    set_json_measurementinfo(MP_BencmarkDict,jsonFileName)
    return jsonify(MP_BencmarkDict)

print(Back.BLUE + Fore.CYAN + myname + ".bp registered!") # leave 2 lines blank before this
# endregion


# OK
