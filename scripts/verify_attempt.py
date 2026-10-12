"""Recompute completed demo acceptance from immutable saved native evidence.

Run with --attempt NAME --verification NEW_NAME. No simulator/model starts, no
attempt files are changed, and missing result.json fails without waiting. The
verification directory contains this verifier's identity and a measured report.
"""
import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from warehouse_incident.core import shortest_path
from warehouse_incident.cosmos import MODEL, REVISION, parse_answer, strict_json
from warehouse_incident.runtime_gates import arrival, demo_gates, parking_ready


class VerificationFailure(ValueError):
    pass


def basename(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',value):
        raise ValueError('attempt and verification must be single directory names')
    return value


def finite(value, label):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise VerificationFailure(f'{label} must be finite numeric evidence')
    return value


def vector(value, length, label):
    if not isinstance(value,list) or len(value)!=length:
        raise VerificationFailure(f'{label} requires {length} coordinates')
    return [finite(v,label) for v in value]


def prompt_identity(source, health, record=None):
    """Bind immutable prompt text to service evidence without executing snapshot code."""
    known = {'incident':'PROMPT', 'patrol':'PATROL_PROMPT'}
    if not isinstance(health, dict):
        raise VerificationFailure('Saved health must identify a known prompt task')
    task, name = health.get('task', 'incident'), health.get('prompt_name', 'PROMPT')
    if not isinstance(task, str) or task not in known or name != known[task]:
        raise VerificationFailure('Saved health task and prompt_name are unknown or inconsistent')
    tree = ast.parse(source)
    assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == name
                           for target in node.targets)]
    if len(assignments) != 1:
        raise VerificationFailure(f'Snapshot must contain one literal {name} assignment')
    try:
        prompt = ast.literal_eval(assignments[0].value)
    except (ValueError, TypeError) as error:
        raise VerificationFailure('Snapshot PROMPT must be a literal string') from error
    if not isinstance(prompt, str):
        raise VerificationFailure('Snapshot PROMPT must be a literal string')
    expected = hashlib.sha256(prompt.encode()).hexdigest()
    if not isinstance(health, dict) or health.get('prompt_sha256') != expected:
        raise VerificationFailure('Saved health prompt SHA256 differs from snapshot PROMPT')
    system_name, system_hash = None, None
    if task == 'patrol':
        system_name = 'PATROL_SYSTEM'
        if health.get('system_prompt_name') != system_name:
            raise VerificationFailure('Patrol health requires known system_prompt_name PATROL_SYSTEM')
        system_nodes = [node for node in tree.body if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == system_name
                                for target in node.targets)]
        if len(system_nodes) != 1:
            raise VerificationFailure('Snapshot must contain one literal PATROL_SYSTEM assignment')
        try:
            system_text = ast.literal_eval(system_nodes[0].value)
        except (ValueError, TypeError) as error:
            raise VerificationFailure('Snapshot PATROL_SYSTEM must be a literal string') from error
        if not isinstance(system_text, str):
            raise VerificationFailure('Snapshot PATROL_SYSTEM must be a literal string')
        system_hash = hashlib.sha256(system_text.encode()).hexdigest()
        if health.get('system_prompt_sha256') != system_hash:
            raise VerificationFailure('Saved health system prompt SHA256 differs from snapshot PATROL_SYSTEM')
    elif health.get('system_prompt_name') is not None or health.get('system_prompt_sha256') is not None:
        raise VerificationFailure('Incident task cannot claim a system prompt')
    sources = health.get('source_sha256')
    required = ('scripts/cosmos_server.py', 'src/warehouse_incident/cosmos.py',
                'src/warehouse_incident/core.py')
    if not isinstance(sources, dict) or any(not isinstance(sources.get(key), str)
            or not re.fullmatch(r'[0-9a-f]{64}', sources[key]) for key in required):
        raise VerificationFailure('Saved health lacks required service source SHA256 identity')
    if record is not None:
        if not isinstance(record, dict) or (record.get('task', 'incident'), record.get('prompt_name', 'PROMPT')) != (task, name):
            raise VerificationFailure('Request task/prompt_name differs from saved health')
        if record.get('system_prompt_name') != system_name or record.get('system_prompt_sha256') != system_hash:
            raise VerificationFailure('Request system prompt identity differs from saved health')
        if record.get('prompt_sha256') != expected:
            raise VerificationFailure('Request prompt SHA256 differs from snapshot PROMPT')
        if record.get('source_sha256') != sources:
            raise VerificationFailure('Request service source SHA256 differs from saved health')
    return expected


