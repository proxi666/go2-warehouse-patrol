"""Measured native acceptance; scenario truth is used only after control."""
import math

def angle_error(target,yaw):return math.atan2(math.sin(target-yaw),math.cos(target-yaw))

def arrival(pose,target,tolerance=.15):
    return math.dist(pose[:2],target[:2])<=tolerance and (len(target)==2 or abs(angle_error(target[2],pose[2]))<=.12)

def baseline_gates(rows):
    if not rows:return {'passed':False,'reason':'No measured trajectory'}
    forward=[r for r in rows if 3<=r['t']<=11.1]
    turn=[r for r in rows if 10.8<=r['t']<=18.1]
    stop=[r for r in rows if r['t']>=18]
    if min(len(forward),len(turn),len(stop))<2:return {'passed':False,'reason':'Insufficient phase measurements'}
    yaw=rows[0]['dog'][3];origin=forward[0]['dog']
    displacement=max((r['dog'][0]-origin[0])*math.cos(yaw)+(r['dog'][1]-origin[1])*math.sin(yaw) for r in forward)
    yaw_change=abs(angle_error(turn[-1]['dog'][3],turn[0]['dog'][3]))
    drift=max(math.dist(r['dog'][:2],stop[0]['dog'][:2]) for r in stop)
    yaw_drift=max(abs(angle_error(r['dog'][3],stop[0]['dog'][3])) for r in stop)
    result={'upright':all(r['up']>.65 and r['dog'][2]>.2 for r in rows),'forward_displacement_m':displacement,
            'yaw_change_rad':yaw_change,'stop_drift_m':drift,'stop_yaw_drift_rad':yaw_drift,'duration_s':rows[-1]['t']}
    result['passed']=result['upright'] and displacement>=1 and 1.35<=yaw_change<=1.8 and drift<=.15 and yaw_drift<=.08 and rows[-1]['t']>=19.9
    return result

def parking_ready(rows,target,dwell=1.,tolerance=.15):
    if len(rows)<2:return False
    last=rows[-1]['t'];recent=[r for r in rows if r['t']>=last-dwell-.15]
    if len(recent)<2 or recent[-1]['t']-recent[0]['t']<dwell:return False
    for row in recent:
        p=row['dog']
        if not arrival((p[0],p[1],p[3]),target,tolerance=tolerance):return False
    for a,b in zip(recent,recent[1:]):
        dt=b['t']-a['t']
        if dt<=0 or math.dist(a['dog'][:2],b['dog'][:2])/dt>.1 or abs(angle_error(b['dog'][3],a['dog'][3]))/dt>.25:return False
    return True

def demo_gates(case,events,closed,initial_route,route,error):
    answers=[e for e in events if e['event']=='assessment_received']
    if case=='blocked':correct=len(answers)==2 and all(e['status']=='blocked' for e in answers) and closed==['main_aisle'] and route!=initial_route
    elif case in ('clear','off-route'):correct=len(answers)==1 and answers[0]['status']=='clear' and not closed and route==initial_route
    else:raise ValueError('Unknown evaluation case')
    return {'incident_correct':correct,'delivery_correct':error<=.15,'passed':correct and error<=.15}
