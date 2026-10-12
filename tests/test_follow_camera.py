import math
import unittest
from warehouse_incident.follow_camera import follow_view

class FollowCameraTests(unittest.TestCase):
    def test_stays_behind_robot_and_above_its_body(self):
        eye, target = follow_view([10, 20, .3, 0])
        self.assertEqual(eye, (7.6, 20., 1.55))
        self.assertEqual(target, (10.65, 20., .5))
    def test_yaw_rotates_camera_offset_and_lookahead(self):
        eye,target=follow_view([10,20,.3,math.pi/2])
        self.assertAlmostEqual(eye[0],10);self.assertAlmostEqual(eye[1],17.6)
        self.assertAlmostEqual(target[0],10);self.assertAlmostEqual(target[1],20.65)
    def test_heading_wrap_and_translation_preserve_relative_geometry(self):
        a,b=follow_view([0,0,.3,.72]);c,d=follow_view([5,-3,.3,.72+2*math.pi])
        for i,shift in enumerate([5,-3,0]):
            self.assertAlmostEqual(c[i]-a[i],shift);self.assertAlmostEqual(d[i]-b[i],shift)
    def test_rejects_invalid_pose_instead_of_authoring_nonfinite_camera(self):
        for pose in [[],[1,2,3],[1,2,3,math.nan],[1,2,3,math.inf],[1,2,True,0]]:
            with self.subTest(pose=pose),self.assertRaises(ValueError):follow_view(pose)

if __name__=='__main__':unittest.main()
