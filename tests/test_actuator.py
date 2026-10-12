import unittest
from warehouse_incident.actuator import dc_motor_effort
class Motor(unittest.TestCase):
    def test_pd_and_zero_velocity_limit(self):self.assertEqual(dc_motor_effort(2,0,0),23.5)
    def test_speed_reduces_driving_torque_but_allows_braking(self):
        self.assertAlmostEqual(dc_motor_effort(2,0,15),11.75)
        self.assertEqual(dc_motor_effort(-2,0,15),-23.5)
    def test_reverse_symmetry(self):self.assertAlmostEqual(dc_motor_effort(-2,0,-15),-11.75)
    def test_velocity_beyond_stall_region_is_bounded(self):self.assertEqual(dc_motor_effort(20,0,100),-23.5)
