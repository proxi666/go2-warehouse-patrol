"""Synthetic offline evidence exercises the full verifier without simulator or ports."""
import copy
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify_patrol',ROOT/'scripts/verify_patrol.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


def fixture(root, case='blocked', tolerance=.15, offset=0., moving_look=False):
    evidence = root/'evidence'; folder = evidence/'patrol-fixture'; folder.mkdir(parents=True)
    def write(path,obj):
        path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(obj))
    def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
    config = {'aisles':[{'id':f'aisle-{i+1}','mouth':[x,12.8,math.pi/2],'confirm':[x,14,math.pi/2]}
                        for i,x in enumerate((-4,0,4))], 'park':[-6,12.8,0], 'max_age_s':120, 'view_tolerance_m':tolerance,
              'cosmos_model':module.MODEL,'cosmos_revision':module.REVISION}
    if moving_look:
        for aisle in config['aisles']:
            x = aisle['mouth'][0]
            aisle.update(entry=[x-.5,11.8,0.],mouth=[x,12.3,math.pi/2],
                         forward=[x+.5,12.8,0.],confirm=[x,13.5,math.pi/2])
    sources = {}
    for name in ('scripts/run_native.py','src/warehouse_incident/patrol.py','src/warehouse_incident/core.py',
                 'src/warehouse_incident/runtime_gates.py','src/warehouse_incident/cosmos.py','config/patrol.json'):
        path = folder/'source'/name; path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(config) if name.endswith('.json') else "PROMPT = 'legacy fixture prompt'\nPATROL_PROMPT = 'fixture prompt'\nPATROL_SYSTEM = 'fixture system'\n")
        sources[name] = sha(path)
    stage = root/'assets/V44/V44.usda'; stage.parent.mkdir(parents=True); stage.write_text('fixture scene')
    source = root/'assets/source/V39/source.usda'; source.parent.mkdir(parents=True); source.write_text('fixture source')
    health = {'model':module.MODEL,'revision':module.REVISION,'status':'ready',
              'task':'patrol','prompt_name':'PATROL_PROMPT',
              'system_prompt_name':'PATROL_SYSTEM','system_prompt_sha256':hashlib.sha256(b'fixture system').hexdigest(),
              'prompt_sha256':hashlib.sha256(b'fixture prompt').hexdigest(),
              'source_sha256':{name:'a'*64 for name in ('scripts/cosmos_server.py','src/warehouse_incident/cosmos.py','src/warehouse_incident/core.py')}}
    stream = io.BytesIO(); Image.new('RGB',(4,4)).save(stream,format='PNG'); png = stream.getvalue()
    Image.new('RGB',(4,4)).save(folder/'frame-0001.jpg')
    rows, events, aisles = [], [], []; t = 0.
    def event(kind,**kwargs):
        value = {'event':kind,'time_s':t,'wall_time':1000+t,**kwargs}; events.append(value); return value
    def dwell(pose):
        nonlocal t
        for _ in range(16):
            t = round(t+.1,2)
            rows.append({'t':t,'dog':[pose[0]+offset,pose[1],.35,pose[2]],'up':1.,'command':[0,0,0],
                         'phase':'fixture','dof_positions':[[.1]*12],'policy_action':[.1]*12})
    for i, aisle in enumerate(config['aisles']):
        aid = aisle['id']; mouth = aisle['mouth']; confirm = aisle['confirm']
        dwell(aisle.get('entry', [*mouth[:2],0])); event('patrol_phase',phase='LOOK',aisle=aid,pose=rows[-1]['dog'])
        saved = []; obstructed = case == 'blocked' and i == 2
        for view in range(2 if obstructed else 1):
            target = confirm if view else mouth; dwell(target)
            event('patrol_phase',phase='ASSESS',aisle=aid,pose=rows[-1]['dog'])
            oid = f'obs-{i}-{view}'; rid = f'req-{i}-{view}'; filename = f'observation-{oid}.png'
            (folder/filename).write_bytes(png)
            actual_pose = [target[0]+offset,target[1],target[2]]
            obs = {'id':oid,'captured_at':1000+t,'pose':actual_pose,'edge_id':aid}
            event('assessment_requested',aisle=aid,observation=obs)
            status = 'blocked' if obstructed else 'clear'; reason = 'Visible fixture evidence'
            meta = {'id':rid,'model':module.MODEL,'model_revision':module.REVISION,'latency_s':.1}
            phase = 'APPROACH' if obstructed and view == 0 else 'FACE_FORWARD'
            event('assessment_received',aisle=aid,status=status,reason=reason,phase=phase,metadata=meta)['wall_time'] += .2
            record = {**health,'request_id':rid,'status':'inferred','image_sha256':hashlib.sha256(png).hexdigest(),
                      'raw_response':json.dumps({'status':status,'reason':reason}), 'assessment':{'status':status,'reason':reason},
                      'latency_s':.1,'started_at':1000+t}
            write(evidence/'cosmos-fixture/requests'/f'{rid}.json',record)
            saved.append({'id':oid,'captured_at':1000+t,'received_at':1000+t+.2,'pose':actual_pose,'image':filename,
                          'status':status,'reason':reason,'metadata':meta})
        aisles.append({'id':aid,'status':'obstructed' if obstructed else 'clear','evidence':saved,
                       'mouth':mouth,'confirm':confirm,'entry':aisle.get('entry', [*mouth[:2],0]),
                       'forward':aisle.get('forward', [*mouth[:2],0]),'reason':reason,'latencies':[.1]*len(saved)})
        dwell(aisle.get('forward', [*mouth[:2],0])); event('patrol_phase',phase='MOVE' if i<2 else 'RETURN',
                                    aisle=config['aisles'][i+1]['id'] if i<2 else None,pose=rows[-1]['dog'])
    dwell(config['park']); event('patrol_phase',phase='COMPLETE',aisle=None,pose=rows[-1]['dog'])
    statuses = {a['id']:a['status'] for a in aisles}; event('patrol_complete',aisles=statuses)
    result = {'mode':'patrol','status':'passed','native_robot_motion':True,'cosmos_inference':True,'cleanup_errors':[],
              'case':case,'sim_seconds':t,'source_sha256':sources,'runtime_arguments':{'stage':str(stage)},'stage_sha256':sha(stage),
              'scene_files_sha256':{'V44/V44.usda':sha(stage)},'warehouse_source_sha256':{'source.usda':sha(source)},
              'cosmos_health':health,'evaluation':{'observed':statuses,'expected':statuses,'passed':True}}
    state = {'attempt':folder.name,'phase':'COMPLETE','complete':True,'native_status':'passed','aisles':aisles,
             'alerts':['Object detected in aisle 3. Kindly clear it.'] if case=='blocked' else [],'pose':[config['park'][0]+offset,*config['park'][1:]],'park':config['park'],'max_age_s':120, 'view_tolerance_m':tolerance,'updated_at':1001+t,'sim_seconds':t}
    for name,value in [('result.json',result),('identity.json',{'source_sha256':sources}),('trajectory.json',rows),
                       ('contacts.json',[]),('patrol-state.json',state)]:write(folder/name,value)
    (folder/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
    return folder


class VerifyPatrolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.folder = fixture(self.root)

    def verify(self): return module.verify_patrol(self.folder.name,self.root/'evidence')

    def alter(self,name,change):
        path = self.folder/name; obj = json.loads(path.read_text()); change(obj); path.write_text(json.dumps(obj))

    def test_valid_blocked_and_clear_evidence(self):
        self.assertEqual(self.verify()['status'],'passed',self.verify()['failed_reasons'])
        with tempfile.TemporaryDirectory() as d:
            folder = fixture(Path(d),'clear')
            self.assertEqual(module.verify_patrol(folder.name,Path(d)/'evidence')['status'],'passed')

    def test_missing_result_fails_without_wait(self):
        (self.folder/'result.json').unlink(); self.assertEqual(self.verify()['status'],'failed')

    def test_changed_prompt_request_rejected(self):
        path = next((self.root/'evidence/cosmos-fixture/requests').glob('*.json'))
        record = json.loads(path.read_text()); record['prompt_sha256'] = '0'*64; path.write_text(json.dumps(record))
        self.assertIn('Request prompt',str(self.verify()['failed_reasons']))

    def test_fake_dashboard_clear_rejected(self):
        self.alter('patrol-state.json',lambda s:s['aisles'][2].update(status='clear'))
        self.assertIn('Dashboard classification',str(self.verify()['failed_reasons']))

    def test_missing_alert_rejected(self):
        self.alter('patrol-state.json',lambda s:s.update(alerts=[]))
        self.assertIn('Operator alert',str(self.verify()['failed_reasons']))

    def test_unsettled_inspection_rejected(self):
        def change(rows):
            for row in rows:
                if 2.1<=row['t']<=2.4: row['dog'][3] = 0
        self.alter('trajectory.json',change)
        self.assertIn('settled dwell',str(self.verify()['failed_reasons']))

    def test_corrupt_source_rejected(self):
        (self.folder/'source/src/warehouse_incident/patrol.py').write_text('changed')
        self.assertIn('File identity',str(self.verify()['failed_reasons']))

    def test_cleanup_failure_rejected(self):
        self.alter('result.json',lambda s:s.update(cleanup_errors=['rgb failed']))
        self.assertIn('cleanup',str(self.verify()['failed_reasons']))

    def test_contact_rejected(self):
        self.alter('contacts.json',lambda s:s.append({'actors':['rack','dog']}))
        self.assertIn('contact',str(self.verify()['failed_reasons']))

    def test_stale_observation_rejected(self):
        path = self.folder/'events.jsonl'
        events = [json.loads(line) for line in path.read_text().splitlines()]
        next(e for e in events if e['event']=='assessment_requested')['observation']['captured_at'] -= 121
        path.write_text(''.join(json.dumps(e)+'\n' for e in events))
        self.assertIn('Stale/future',str(self.verify()['failed_reasons']))

    def test_forward_heading_not_just_named_phase(self):
        path = self.folder/'events.jsonl'
        events = [json.loads(line) for line in path.read_text().splitlines()]
        next(e for e in events if e['event']=='patrol_phase' and e['phase']=='MOVE')['pose'][3] = 1.5
        path.write_text(''.join(json.dumps(e)+'\n' for e in events))
        self.assertIn('Phase event pose',str(self.verify()['failed_reasons']))

    def test_sparse_dwell_not_accepted(self):
        self.alter('trajectory.json',lambda rows: rows.__delitem__(slice(5,10)))
        self.assertIn('sparse trajectory',str(self.verify()['failed_reasons']))

    def test_incident_task_cannot_qualify_patrol(self):
        self.alter('result.json',lambda result:result['cosmos_health'].update(task='incident',prompt_name='PROMPT'))
        self.assertIn('Patrol requires task=patrol',str(self.verify()['failed_reasons']))

    def test_missing_task_cannot_qualify_patrol(self):
        self.alter('result.json',lambda result:result['cosmos_health'].pop('task'))
        self.assertIn('Patrol requires task=patrol',str(self.verify()['failed_reasons']))

    def test_position_offset_requires_declared_tolerance(self):
        for tolerance, expected in ((.15,'failed'),(.25,'passed')):
            with self.subTest(tolerance=tolerance), tempfile.TemporaryDirectory() as d:
                folder = fixture(Path(d), tolerance=tolerance, offset=.22)
                report = module.verify_patrol(folder.name,Path(d)/'evidence')
                self.assertEqual(report['status'],expected,report['failed_reasons'])

    def test_tolerance_above_safety_bound_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            folder = fixture(Path(d), tolerance=.31)
            report = module.verify_patrol(folder.name,Path(d)/'evidence')
            self.assertIn('at most 0.3',str(report['failed_reasons']))

    def test_dashboard_tolerance_must_match_config(self):
        self.alter('patrol-state.json',lambda state:state.update(view_tolerance_m=.25))
        self.assertIn('Dashboard view tolerance',str(self.verify()['failed_reasons']))

    def test_moving_look_entry_and_forward_targets(self):
        with tempfile.TemporaryDirectory() as d:
            folder = fixture(Path(d),tolerance=.25,moving_look=True)
            report = module.verify_patrol(folder.name,Path(d)/'evidence')
            self.assertEqual(report['status'],'passed',report['failed_reasons'])
            events = [json.loads(line) for line in (folder/'events.jsonl').read_text().splitlines()]
            first_move = next(e for e in events if e['event']=='patrol_phase' and e['phase']=='MOVE')
            first_move['pose'] = [-4.,12.3,.35,0.]
            (folder/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
            report = module.verify_patrol(folder.name,Path(d)/'evidence')
            self.assertIn('Phase event pose',str(report['failed_reasons']))

    def test_dashboard_forward_target_must_match_moving_config(self):
        with tempfile.TemporaryDirectory() as d:
            folder = fixture(Path(d),moving_look=True)
            path = folder/'patrol-state.json'; state = json.loads(path.read_text())
            state['aisles'][0]['forward'] = [-4,12.3,0.]
            path.write_text(json.dumps(state))
            report = module.verify_patrol(folder.name,Path(d)/'evidence')
            self.assertIn('Dashboard forward',str(report['failed_reasons']))

    def test_arrival_interpolates_at_event_time_without_relaxing_tolerance(self):
        with tempfile.TemporaryDirectory() as d:
            folder = fixture(Path(d),tolerance=.25)
            path = folder/'trajectory.json'; rows = json.loads(path.read_text())
            for row in rows:
                if row['t'] == 1.5: row['dog'][0] = -4.+.254
                if row['t'] == 1.6: row['dog'][0] = -4.+.234
            path.write_text(json.dumps(rows))
            path = folder/'events.jsonl'; events = [json.loads(line) for line in path.read_text().splitlines()]
            event = events[0]; event['time_s'] = 1.53; event['wall_time'] = 1001.53
            event['pose'][0] = -4.+.248
            path.write_text(''.join(json.dumps(e)+'\n' for e in events))
            report = module.verify_patrol(folder.name,Path(d)/'evidence')
            self.assertEqual(report['status'],'passed',report['failed_reasons'])
            event['time_s'] = 1.51; event['wall_time'] = 1001.51
            event['pose'][0] = -4.+.249  # Native sample differs 3 mm from linear estimate.
            path.write_text(''.join(json.dumps(e)+'\n' for e in events))
            report = module.verify_patrol(folder.name,Path(d)/'evidence')
            self.assertEqual(report['status'],'passed',report['failed_reasons'])
            event['pose'][0] = -4.+.252
            path.write_text(''.join(json.dumps(e)+'\n' for e in events))
            report = module.verify_patrol(folder.name,Path(d)/'evidence')
            self.assertIn('Phase event pose differs',str(report['failed_reasons']))

    def test_forged_inside_target_pose_rejected_by_trajectory(self):
        path = self.folder/'events.jsonl'; events = [json.loads(line) for line in path.read_text().splitlines()]
        events[0]['pose'][0] += .1  # Both points remain inside the arrival region.
        path.write_text(''.join(json.dumps(e)+'\n' for e in events))
        report = self.verify()
        self.assertIn('disagrees with time-aligned trajectory',str(report['failed_reasons']))