def verify(attempt, evidence_root=None):
    """Return a report; failed conditions never reuse the native pass verdict."""
    evidence_root = Path(evidence_root) if evidence_root is not None else ROOT / 'evidence'
    folder = evidence_root / basename(attempt)
    report = {'status':'failed','attempt':attempt,'failed_reasons':[], 'metrics':{},
              'limitations':[], 'input_sha256':{}}
    failures, metrics = report['failed_reasons'], report['metrics']

    def check(condition, reason):
        if not condition:
            failures.append(reason)

    def read(path):
        path = Path(path)
        if not path.is_file():
            raise VerificationFailure(f'Missing required evidence: {path}')
        data = path.read_bytes()
        report['input_sha256'][str(path)] = hashlib.sha256(data).hexdigest()
        return data

    def load(path):
        try:
            return strict_json(read(path))
        except ValueError as error:
            raise VerificationFailure(f'Invalid JSON evidence {path}: {error}') from error

    def identity(value,label,revision_key='revision'):
        check(isinstance(value,dict) and value.get('model')==MODEL and value.get(revision_key)==REVISION,
              f'{label}: model/revision must match pinned {MODEL}@{REVISION}')

    try:
        result = load(folder / 'result.json')
        if not isinstance(result,dict):raise VerificationFailure('result.json must be an object')
        case = result.get('case')
        if case not in ('blocked','clear','off-route'):raise VerificationFailure('Unknown or missing evaluation case')
        report['case'] = case
        check(result.get('status')=='passed','Native result.status is not passed; inspect result.error')
        check(isinstance(result.get('evaluation'),dict) and result['evaluation'].get('passed') is True,
              'Native case evaluation is not passed')
        check(result.get('mode')=='demo','Attempt is not a native demo')
        check(result.get('native_robot_motion') is True,'Native robot motion not established by result')
        check(result.get('cosmos_inference') is True,'Cosmos inference not established by result')
        original_identity = load(folder / 'identity.json')
        sources = result.get('source_sha256')
        if not isinstance(sources,dict) or not sources:raise VerificationFailure('Missing source_sha256 identity')
        check(original_identity.get('source_sha256')==sources,'Launch identity source hashes differ from final result')
        for required in ('scripts/run_native.py','src/warehouse_incident/core.py',
                         'src/warehouse_incident/runtime_gates.py','src/warehouse_incident/cosmos.py','config/mission.json'):
            check(required in sources,f'Source identity omitted required file: {required}')
        source_root = (folder / 'source').resolve()
        for relative, expected in sources.items():
            if not isinstance(relative,str) or Path(relative).is_absolute() or '..' in Path(relative).parts:
                raise VerificationFailure('Unsafe path in source_sha256 identity')
            path = (source_root / relative).resolve()
            if not path.is_relative_to(source_root):raise VerificationFailure('Source path escapes immutable source copy')
            actual = hashlib.sha256(read(path)).hexdigest()
            check(actual==expected,f'Copied source hash mismatch: {relative}; preserve attempt, inspect source copy')
        metrics['source_files_verified'] = len(sources)
        stage_path = result.get('runtime_arguments',{}).get('stage')
        if result.get('stage_sha256') and stage_path:
            path = Path(stage_path).resolve()
            if not path.is_relative_to((ROOT / 'assets').resolve()):
                raise VerificationFailure('Recorded scene path escapes project assets')
            check(hashlib.sha256(read(path)).hexdigest()==result['stage_sha256'],
                  'Immutable scene stage SHA256 differs from native result')
            metrics['stage_sha256_verified'] = True
        else:
            report['limitations'].append('Native result omitted scene stage SHA256; scene identity not independently verified')
        scene_hashes = result.get('scene_files_sha256')
        if scene_hashes is None:
            report['limitations'].append('Native result omitted full scene_files_sha256; stage root identity verified when recorded, dependency provenance remains limited')
        else:
            if not isinstance(scene_hashes,dict) or not scene_hashes:
                raise VerificationFailure('Recorded scene_files_sha256 is empty or malformed')
            assets = (ROOT / 'assets').resolve()
            for relative,expected in scene_hashes.items():
                path = (assets / relative).resolve()
                if not path.is_relative_to(assets):raise VerificationFailure('Scene dependency path escapes project assets')
                check(hashlib.sha256(read(path)).hexdigest()==expected,f'Scene dependency SHA256 changed: {relative}')
            metrics['scene_dependency_files_verified'] = len(scene_hashes)
        config = load(source_root / 'config/mission.json')
        check(config.get('cosmos_model')==MODEL and config.get('cosmos_revision')==REVISION,
              'Copied mission configuration does not identify pinned Cosmos')
        health = result.get('cosmos_health')
        identity(health,'Saved Cosmos health')
        snapshot_cosmos = read(source_root / 'src/warehouse_incident/cosmos.py')
        metrics['prompt_sha256_verified'] = prompt_identity(snapshot_cosmos, health)
        check(isinstance(health,dict) and health.get('status')=='ready','Saved Cosmos health is not ready')
        events = []
        for number,line in enumerate(read(folder / 'events.jsonl').splitlines(),1):
            if not line.strip():continue
            event = strict_json(line)
            if not isinstance(event,dict) or not isinstance(event.get('event'),str):
                raise VerificationFailure(f'Malformed event at line {number}')
            finite(event.get('time_s'),f'event line {number} time_s')
            events.append(event)
        if not events:raise VerificationFailure('No measured events')
        check(all(a['time_s']<=b['time_s'] for a,b in zip(events,events[1:])),
              'Simulation event timestamps are not ordered')
        check(not any(e['event']=='assessment_failed' for e in events),'Assessment failure was recorded in this attempt')
        rows = load(folder / 'trajectory.json')
        if not isinstance(rows,list) or len(rows)<2:raise VerificationFailure('Trajectory has insufficient measured rows')
        for index,row in enumerate(rows):
            if not isinstance(row,dict):raise VerificationFailure(f'Malformed trajectory row {index}')
            finite(row.get('t'),f'row {index} t')
            vector(row.get('dog'),4,f'row {index} dog')
            vector(row.get('amr'),4,f'row {index} amr')
            finite(row.get('up'),f'row {index} up')
        check(all(a['t']<b['t'] for a,b in zip(rows,rows[1:])), 'Trajectory timestamps must strictly increase')
        metrics['trajectory_rows'] = len(rows)
        metrics['minimum_up'] = min(r['up'] for r in rows)
        metrics['minimum_dog_height_m'] = min(r['dog'][2] for r in rows)
        check(metrics['minimum_up']>.65,'Dog upright projection did not stay above 0.65')
        check(metrics['minimum_dog_height_m']>.2,'Dog body height did not stay above 0.2 m')
        contacts = load(folder / 'contacts.json')
        check(contacts==[],'Contacts are nonempty or malformed; inspect contacts.json')
        frames = sorted(folder.glob('frame-*.jpg'))
        check(bool(frames),'Robot camera frame sequence is missing')
        for frame in frames:
            data = read(frame)
            check(data.startswith(b'\xff\xd8\xff'),f'Camera frame is empty or lacks JPEG signature: {frame.name}')
        metrics['camera_frames'] = len(frames)

        pending, pairs, observation_ids, request_ids = None, [], set(), set()
        for index,event in enumerate(events):
            if event['event']=='assessment_requested':
                if pending is not None:raise VerificationFailure('Assessment requests overlap or are not paired in order')
                observation = event.get('observation')
                if not isinstance(observation,dict):raise VerificationFailure('Assessment request lacks observation')
                oid = basename(observation.get('id'))
                check(oid not in observation_ids,'Observation ID was reused')
                observation_ids.add(oid)
                vector(observation.get('pose'),3,f'observation {oid} pose')
                finite(observation.get('captured_at'),f'observation {oid} captured_at')
                check(observation.get('edge_id')==config['inspected_edge'],f'Observation {oid} describes wrong inspected edge')
                image = read(folder / f'observation-{oid}.png')
                check(image.startswith(b'\x89PNG\r\n\x1a\n'),f'Observation {oid} lacks valid PNG signature')
                pending = (index,event,hashlib.sha256(image).hexdigest())
            elif event['event']=='assessment_received':
                if pending is None:raise VerificationFailure('Assessment received without a preceding request')
                request_index,requested,image_hash = pending
                metadata = event.get('metadata')
                identity(metadata,'Assessment response metadata','model_revision')
                if not isinstance(metadata,dict):raise VerificationFailure('Assessment metadata is not an object')
                rid = basename(metadata.get('id'))
                check(rid not in request_ids,'Cosmos request ID was reused')
                request_ids.add(rid)
                matches = list(evidence_root.glob(f'cosmos-*/requests/{rid}.json'))
                if len(matches)!=1:raise VerificationFailure(f'Cosmos request {rid}: expected one immutable server record, found {len(matches)}')
                record = load(matches[0])
                identity(record,f'Cosmos request {rid}')
                prompt_identity(snapshot_cosmos, health, record)
                check(record.get('request_id')==rid,f'Server record request ID differs: {rid}')
                check(record.get('status')=='inferred',f'Server record {rid} did not complete inferred')
                check(record.get('image_sha256')==image_hash,f'Observation image hash differs from Cosmos record {rid}')
                answer = parse_answer(record.get('raw_response'))
                check(record.get('assessment')=={'status':answer.status,'reason':answer.reason},
                      f'Server assessment disagrees with parsed raw answer: {rid}')
                check(answer.status==event.get('status') and answer.reason==event.get('reason'),
                      f'Model answer differs from assessment_received: {rid}')
                expected_state = 'INSPECT' if not pairs and answer.status=='blocked' else 'RETURN'
                check(event.get('state')==expected_state,f'Assessment {rid} coordinator state differs from independently expected {expected_state}')
                observation = requested['observation']
                received_wall = event.get('wall_time')
                if received_wall is None:
                    received_wall = finite(record.get('started_at'),f'record {rid} started_at') + finite(record.get('latency_s'),f'record {rid} latency_s')
                finite(received_wall,f'assessment {rid} received wall time')
                age = received_wall-observation['captured_at']
                check(0<=age<=config['decision_max_age_s'],f'Observation {observation["id"]} stale/future at answer receipt: {age:.3f} s')
                pairs.append({'request_index':request_index,'received_index':index,
                              'observation':observation,'record':str(matches[0]),'request_id':rid,
                              'answer_age_s':age,'received_wall':received_wall})
                pending = None
        check(pending is None,'Unanswered assessment request remains')
        metrics['assessment_pairs'] = [{k:v for k,v in p.items() if k not in ('observation','request_index','received_index','received_wall')} for p in pairs]
        expected_answers = 2 if case=='blocked' else 1
        check(len(pairs)==expected_answers,f'{case} requires {expected_answers} paired assessment(s), found {len(pairs)}')
        if len(pairs)==2:
            first, second = [p['observation'] for p in pairs]
            distance = math.dist(first['pose'][:2],second['pose'][:2])
            metrics['view_separation_m'] = distance
            check(distance>=.5,'Blocked confirmation viewpoints are less than 0.5 m apart')
            check(second['captured_at']>=first['captured_at'],'Second observation predates first')
            first_age = pairs[1]['received_wall']-first['captured_at']
            metrics['first_view_age_at_confirmation_s'] = first_age
            check(0<=first_age<=config['decision_max_age_s'],'First view expired before second blocked confirmation')

        releases = [(i,e) for i,e in enumerate(events) if e['event']=='amr_released']
        deliveries = [(i,e) for i,e in enumerate(events) if e['event']=='delivered']
        if len(releases)!=1 or len(deliveries)!=1:raise VerificationFailure('Exactly one AMR release and delivery event required')
        release_index,release = releases[0]
        delivery_index,delivered = deliveries[0]
        check(release_index<delivery_index,'AMR delivery precedes release')
        check(all(p['received_index']<release_index for p in pairs),'AMR released before all assessments completed')
        before = [r for r in rows if r['t']<=release['time_s']]
        after = [r for r in rows if r['t']>=release['time_s']]
        if len(before)<2 or not after:raise VerificationFailure('Insufficient trajectory before/after AMR release')
        park = vector(config['dog_park'],3,'dog_park')
        ready = parking_ready(before,park)
        metrics['parking_ready_recomputed'] = ready
        check(ready,'parking_ready failed at measured AMR release; inspect pre-release dwell/velocity/yaw')
        release_dog = vector(release.get('dog_pose'),4,'release dog_pose')
        check(arrival((release_dog[0],release_dog[1],release_dog[3]),park), 'Release dog pose is outside parking arrival tolerance')
        amr_start = vector(config['amr_start'],3,'amr_start')
        drift = max(math.dist(r['amr'][:2],amr_start[:2]) for r in before)
        metrics['amr_pre_release_drift_m'] = drift
        check(drift<=.03,'AMR moved more than 0.03 m from start before release')
        park_distance = max(math.dist(r['dog'][:2],park[:2]) for r in after)
        metrics['dog_post_release_max_park_distance_m'] = park_distance
        check(park_distance<=.3,'Dog moved more than 0.3 m from parking after release')
        if release.get('wall_time') is None:
            metrics['release_observation_age_s'] = None
            report['limitations'].append('Release observation freshness unavailable: amr_released has no wall_time; measured parking/route gates still recomputed')
        else:
            release_wall = finite(release['wall_time'],'release wall_time')
            ages = [release_wall-p['observation']['captured_at'] for p in pairs]
            metrics['release_observation_age_s'] = ages
            check(all(0<=age<=config['decision_max_age_s'] for age in ages),'Supporting observation stale/future at AMR release')
        closed = result.get('closed_edges')
        if not isinstance(closed,list):raise VerificationFailure('closed_edges must be a list')
        initial = shortest_path(config['nodes'],config['edges'],'start','delivery',set())
        closed_pairs = set()
        for edge in closed:
            if edge not in config['edge_pairs']:raise VerificationFailure(f'Unknown closed edge: {edge}')
            closed_pairs.add(tuple(config['edge_pairs'][edge]))
        route = shortest_path(config['nodes'],config['edges'],'start','delivery',closed_pairs)
        check(result.get('initial_route')==initial,'Initial route differs from independently recomputed shortest path')
        check(result.get('route')==route and release.get('route')==route,'Released route differs from independently recomputed shortest path')
        delivered_pose = vector(delivered.get('amr_pose'),4,'delivered amr_pose')
        error = math.dist(delivered_pose[:2],config['nodes']['delivery'])
        metrics['delivery_error_m_recomputed'] = error
        check(abs(finite(result.get('delivery_error_m'),'result delivery_error_m')-error)<=1e-6,
              'Result delivery error differs from delivered event pose')
        gates = demo_gates(case,events,closed,initial,route,error)
        metrics['demo_gates_recomputed'] = gates
        check(gates['passed'],'Independent demo_gates failed incident/route/delivery acceptance')
        metrics['amr_max_y_m'] = max(r['amr'][1] for r in after)
        metrics['amr_main_aisle_max_y_deviation_m'] = max(abs(r['amr'][1]-amr_start[1]) for r in rows)
        if case=='blocked':
            check(metrics['amr_max_y_m']>=18.8,'Blocked AMR trajectory did not reach detour y >= 18.8 m')
        else:
            check(closed==[],'Control case closed an edge')
            check(metrics['amr_main_aisle_max_y_deviation_m']<=.2,'Control AMR left main aisle by more than 0.2 m')
    except (ValueError,TypeError,KeyError,IndexError,OSError,SyntaxError) as error:
        failures.append(f'{type(error).__name__}: {error}')
    report['status'] = 'failed' if failures else 'passed'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt',required=True,type=basename)
    parser.add_argument('--verification',required=True,type=basename)
    args = parser.parse_args()
    if args.attempt==args.verification:parser.error('verification must use a new directory name')
    out = ROOT / 'evidence' / args.verification
    out.mkdir(parents=True,exist_ok=False)
    identity = {'attempt':args.attempt,'verification':args.verification,'started_at':time.time(),
                'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'helper_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (ROOT / 'src/warehouse_incident/runtime_gates.py',ROOT / 'src/warehouse_incident/core.py',ROOT / 'src/warehouse_incident/cosmos.py')},
                'offline':True,'attempt_mutated':False}
    (out / 'verify_attempt.py').write_bytes(Path(__file__).read_bytes())
    (out / 'identity.json').write_text(json.dumps(identity,indent=2))
    report = verify(args.attempt)
    report['finished_at'] = time.time()
    (out / 'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({'status':report['status'],'verification':str(out),'failed_reasons':report['failed_reasons']}))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
