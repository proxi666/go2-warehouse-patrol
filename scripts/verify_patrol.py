"""Offline patrol acceptance from immutable observations, motion, and service evidence."""
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_attempt import VerificationFailure, basename, finite, vector, prompt_identity
from warehouse_incident.cosmos import MODEL, REVISION, parse_answer, strict_json
from warehouse_incident.runtime_gates import arrival, angle_error, parking_ready


def verify_patrol(attempt, evidence_root=None):
    """Fail closed; never execute historical Python or mutate an attempt."""
    evidence = Path(evidence_root) if evidence_root is not None else ROOT / 'evidence'
    folder = evidence / basename(attempt)
    report = {'status':'failed', 'attempt':attempt, 'failed_reasons':[], 'metrics':{},
              'limitations':['Frontend served-version provenance is a separate dashboard artifact; this report verifies recorded state only.'],
              'input_sha256':{}}
    metrics = report['metrics']

    def require(condition, message):
        if not condition: raise VerificationFailure(message)

    def read(path):
        data = Path(path).read_bytes()
        report['input_sha256'][str(path)] = hashlib.sha256(data).hexdigest()
        return data

    def load(path): return strict_json(read(path))

    def image(path):
        from PIL import Image
        with Image.open(io.BytesIO(read(path))) as picture:
            require(picture.format in ('PNG','JPEG'), 'Unsupported camera format')
            picture.verify()

    def identity(obj, revision='revision'):
        require(isinstance(obj,dict) and obj.get('model') == MODEL and obj.get(revision) == REVISION,
                'Cosmos model/revision mismatch')

    def checked_files(base, hashes):
        require(isinstance(hashes,dict) and bool(hashes), 'Required file hash map missing')
        base = base.resolve()
        for relative, digest in hashes.items():
            path = (base / relative).resolve()
            require(not Path(relative).is_absolute() and path.is_relative_to(base), 'Evidence path escapes hash root')
            require(hashlib.sha256(read(path)).hexdigest() == digest, 'File identity changed: '+relative)

    try:
        result = load(folder / 'result.json')
        require(result.get('mode') == 'patrol' and result.get('status') == 'passed', 'Native patrol did not pass')
        require(result.get('native_robot_motion') is True and result.get('cosmos_inference') is True,
                'Native/model evidence flags missing')
        require(result.get('cleanup_errors') == [], 'Owned cleanup was not verified successful')
        case = result.get('case'); require(case in ('blocked','clear'), 'Unsupported patrol case')
        launch = load(folder / 'identity.json')
        sources = result.get('source_sha256')
        require(launch.get('source_sha256') == sources, 'Launch/final source identities differ')
        required = {'scripts/run_native.py','src/warehouse_incident/patrol.py','src/warehouse_incident/core.py',
                    'src/warehouse_incident/runtime_gates.py','src/warehouse_incident/cosmos.py','config/patrol.json'}
        require(isinstance(sources,dict) and required <= sources.keys(), 'Required patrol source identities missing')
        checked_files(folder / 'source', sources)
        config = load(folder / 'source/config/patrol.json')
        aisles = config['aisles']; ids = [a['id'] for a in aisles]
        require(ids == ['aisle-1','aisle-2','aisle-3'], 'Expected three ordered inspection aisles')
        require(config.get('cosmos_model') == MODEL and config.get('cosmos_revision') == REVISION, 'Configuration model mismatch')
        max_age = finite(config['max_age_s'],'max_age_s'); require(max_age > 0,'Invalid observation age bound')
        tolerance = finite(config.get('view_tolerance_m',.15),'view_tolerance_m')
        require(0 < tolerance <= .3, 'Patrol view_tolerance_m must be positive and at most 0.3 m')
        assets = (evidence.parent / 'assets').resolve()
        stage = Path(result['runtime_arguments']['stage']).resolve()
        require(stage.is_relative_to(assets), 'Stage escapes project assets')
        require(hashlib.sha256(read(stage)).hexdigest() == result['stage_sha256'], 'Scene root identity changed')
        checked_files(assets, result.get('scene_files_sha256'))
        checked_files(assets / 'source/V39', result.get('warehouse_source_sha256'))
        health = result.get('cosmos_health'); identity(health)
        require(health.get('task') == 'patrol' and health.get('prompt_name') == 'PATROL_PROMPT',
                'Patrol requires task=patrol and prompt_name=PATROL_PROMPT')
        require(health.get('status') == 'ready', 'Service not ready at launch')
        snapshot_cosmos = read(folder / 'source/src/warehouse_incident/cosmos.py')
        metrics['prompt_sha256'] = prompt_identity(snapshot_cosmos, health)
        require(load(folder / 'contacts.json') == [], 'Relevant contact occurred or contacts missing')
        rows = load(folder / 'trajectory.json')
        require(isinstance(rows,list) and len(rows) >= 2, 'Insufficient trajectory')
        for row in rows:
            finite(row['t'],'trajectory time'); vector(row['dog'],4,'dog pose'); vector(row['command'],3,'body command')
            require(finite(row['up'],'upright projection') > .65 and row['dog'][2] > .2, 'Dog failed upright/height acceptance')
        require(all(0 < b['t']-a['t'] <= .2 for a,b in zip(rows,rows[1:])), 'Unordered or sparse trajectory')
        require(any(r.get('dof_positions') for r in rows) and any(r.get('policy_action') for r in rows), 'Native joint/policy measurements missing')
        events = [strict_json(line) for line in read(folder / 'events.jsonl').splitlines() if line.strip()]
        for event in events:
            finite(event['time_s'],'event time'); finite(event['wall_time'],'event wall time')
        require(all(a['time_s'] <= b['time_s'] for a,b in zip(events,events[1:])), 'Unordered events')
        require(not any(e['event'] == 'assessment_failed' for e in events), 'Inference failure recorded')
        frames = list(folder.glob('frame-*.jpg')); require(bool(frames),'Robot camera sequence missing')
        for path in frames: image(path)

        def measured(event, target, settled=False):
            t = event['time_s']; near = min(rows,key=lambda row:abs(row['t']-t))
            require(abs(near['t']-t) <= .15, 'No trajectory sample near physical event')
            preceding = [row for row in rows if row['t'] <= t]
            following = [row for row in rows if row['t'] >= t]
            # Physical events run faster than saved trajectory samples. Estimate
            # pose at the event's own time, without expanding arrival tolerance.
            p = list(near['dog'])
            if preceding and following:
                left, right = preceding[-1], following[0]
                span = right['t']-left['t']
                if span > 0:
                    require(span <= .2, 'Trajectory cannot bracket physical event')
                    fraction = (t-left['t'])/span
                    p = [a+fraction*(b-a) for a,b in zip(left['dog'][:3],right['dog'][:3])]
                    p.append(left['dog'][3]+fraction*angle_error(right['dog'][3],left['dog'][3]))
            if settled:
                before = [r for r in rows if r['t'] <= t + .001]
                require(before and t-before[-1]['t'] <= .15 and parking_ready(before,target,tolerance=tolerance), 'Measured settled dwell absent')
            # The event contains an actual native pose sampled at its own time.
            # Apply the exact arrival bound to it; interpolation is a consistency
            # check, not an assumption of perfectly linear motion between rows.
            if 'pose' in event:
                recorded = vector(event['pose'],4,'phase pose')
            elif 'observation' in event:
                obs_pose = vector(event['observation']['pose'],3,'observation pose')
                recorded = [obs_pose[0],obs_pose[1],p[2],obs_pose[2]]
            else:
                recorded = p
            require(arrival((recorded[0],recorded[1],recorded[3]),target,tolerance=tolerance), 'Phase event pose differs from physical target')
            require(math.dist(recorded[:2],p[:2]) <= .04 and abs(angle_error(recorded[3],p[3])) <= .08,
                    'Phase event pose disagrees with time-aligned trajectory')

        index, phase, pending = 0, 'MOVE', None
        observations, requests, records = set(), set(), {i:[] for i in ids}
        statuses = {i:'uninspected' for i in ids}; completed = False
        for event in events:
            kind = event['event']
            if kind == 'patrol_phase':
                require(pending is None, 'Physical phase advanced during inference')
                if phase == 'MOVE':
                    target = aisles[index].get('entry', [*aisles[index]['mouth'][:2],0.]); next_phase = 'LOOK'; dwell = False
                elif phase in ('LOOK','APPROACH'):
                    target = aisles[index]['mouth' if phase == 'LOOK' else 'confirm']; next_phase = 'ASSESS'; dwell = True
                elif phase == 'FACE_FORWARD':
                    target = aisles[index].get('forward', [*aisles[index]['mouth'][:2],0.]); next_phase = 'MOVE' if index < 2 else 'RETURN'; dwell = True
                    index += 1
                elif phase == 'RETURN':
                    target = config['park']; next_phase = 'COMPLETE'; dwell = True
                else: raise VerificationFailure('Unexpected physical phase transition')
                require(event['phase'] == next_phase, 'Physical phase sequence differs from inspection protocol')
                require(event.get('aisle') == (ids[index] if index < 3 else None), 'Phase aisle order mismatch')
                measured(event,target,dwell); phase = next_phase
            elif kind == 'assessment_requested':
                require(phase == 'ASSESS' and pending is None and index < 3, 'Assessment outside ordered settled inspection')
                obs = event['observation']; oid = basename(obs['id'])
                require(oid not in observations, 'Observation ID reused'); observations.add(oid)
                require(obs['edge_id'] == ids[index] and event.get('aisle') == ids[index], 'Observation aisle mismatch')
                target = aisles[index]['mouth' if not records[ids[index]] else 'confirm']
                measured(event,target,True)
                p = vector(obs['pose'],3,'observation pose'); require(arrival(p,target,tolerance=tolerance),'Observation pose differs from target')
                finite(obs['captured_at'],'capture time')
                filename = 'observation-'+oid+'.png'; image(folder / filename)
                pending = (obs,filename,hashlib.sha256(read(folder / filename)).hexdigest())
            elif kind == 'assessment_received':
                require(phase == 'ASSESS' and pending is not None,'Unpaired assessment response')
                obs,filename,digest = pending; aid = ids[index]; meta = event['metadata']; identity(meta,'model_revision')
                require(event.get('aisle') == aid,'Answer aisle mismatch')
                rid = basename(meta['id']); require(rid not in requests,'Request ID reused'); requests.add(rid)
                matches = list(evidence.glob('cosmos-*/requests/'+rid+'.json'))
                require(len(matches) == 1,'Expected exactly one service request record')
                record = load(matches[0]); identity(record); prompt_identity(snapshot_cosmos,health,record)
                require(record.get('request_id') == rid and record.get('status') == 'inferred','Service request did not infer')
                require(record.get('image_sha256') == digest,'Camera/request image hash mismatch')
                answer = parse_answer(record['raw_response'])
                require(record.get('assessment') == {'status':answer.status,'reason':answer.reason}, 'Service raw answer differs from assessment')
                require(event.get('status') == answer.status and event.get('reason') == answer.reason,'Event differs from model answer')
                require(answer.status in ('clear','blocked'), 'Uncertain answer cannot complete patrol')
                require(0 <= event['wall_time']-obs['captured_at'] <= max_age,'Stale/future observation')
                latency = finite(record['latency_s'],'inference latency')
                require(latency >= 0 and finite(meta['latency_s'],'response latency') == latency, 'Inference latency mismatch')
                started = finite(record['started_at'],'service request start')
                require(obs['captured_at'] <= started <= event['wall_time'] and started+latency <= event['wall_time']+.05,
                        'Service timing inconsistent with capture/receipt')
                prior = records[aid]
                if not prior:
                    phase = 'FACE_FORWARD' if answer.status == 'clear' else 'APPROACH'
                    statuses[aid] = 'clear' if answer.status == 'clear' else 'inspecting'
                else:
                    require(len(prior) == 1 and prior[0]['status'] == answer.status == 'blocked', 'Contradictory/excess confirmation')
                    first = prior[0]
                    require(first['captured_at'] <= obs['captured_at'] and 0 <= event['wall_time']-first['captured_at'] <= max_age,'First view expired or second view predates it')
                    require(math.dist(first['pose'][:2],obs['pose'][:2]) >= .5,'Confirmation viewpoints too close')
                    phase = 'FACE_FORWARD'; statuses[aid] = 'obstructed'
                require(event.get('phase') == phase,'Answer transition mismatch')
                prior.append({'id':obs['id'],'captured_at':obs['captured_at'],'pose':obs['pose'],'image':filename,
                              'status':answer.status,'reason':answer.reason,'metadata':meta,'received_wall':event['wall_time']})
                pending = None
            elif kind == 'patrol_complete':
                require(phase == 'COMPLETE' and not completed and event.get('aisles') == statuses,'Invalid completion event')
                completed = True
        require(completed and pending is None and phase == 'COMPLETE','Patrol did not physically complete')
        expected = {aid:('obstructed' if case == 'blocked' and aid == 'aisle-3' else 'clear') for aid in ids}
        require(statuses == expected,'Independent post-hoc classification acceptance failed')
        require(result.get('evaluation') == {'observed':statuses,'expected':expected,'passed':True}, 'Native evaluation differs from recomputed result')
        state = load(folder / 'patrol-state.json')
        require(state.get('attempt') == attempt and state.get('phase') == 'COMPLETE' and state.get('complete') is True
                and state.get('native_status') == 'passed' and not state.get('runtime_error'), 'Final dashboard completion flags mismatch')
        require([a['id'] for a in state['aisles']] == ids, 'Final dashboard aisle order mismatch')
        require(state.get('view_tolerance_m',.15) == tolerance, 'Dashboard view tolerance differs from configuration')
        require(state.get('park') == config['park'] and state.get('max_age_s') == max_age, 'Dashboard parking/age configuration mismatch')
        require(finite(state['updated_at'],'state update') >= events[-1]['wall_time'], 'Final dashboard predates completion')
        require(abs(finite(state['sim_seconds'],'state simulation time')-finite(result['sim_seconds'],'result simulation time')) <= .001,
                'Dashboard/result simulation clocks differ')
        for aisle, configured in zip(state['aisles'],aisles):
            require(aisle.get('mouth') == configured['mouth'] and aisle.get('confirm') == configured['confirm'], 'Dashboard layout differs from configuration')
            for point in ('entry','forward'):
                expected_point = configured.get(point,[*configured['mouth'][:2],0.])
                require(aisle.get(point,[*aisle['mouth'][:2],0.]) == expected_point, 'Dashboard '+point+' differs from configuration')
            aid = aisle['id']; require(aisle['status'] == statuses[aid], 'Dashboard classification mismatch')
            saved = aisle['evidence']; require(len(saved) == len(records[aid]), 'Dashboard evidence count mismatch')
            require(aisle.get('reason') == records[aid][-1]['reason'], 'Dashboard reason differs from accepted answer')
            require(aisle.get('latencies') == [r['metadata']['latency_s'] for r in records[aid]], 'Dashboard latencies differ from inference evidence')
            for actual, expected_record in zip(saved,records[aid]):
                for key in ('id','captured_at','pose','image','status','reason','metadata'):
                    require(actual.get(key) == expected_record[key], 'Dashboard observation differs: '+key)
                require(0 <= finite(actual['received_at'],'dashboard receipt')-actual['captured_at'] <= max_age,
                        'Dashboard observation age invalid')
                require(0 <= expected_record['received_wall']-actual['received_at'] <= 1., 'Dashboard/model receipt time mismatch')
        expected_alerts = ['Object detected in aisle 3. Kindly clear it.'] if case == 'blocked' else []
        require(state.get('alerts') == expected_alerts,'Operator alert differs from confirmed incident')
        require(parking_ready(rows,config['park'],tolerance=tolerance), 'Final physical parking dwell absent')
        require(arrival(vector(state['pose'],3,'final dashboard pose'),config['park'],tolerance=tolerance), 'Dashboard final pose outside park')
        dashboard = evidence / ('dashboard-'+attempt+'-provenance')
        if dashboard.exists():
            frontend = load(dashboard / 'IDENTITY.json')
            require(frontend.get('attempt') == attempt, 'Frontend provenance names another attempt')
            require(hashlib.sha256(read(dashboard / 'index.html')).hexdigest() == frontend.get('frontend_sha256'), 'Served frontend hash mismatch')
            for name in ('scripts/dashboard_server.py','app'):
                require(hashlib.sha256(read(dashboard / Path(name).name)).hexdigest() == frontend.get('source_sha256',{}).get(name), 'Dashboard server/launcher source hash mismatch')
            metrics['frontend_provenance_verified'] = str(dashboard)
            report['limitations'] = ['Served frontend identity verified; browser rendering and interaction require separate browser evidence.']
        metrics.update(aisles=statuses, observations=len(observations), requests=len(requests), trajectory_rows=len(rows),
                       camera_frames=len(frames), minimum_up=min(r['up'] for r in rows),
                       minimum_height_m=min(r['dog'][2] for r in rows), parking_ready=True)
        report['status'] = 'passed'
    except (ValueError,TypeError,KeyError,IndexError,OSError,SyntaxError,AttributeError) as error:
        report['failed_reasons'].append(f'{type(error).__name__}: {error}')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt',required=True,type=basename)
    parser.add_argument('--verification',required=True,type=basename)
    args = parser.parse_args()
    if args.attempt == args.verification: parser.error('Verification must use a separate new folder')
    out = ROOT / 'evidence' / args.verification; out.mkdir(parents=True,exist_ok=False)
    dependencies = [Path(__file__),ROOT/'scripts/verify_attempt.py',ROOT/'src/warehouse_incident/runtime_gates.py',
                    ROOT/'src/warehouse_incident/cosmos.py',ROOT/'src/warehouse_incident/core.py']
    hashes = {}
    for source in dependencies:
        relative = source.relative_to(ROOT); data = source.read_bytes(); hashes[str(relative)] = hashlib.sha256(data).hexdigest()
        target = out/'source'/relative; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data)
    (out/'identity.json').write_text(json.dumps({'attempt':args.attempt,'started_at':time.time(),'offline':True,
                                               'attempt_mutated':False,'source_sha256':hashes},indent=2))
    report = verify_patrol(args.attempt); report['finished_at'] = time.time()
    (out/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({'status':report['status'],'verification':str(out),'failed_reasons':report['failed_reasons']}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
