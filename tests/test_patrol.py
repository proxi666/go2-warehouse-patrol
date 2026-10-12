import importlib.util
import json
import math
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error

from warehouse_incident.core import Assessment, Observation
try:
    from warehouse_incident.patrol import Patrol
except ImportError:
    Patrol = None

CONFIG = {'aisles': [{'id': f'aisle-{i+1}', 'label': f'Aisle {i+1}',
                      'mouth': [x, 12.8, math.pi/2], 'confirm': [x, 14., math.pi/2]}
                     for i, x in enumerate([-4., 0., 4.])],
          'park': [-6., 12.8, 0.], 'max_age_s': 120.}


class PatrolTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(Patrol, 'Patrol coordinator missing')
        self.p = Patrol(CONFIG)

    def look(self):
        self.assertEqual(self.p.advance(self.p.target, 100.), 'LOOK')
        self.assertEqual(self.p.advance(self.p.target, 100., settled=False), 'LOOK')
        self.assertEqual(self.p.advance(self.p.target, 100., settled=True), 'ASSESS')

    def record(self, status, identifier='first', pose=None, captured=99., edge=None, now=100.):
        obs = Observation(identifier, captured, pose or tuple(CONFIG['aisles'][0]['mouth']), edge or self.p.aisle_id)
        return self.p.record_observation(obs, Assessment(status, 'actual answer'), now, identifier+'.png', {'latency_s': .4})

    def test_view_tolerance_is_explicit_and_default_remains_strict(self):
        offset=(-4.22,12.8,0.)
        self.assertEqual(self.p.advance(offset,100.),'MOVE')
        config={**CONFIG,'view_tolerance_m':.25}
        self.p=Patrol(config)
        self.assertEqual(self.p.advance(offset,100.),'LOOK')
        look=(-4.22,12.8,math.pi/2)
        self.assertEqual(self.p.advance(look,100.,settled=True),'ASSESS')
        self.assertEqual(self.p.snapshot()['view_tolerance_m'],.25)

    def test_view_tolerance_invalid_values_fail(self):
        for value in (0.,-.1,.301,float('nan'),float('inf'),True):
            with self.subTest(value=value),self.assertRaises(ValueError):
                Patrol({**CONFIG,'view_tolerance_m':value})

    def test_wider_view_tolerance_does_not_relax_confirmation_distance(self):
        self.p=Patrol({**CONFIG,'view_tolerance_m':.25})
        self.look();self.record('blocked')
        self.p.advance(self.p.target,101.,settled=True)
        self.assertEqual(self.record('blocked','second',(-4.,13.29,math.pi/2),101.,now=102.),'HOLD')
        self.assertEqual(self.p.snapshot()['aisles'][0]['status'],'uncertain')

    def test_translating_entry_look_and_forward_targets(self):
        config={**CONFIG,'aisles':[{**CONFIG['aisles'][0],
                                  'entry':[-4.5,11.8,0.],
                                  'mouth':[-4.,12.3,math.pi/2],
                                  'forward':[-3.5,12.8,0.]}]}
        self.p=Patrol(config)
        self.assertEqual(self.p.target,(-4.5,11.8,0.))
        self.assertEqual(self.p.advance((-4.,12.3,0.),100.),'MOVE')
        self.assertEqual(self.p.advance(self.p.target,100.),'LOOK')
        self.assertEqual(self.p.target,(-4.,12.3,math.pi/2))
        self.p.advance(self.p.target,100.,settled=True)
        self.record('clear',pose=(-4.,12.3,math.pi/2))
        self.assertEqual(self.p.target,(-3.5,12.8,0.))
        self.assertEqual(self.p.advance((-4.,12.3,0.),100.,settled=True),'FACE_FORWARD')
        self.assertEqual(self.p.advance(self.p.target,100.,settled=True),'RETURN')
        row=self.p.snapshot()['aisles'][0]
        self.assertEqual(row['entry'],(-4.5,11.8,0.))
        self.assertEqual(row['forward'],(-3.5,12.8,0.))

    def test_entry_forward_pose_validation_and_default_compatibility(self):
        for key in ('entry','forward'):
            for value in ([0.,0.],[0.,float('nan'),0.],'bad'):
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                    Patrol({**CONFIG,'aisles':[{**CONFIG['aisles'][0],key:value}]})
        row=self.p.snapshot()['aisles'][0]
        self.assertEqual(row['entry'],(-4.,12.8,0.))
        self.assertEqual(row['forward'],(-4.,12.8,0.))

    def test_initial_uninspected_and_heading_sequence(self):
        self.assertEqual(self.p.target, (-4., 12.8, 0.))
        self.assertEqual([a['status'] for a in self.p.snapshot()['aisles']], ['uninspected']*3)
        self.look()
        self.assertIsNone(self.p.target)

    def test_clear_advances_only_after_settled_forward(self):
        self.look()
        self.assertEqual(self.record('clear'), 'FACE_FORWARD')
        self.assertEqual(self.p.snapshot()['aisles'][0]['status'], 'clear')
        self.assertEqual(self.p.target, (-4., 12.8, 0.))
        self.assertEqual(self.p.advance(self.p.target, 101., settled=False), 'FACE_FORWARD')
        self.assertEqual(self.p.advance(self.p.target, 101., settled=True), 'MOVE')
        self.assertEqual(self.p.aisle_id, 'aisle-2')

    def test_blocked_two_physical_views_confirm_alert(self):
        self.look()
        self.assertEqual(self.record('blocked'), 'APPROACH')
        self.assertEqual(self.p.snapshot()['aisles'][0]['status'], 'inspecting')
        self.assertEqual(self.p.advance(self.p.target, 101., settled=True), 'ASSESS')
        self.assertEqual(self.record('blocked', 'second', tuple(CONFIG['aisles'][0]['confirm']), 101., now=102.), 'FACE_FORWARD')
        row = self.p.snapshot()['aisles'][0]
        self.assertEqual(row['status'], 'obstructed')
        self.assertEqual(row['latencies'], [.4, .4])
        self.assertEqual(len(row['evidence']), 2)
        self.assertIn('Object detected in aisle 1. Kindly clear it.', self.p.snapshot()['alerts'])

    def test_invalid_second_views_hold_never_clear(self):
        for status, identifier, pose, captured, edge in [
                ('clear', 'second', (-4., 14., math.pi/2), 101., 'aisle-1'),
                ('blocked', 'first', (-4., 14., math.pi/2), 101., 'aisle-1'),
                ('blocked', 'second', (-4., 12.9, math.pi/2), 101., 'aisle-1'),
                ('blocked', 'second', (-4., 14., math.pi/2), -30., 'aisle-1'),
                ('blocked', 'second', (-4., 14., math.pi/2), 103., 'aisle-1'),
                ('blocked', 'second', (-4., 14., math.pi/2), 101., 'aisle-2')]:
            with self.subTest(status=status, id=identifier):
                self.p = Patrol(CONFIG); self.look(); self.record('blocked')
                self.p.advance(self.p.target, 101., settled=True)
                self.assertEqual(self.record(status, identifier, pose, captured, edge, 102.), 'HOLD')
                self.assertEqual(self.p.snapshot()['aisles'][0]['status'], 'uncertain')
                self.assertIsNone(self.p.target)

    def test_third_aisle_alert_and_snapshot_cannot_mutate_policy(self):
        for index in range(2):
            self.look(); self.record('clear', f'clear-{index}', tuple(CONFIG['aisles'][index]['mouth']))
            self.p.advance(self.p.target, 101., settled=True)
        self.look();self.record('blocked','third-first',tuple(CONFIG['aisles'][2]['mouth']))
        self.p.advance(self.p.target,101.,settled=True)
        self.record('blocked','third-second',tuple(CONFIG['aisles'][2]['confirm']),101.,now=102.)
        self.assertEqual(self.p.snapshot()['alerts'],['Object detected in aisle 3. Kindly clear it.'])
        snap=self.p.snapshot();snap['aisles'][2]['status']='clear';snap['alerts'].clear()
        self.assertEqual(self.p.snapshot()['aisles'][2]['status'],'obstructed')
        self.assertEqual(len(self.p.snapshot()['alerts']),1)

    def test_expired_first_and_malformed_model_failure_hold(self):
        self.look();self.record('blocked',captured=0.,now=1.)
        self.p.advance(self.p.target,100.,settled=True)
        self.assertEqual(self.record('blocked','second',tuple(CONFIG['aisles'][0]['confirm']),121.,now=121.),'HOLD')
        self.p=Patrol(CONFIG);self.look()
        with self.assertRaises(ValueError):
            self.p.record_observation(None,None,100.,'frame.png',{})
        self.assertEqual(self.p.phase,'HOLD')
        self.assertEqual(self.p.snapshot()['aisles'][0]['status'],'uncertain')

    def test_uncertain_first_holds_and_schema_fails_loud(self):
        self.look()
        self.assertEqual(self.record('uncertain'), 'HOLD')
        self.assertFalse(self.p.complete)
        with self.assertRaises(ValueError):
            self.p.advance((0., 0., float('nan')), 100.)
        with self.assertRaises(ValueError):
            Patrol({'aisles': [], 'park': [0,0,0]})

    def test_all_clear_returns_and_requires_settled_parking(self):
        for index in range(3):
            self.look(); self.record('clear', f'view-{index}', tuple(CONFIG['aisles'][index]['mouth']))
            self.p.advance(self.p.target, 101., settled=True)
        self.assertEqual(self.p.phase, 'RETURN')
        self.assertIsNone(self.p.aisle_id)
        self.assertEqual(self.p.advance(self.p.target, 102.), 'RETURN')
        self.assertEqual(self.p.advance(self.p.target, 102., settled=True), 'COMPLETE')
        self.assertTrue(self.p.complete)
        self.assertIsNone(self.p.target)
        json.dumps(self.p.snapshot(), allow_nan=False)


class DashboardTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1]/'scripts/dashboard_server.py'
        self.assertTrue(source.exists(), 'Read-only dashboard server missing')
        spec=importlib.util.spec_from_file_location('dashboard_server',source)
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'evidence/run-01').mkdir(parents=True)
        self.attempt=self.module.resolve_attempt('run-01',self.root)
        self.server=self.module.make_server(self.attempt,port=0)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.base=f'http://127.0.0.1:{self.server.server_port}'

    def test_missing_state_explicit_pending_then_actual_snapshot(self):
        data=json.load(urllib.request.urlopen(self.base+'/api/state'))
        self.assertEqual(data['phase'],'PENDING')
        self.assertNotIn('clear', json.dumps(data))
        (self.attempt/'patrol-state.json').write_text(json.dumps({'phase':'HOLD','reason':'Inference failed'}))
        self.assertEqual(json.load(urllib.request.urlopen(self.base+'/api/state'))['phase'],'HOLD')

    def test_attempt_and_media_paths_cannot_escape(self):
        for name in ('../other','a/b','', '.', '..'):
            with self.assertRaises(ValueError):self.module.resolve_attempt(name,self.root)
        (self.attempt/'frame.png').write_bytes(b'actual pixels')
        self.assertEqual(urllib.request.urlopen(self.base+'/media/frame.png').read(),b'actual pixels')
        (self.attempt/'leak.png').symlink_to(self.root/'secret.png')
        (self.root/'secret.png').write_bytes(b'secret')
        for path in ('/media/%2e%2e%2fsecret.png','/media/leak.png','/media/patrol-state.json'):
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(self.base+path)

    def test_homepage_is_inspection_and_read_only(self):
        html=urllib.request.urlopen(self.base+'/').read().decode()
        self.assertIn('<h1>Warehouse inspection</h1>',html)
        self.assertIn('setInterval(poll,1000)',html)
        self.assertNotIn('AMR',html)

    def test_bad_state_reports_error_and_post_is_disallowed(self):
        (self.attempt/'patrol-state.json').write_text('{bad')
        data=json.load(urllib.request.urlopen(self.base+'/api/state'))
        self.assertEqual(data['phase'],'ERROR')
        req=urllib.request.Request(self.base+'/api/state',data=b'{}',method='POST')
        with self.assertRaises(urllib.error.HTTPError) as ctx:urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code,501)


class ArrivalHysteresisTests(unittest.TestCase):
    def test_enter_inside_acceptance_then_hold_through_small_drift(self):
        from warehouse_incident.patrol import settling_arrival
        target=(-3.5,12.8,0.)
        # Recorded server edge pose must keep moving before a settling latch.
        edge=(-3.651724,12.605147,.054638)
        self.assertFalse(settling_arrival(edge,target,.25,False))
        self.assertTrue(settling_arrival((-3.6,12.7,.04),target,.25,False))
        self.assertTrue(settling_arrival(edge,target,.25,True))
        self.assertFalse(settling_arrival((-3.7,12.6,.04),target,.25,True))
        self.assertFalse(settling_arrival((-3.6,12.7,.2),target,.25,True))

if __name__=='__main__':unittest.main()
