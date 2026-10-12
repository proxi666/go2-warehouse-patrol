import unittest
from warehouse_incident.runtime_gates import baseline_gates, arrival, parking_ready, demo_gates

def rows():
    return [{'t':t,'dog':[x,0,.4,yaw],'up':1.} for t,x,yaw in [(0,0,0),(3,0,0),(7,.8,0),(11,1.5,0),(14,1.5,.8),(18,1.5,1.57),(19,1.5,1.57),(20,1.51,1.57)]]
class Gates(unittest.TestCase):
    def test_standing_alone_cannot_pass_walking(self):
        r=rows()
        for row in r:row['dog'][0]=0
        self.assertFalse(baseline_gates(r)['passed'])
    def test_sideways_drift_is_not_forward(self):
        r=rows()
        for row in r:row['dog'][1]=row['dog'][0];row['dog'][0]=0
        self.assertFalse(baseline_gates(r)['passed'])
    def test_fall_rejects_otherwise_good_motion(self):
        r=rows();r[3]['dog'][2]=.12;r[3]['up']=.3
        self.assertFalse(baseline_gates(r)['passed'])
    def test_valid_motion_turn_stop(self):self.assertTrue(baseline_gates(rows())['passed'])
    def test_stop_yaw_drift_rejects(self):
        r=rows();r[-1]['dog'][3]=1.75
        self.assertFalse(baseline_gates(r)['passed'])
    def test_arrival_requires_heading_for_inspection(self):
        self.assertFalse(arrival((1,2,3.14),(1,2,0)));self.assertTrue(arrival((1,2,.05),(1,2,0)))
    def test_park_requires_dwell_and_low_speed(self):
        r=[{'t':t,'dog':[0,0,.4,0]} for t in [0,.2,.4,.6,.8,1.]]
        self.assertFalse(parking_ready(r[:1],(0,0,0)))
        self.assertTrue(parking_ready(r,(0,0,0)))
        r[-1]['dog'][0]=.1
        self.assertFalse(parking_ready(r,(0,0,0)))
    def test_delivered_false_blockage_cannot_pass_clear_case(self):
        e=[{'event':'assessment_received','status':'blocked'}]*2
        self.assertFalse(demo_gates('clear',e,['main_aisle'],['s','g'],['s','d','g'],.01)['passed'])
    def test_two_blocked_views_and_detour_pass_only_blocked_case(self):
        e=[{'event':'assessment_received','status':'blocked'}]*2
        self.assertTrue(demo_gates('blocked',e,['main_aisle'],['s','g'],['s','d','g'],.01)['passed'])
        self.assertFalse(demo_gates('blocked',e,[],['s','g'],['s','g'],.01)['passed'])

    def test_patrol_position_tolerance_does_not_relax_legacy_parking(self):
        r=[{"t":t,"dog":[.22,0,.4,0]} for t in [0,.2,.4,.6,.8,1.]]
        self.assertFalse(parking_ready(r,(0,0,0)))
        self.assertTrue(parking_ready(r,(0,0,0),tolerance=.25))
