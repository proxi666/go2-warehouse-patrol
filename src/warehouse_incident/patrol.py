"""Serial physical aisle inspection policy; contains no robot/model I/O."""
import copy
import json
import math
from pathlib import Path
from .core import Assessment, Observation, _identifier, _number, _vector
from .runtime_gates import arrival


def settling_arrival(pose, target, tolerance, settling):
    """Enter a tighter stop region; retain the original acceptance on drift.

    This prevents stop/move cycling at the outer arrival boundary. The measured
    dwell, speed and final observation gates still use their original limits.
    """
    return arrival(pose, target, tolerance=tolerance if settling else .8*tolerance)


class Patrol:
    """The runner owns localization, physical settling, inference, and time.

    settled must be a measured consecutive dwell, never a timer alone. Snapshot
    evidence is immutable-by-copy and suitable for atomic patrol-state.json writes.
    """
    def __init__(self, config):
        if not isinstance(config, dict) or not isinstance(config.get('aisles'), list) or not config['aisles']:
            raise ValueError('Patrol config requires a nonempty aisles list')
        self.max_age = _number(config.get('max_age_s', 120.), 'max_age_s')
        if self.max_age <= 0: raise ValueError('max_age_s must be positive')
        self.view_tolerance = _number(config.get('view_tolerance_m', .15), 'view_tolerance_m')
        if not 0 < self.view_tolerance <= .3:
            raise ValueError('view_tolerance_m must be positive and at most 0.3 m')
        self.park = _vector(config.get('park'), (3,), 'park')
        self.aisles = []
        seen = set()
        for item in config['aisles']:
            if not isinstance(item, dict): raise ValueError('Aisle requires an object')
            _identifier(item.get('id'), 'aisle id'); _identifier(item.get('label'), 'aisle label')
            if item['id'] in seen: raise ValueError('Aisle IDs must be unique')
            seen.add(item['id'])
            mouth = _vector(item.get('mouth'), (3,), 'mouth')
            confirm = _vector(item.get('confirm'), (3,), 'confirm')
            entry = _vector(item.get('entry', (*mouth[:2], 0.)), (3,), 'entry')
            forward = _vector(item.get('forward', (*mouth[:2], 0.)), (3,), 'forward')
            if math.dist(mouth[:2], confirm[:2]) < .5: raise ValueError('Confirmation must be at least 0.5 m from mouth')
            self.aisles.append({'id':item['id'], 'label':item['label'], 'mouth':mouth,
                                'confirm':confirm, 'entry':entry, 'forward':forward, 'status':'uninspected', 'reason':'Not inspected',
                                'evidence':[], 'latencies':[]})
        self.phase = 'MOVE'; self.index = 0; self.reason = 'Moving to first inspection mouth'
        self.pose = None; self.updated_at = None; self.alerts = []; self._seen = set()

    @property
    def complete(self): return self.phase == 'COMPLETE'

    @property
    def aisle_id(self):
        return self.aisles[self.index]['id'] if self.index < len(self.aisles) else None

    @property
    def target(self):
        if self.phase in ('ASSESS','HOLD','COMPLETE'): return None
        if self.phase == 'RETURN': return self.park
        aisle = self.aisles[self.index]
        if self.phase == 'APPROACH': return aisle['confirm']
        if self.phase == 'LOOK': return aisle['mouth']
        if self.phase == 'MOVE': return aisle['entry']
        return aisle['forward']

    def _hold(self, reason):
        self.phase = 'HOLD'; self.reason = reason
        if self.index < len(self.aisles):
            self.aisles[self.index].update(status='uncertain', reason=reason)
        return self.phase

    def advance(self, pose, now, settled=False):
        try:
            self.pose = _vector(pose, (3,), 'pose')
            self.updated_at = _number(now, 'now')
            if not isinstance(settled, bool): raise ValueError('settled must be a measured boolean')
        except ValueError:
            self._hold('Malformed localization or wall time'); raise
        if self.phase in ('HOLD','COMPLETE','ASSESS'): return self.phase
        if not arrival(self.pose, self.target, tolerance=self.view_tolerance): return self.phase
        if self.phase == 'MOVE': self.phase = 'LOOK'
        elif not settled: return self.phase
        elif self.phase in ('LOOK','APPROACH'): self.phase = 'ASSESS'
        elif self.phase == 'FACE_FORWARD':
            self.index += 1
            self.phase = 'MOVE' if self.index < len(self.aisles) else 'RETURN'
        elif self.phase == 'RETURN': self.phase = 'COMPLETE'
        self.reason = {'LOOK':'Turning to inspect aisle', 'ASSESS':'Waiting for real camera assessment',
                       'MOVE':'Moving to next inspection mouth', 'RETURN':'Returning to parking',
                       'COMPLETE':'Patrol completed; recorded findings retained'}.get(self.phase, self.reason)
        return self.phase

    def record_observation(self, obs, assessment, now, image_filename, metadata):
        try:
            self.updated_at = _number(now, 'now')
            if not isinstance(obs, Observation) or not isinstance(assessment, Assessment):
                raise ValueError('Observation and Assessment required; model failure must hold')
            if not isinstance(image_filename, str) or Path(image_filename).name != image_filename or Path(image_filename).suffix.lower() not in ('.png','.jpg','.jpeg'):
                raise ValueError('Evidence image must be one safe image filename')
            if not isinstance(metadata, dict): raise ValueError('metadata requires an object')
            json.dumps(metadata, allow_nan=False)
            latency = metadata.get('latency_s')
            if latency is not None and _number(latency, 'latency_s') < 0: raise ValueError('latency must be nonnegative')
        except (ValueError, TypeError):
            self._hold('Malformed observation, failed inference, or evidence metadata'); raise ValueError(self.reason) from None
        if self.phase == 'HOLD': return self.phase
        if self.phase != 'ASSESS': return self._hold('Observation arrived outside assessment phase')
        aisle = self.aisles[self.index]
        record = {'id':obs.id,'captured_at':obs.captured_at,'received_at':now,'pose':obs.pose,
                  'image':image_filename,'status':assessment.status,'reason':assessment.reason,
                  'metadata':copy.deepcopy(metadata)}
        prior = list(aisle['evidence']); aisle['evidence'].append(record)
        if latency is not None: aisle['latencies'].append(float(latency))
        if obs.id in self._seen: return self._hold('Observation ID reused')
        self._seen.add(obs.id)
        if obs.edge_id != aisle['id']: return self._hold('Observation describes a different aisle')
        if not 0 <= now - obs.captured_at <= self.max_age: return self._hold('Observation stale or future-dated')
        if assessment.status == 'uncertain': return self._hold(assessment.reason)
        if not prior:
            if assessment.status == 'clear':
                aisle.update(status='clear',reason=assessment.reason); self.phase = 'FACE_FORWARD'
            else:
                aisle.update(status='inspecting',reason=assessment.reason); self.phase = 'APPROACH'
        else:
            first = prior[0]
            if not 0 <= now-first['captured_at'] <= self.max_age: return self._hold('First observation expired before confirmation')
            if obs.captured_at < first['captured_at']: return self._hold('Second observation predates first')
            if assessment.status != 'blocked' or first['status'] != 'blocked': return self._hold('Contradictory second observation')
            if math.dist(obs.pose[:2], first['pose'][:2]) < .5: return self._hold('Confirmation views too close')
            aisle.update(status='obstructed',reason=assessment.reason); self.phase = 'FACE_FORWARD'
            self.alerts.append(f'Object detected in aisle {self.index+1}. Kindly clear it.')
        self.reason = aisle['reason']
        return self.phase

    def snapshot(self):
        return copy.deepcopy({'phase':self.phase,'active_aisle':self.aisle_id,
                              'complete':self.complete,'updated_at':self.updated_at,'pose':self.pose,
                              'reason':self.reason,'max_age_s':self.max_age,'view_tolerance_m':self.view_tolerance,'alerts':self.alerts,
                              'aisles':self.aisles,'park':self.park})
