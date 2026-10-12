import dataclasses
import math
import unittest
import warehouse_incident.core as core

try:
    from warehouse_incident.core import (Observation, Assessment, Coordinator, shortest_path,
                                         dog_command, wheel_command)
except ImportError:
    Observation = Assessment = Coordinator = shortest_path = dog_command = wheel_command = None


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(Coordinator, 'CPU core API not implemented')

    def obs(self, id='a', x=0., edge='A-B', captured=99.):
        return Observation(id, captured, (x, 0., 0.), edge)

    def test_observation_immutable(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            self.obs().id = 'changed'

    def test_two_view_confirmation_requires_parking(self):
        c = Coordinator()
        self.assertEqual(c.observe(self.obs(), Assessment('blocked', 'box'), 100.), 'INSPECT')
        self.assertEqual(c.observe(self.obs('b', .5), Assessment('blocked', 'box'), 100.), 'RETURN')
        self.assertEqual(c.closed_edges, {'A-B'})
        self.assertFalse(c.route_releasable)
        self.assertEqual(c.parked(100.), 'READY')
        self.assertTrue(c.route_releasable)

    def test_parking_revalidates_first_and_second_view_age(self):
        c = Coordinator()
        c.observe(self.obs(captured=10.), Assessment('blocked', 'box'), 11.)
        c.observe(self.obs('b', .6, captured=100.), Assessment('blocked', 'box'), 101.)
        self.assertEqual(c.parked(131.), 'HOLD')
        self.assertFalse(c.route_releasable)

    def test_clear_return_expiry_blocks_release(self):
        c = Coordinator()
        c.observe(self.obs(captured=10.), Assessment('clear', 'open'), 11.)
        self.assertEqual(c.parked(131.), 'HOLD')
        self.assertFalse(c.route_releasable)

    def test_parking_future_view_blocks_release(self):
        c = Coordinator()
        c.observe(self.obs(captured=10.), Assessment('blocked', 'box'), 11.)
        c.observe(self.obs('b', .6, captured=100.), Assessment('blocked', 'box'), 101.)
        self.assertEqual(c.parked(99.), 'HOLD')
        self.assertFalse(c.route_releasable)

    def test_clear_fresh_release_at_max_age_boundary(self):
        c = Coordinator()
        c.observe(self.obs(captured=10.), Assessment('clear', 'open'), 11.)
        self.assertEqual(c.parked(130.), 'READY')
        self.assertTrue(c.route_releasable)

    def test_parking_malformed_time_latches_hold(self):
        for now in (float('nan'), float('inf'), 'bad', None):
            with self.subTest(now=now):
                c = Coordinator()
                c.observe(self.obs(), Assessment('clear', 'open'), 100.)
                with self.assertRaises(ValueError):
                    c.parked(now)
                self.assertEqual(c.state, 'HOLD')
                self.assertFalse(c.route_releasable)

    def test_clear_first_returns_without_closure(self):
        c = Coordinator()
        self.assertEqual(c.observe(self.obs(), Assessment('clear', 'open'), 100.), 'RETURN')
        self.assertEqual(c.closed_edges, set())

    def test_rejected_second_views_hold(self):
        for obs, status in [(self.obs('b', .6, 'C-D'), 'blocked'),
                            (self.obs('b', .49), 'blocked'),
                            (self.obs('a', .6), 'blocked'),
                            (self.obs('b', .6), 'uncertain'),
                            (self.obs('b', .6), 'clear'),
                            (self.obs('b', .6, captured=-30), 'blocked'),
                            (self.obs('b', .6, captured=101), 'blocked')]:
            with self.subTest(obs=obs, status=status):
                c = Coordinator()
                c.observe(self.obs(), Assessment('blocked', 'box'), 100.)
                self.assertEqual(c.observe(obs, Assessment(status, 'view'), 100.), 'HOLD')
                self.assertEqual(c.closed_edges, set())
                self.assertEqual(c.parked(100.), 'HOLD')

    def test_invalid_first_holds(self):
        for obs, status in [(self.obs(captured=-30), 'blocked'),
                            (self.obs(captured=101), 'clear'), (self.obs(), 'uncertain')]:
            c = Coordinator()
            self.assertEqual(c.observe(obs, Assessment(status, 'reason'), 100.), 'HOLD')

    def test_parking_cannot_bypass_inspection(self):
        c = Coordinator()
        self.assertEqual(c.parked(100.), 'PATROL')
        c.observe(self.obs(), Assessment('blocked', 'box'), 100.)
        self.assertEqual(c.parked(100.), 'INSPECT')
        self.assertFalse(c.route_releasable)

    def test_first_view_expiry_and_out_of_order_second_hold(self):
        c = Coordinator()
        c.observe(self.obs(captured=0.), Assessment('blocked', 'box'), 1.)
        self.assertEqual(c.observe(self.obs('b', .6, captured=121.),
                                   Assessment('blocked', 'box'), 121.), 'HOLD')
        c = Coordinator()
        c.observe(self.obs(captured=99.), Assessment('blocked', 'box'), 100.)
        self.assertEqual(c.observe(self.obs('b', .6, captured=98.),
                                   Assessment('blocked', 'box'), 100.), 'HOLD')

    def test_malformed_api_latches_hold(self):
        c = Coordinator()
        with self.assertRaises(ValueError):
            c.observe({}, Assessment('clear', 'open'), 100.)
        self.assertEqual(c.state, 'HOLD')
        self.assertFalse(c.route_releasable)

    def test_malformed_inputs_fail_loud(self):
        for pose in [(0., 1.), (0., float('nan'), 0.), ('bad', 0., 0.)]:
            with self.assertRaises(ValueError):
                Observation('a', 1., pose, 'A-B')
        for time in [float('nan'), float('inf'), 'bad']:
            with self.assertRaises(ValueError):
                Observation('a', time, (0., 0., 0.), 'A-B')
        with self.assertRaises(ValueError):
            Assessment('invalid', 'reason')
        with self.assertRaises(ValueError):
            Coordinator().observe(self.obs(), Assessment('clear', 'view'), float('nan'))

    def test_graph_detour_and_disconnected(self):
        nodes = {'A': (0, 0), 'B': (1, 0), 'C': (0, 1), 'D': (1, 1)}
        edges = [('A', 'B', 1), ('B', 'D', 1), ('A', 'C', 2), ('C', 'D', 2)]
        self.assertEqual(shortest_path(nodes, edges, 'A', 'D', set()), ['A', 'B', 'D'])
        self.assertEqual(shortest_path(nodes, edges, 'A', 'D', {('B', 'A')}), ['A', 'C', 'D'])
        self.assertIsNone(shortest_path(nodes, edges, 'A', 'D', {('A', 'B'), ('A', 'C')}))
        self.assertEqual(shortest_path(nodes, edges, 'A', 'A', set()), ['A'])
        with self.assertRaises(ValueError):
            shortest_path(nodes, [('A', 'B', -1)], 'A', 'D', set())

    def test_heading_wrap_and_bounded_dog_turn(self):
        vx, vy, wz = dog_command((0., 0., math.pi - .01), (-1., -.01))
        self.assertGreater(vx, 0.)
        self.assertEqual(vy, 0.)
        self.assertGreater(wz, 0.)
        self.assertLess(abs(wz), .1)
        vx, vy, wz = dog_command((0., 0., 0.), (0., 2.))
        self.assertEqual(vx, 0.)
        self.assertEqual(vy, 0.)
        self.assertLessEqual(abs(wz), 1.)
        self.assertEqual(dog_command((0., 0., 0.), (.05, 0.)), (0., 0., 0.))

    def test_wheel_bounds_and_positive_yaw(self):
        left, right = wheel_command((0., 0., 0.), (0., 5.))
        self.assertGreater(right, left)
        self.assertLessEqual(max(abs(left), abs(right)), 3.5)
        left, right = wheel_command((0., 0., 0.), (5., 0.))
        self.assertAlmostEqual(left, right)
        self.assertLessEqual(left, 3.5)
        self.assertEqual(wheel_command((0., 0., 0.), (0., 0.)), (0., 0.))

class QuadrupedCommandTests(unittest.TestCase):
    def setUp(self):
        self.command = getattr(core, 'quadruped_command', None)
        self.assertIsNotNone(self.command, 'Body-frame quadruped waypoint controller missing')

    def test_world_x_target_at_yaw_90_commands_negative_body_y(self):
        vx, vy, wz = self.command((0., 0., math.pi / 2), (2., 0.))
        self.assertAlmostEqual(vx, 0.)
        self.assertAlmostEqual(vy, -.3)
        self.assertEqual(wz, 0.)

    def test_backward_target_commands_negative_forward_velocity(self):
        vx, vy, wz = self.command((0., 0., 0.), (-2., 0.))
        self.assertAlmostEqual(vx, -.3)
        self.assertEqual(vy, 0.)
        self.assertEqual(wz, 0.)

    def test_translation_norm_bounded_and_near_target_proportional(self):
        vx, vy, wz = self.command((0., 0., .7), (3., 4.), max_speed=.2, minimum_speed=.1)
        self.assertAlmostEqual(math.hypot(vx, vy), .2)
        vx, vy, wz = self.command((0., 0., 0.), (.2, 0.))
        self.assertAlmostEqual(vx, .2)
        self.assertEqual(vy, 0.)

    def test_near_goal_uses_minimum_speed_outside_arrival(self):
        vx, vy, wz = self.command((0., 0., 0.), (.16, 0.))
        self.assertAlmostEqual(math.hypot(vx, vy), .2)
        self.assertEqual(self.command((0., 0., 0.), (.1, 0.)), (0., 0., 0.))
        vx, vy, wz = self.command((0., 0., .8), (.16, 0.),
                                  max_speed=.15, minimum_speed=.12)
        self.assertAlmostEqual(math.hypot(vx, vy), .128)
        self.assertLessEqual(math.hypot(vx, vy), .15)

    def test_minimum_speed_schema_and_upper_bound(self):
        for value in (0., -1., float('nan'), float('inf'), True, .31):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.command((0., 0., 0.), (.16, 0.), minimum_speed=value)
        with self.assertRaises(ValueError):
            self.command((0., 0., 0.), (.16, 0.), max_speed=.1)

    def test_arrival_stops_translation_and_small_yaw_error(self):
        self.assertEqual(self.command((0., 0., .4), (.05, .05)), (0., 0., 0.))
        self.assertEqual(self.command((0., 0., .4), (.05, .05, .43)), (0., 0., 0.))

    def test_heading_wrap_and_rate_bound(self):
        vx, vy, wz = self.command((0., 0., math.pi - .03), (0., 0., -math.pi + .03))
        self.assertEqual((vx, vy), (0., 0.))
        self.assertAlmostEqual(wz, .36)
        vx, vy, wz = self.command((0., 0., 0.), (1., 0., math.pi / 2), max_yaw_rate=.5)
        self.assertEqual(wz, .5)
        self.assertGreater(vx, 0.)
        self.assertEqual(self.command((0., 0., 0.), (0., 0., -.2), heading_gain=2.)[2], -.4)

    def test_invalid_pose_target_and_bounds_fail_loud(self):
        for pose, target in [((0., 0.), (1., 1.)),
                             ((0., float('nan'), 0.), (1., 1.)),
                             ((0., 0., 0.), (1.,)),
                             ((0., 0., 0.), (1., 1., float('inf')))]:
            with self.subTest(pose=pose, target=target), self.assertRaises(ValueError):
                self.command(pose, target)
        for key in ('max_speed', 'tolerance', 'max_yaw_rate', 'heading_gain'):
            for value in (0., -1., float('nan'), True):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    self.command((0., 0., 0.), (1., 1.), **{key: value})


if __name__ == '__main__':
    unittest.main()
