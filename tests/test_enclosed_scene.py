"""Enclosed NVIDIA warehouse composition, without native acceptance claims."""
import importlib.util,json,tempfile,unittest
from pathlib import Path
from pxr import Usd,UsdGeom,UsdPhysics
ROOT=Path(__file__).resolve().parents[1]

class EnclosedSceneTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  spec=importlib.util.spec_from_file_location('enclosed',ROOT/'scripts/build_enclosed_patrol_scene.py')
  cls.builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.builder)
  cls.temp=tempfile.TemporaryDirectory();cls.out=Path(cls.temp.name)/'V53'
  cls.cfg=json.loads((ROOT/'config/patrol.json').read_text())
  cls.path=cls.builder.build(cls.out,cls.cfg);cls.stage=Usd.Stage.Open(str(cls.path))
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def test_one_nvidia_floor_and_no_base_ground(self):
  self.assertFalse(self.stage.GetPrimAtPath('/World/Ground'))
  floors=[p for p in self.stage.Traverse() if p.GetAttribute('patrol:role').Get()=='floor']
  self.assertEqual(len(floors),1);self.assertTrue(floors[0].HasAPI(UsdPhysics.CollisionAPI))
  bound=UsdGeom.BBoxCache(0,['default']).ComputeWorldBound(floors[0]).ComputeAlignedRange()
  self.assertAlmostEqual(bound.GetMax()[2],0,places=4)
  for lane in self.cfg['aisles']:
   for key in ('entry','mouth','confirm','forward'):
    x,y,*_=lane[key];self.assertTrue(bound.GetMin()[0]<x<bound.GetMax()[0]);self.assertTrue(bound.GetMin()[1]<y<bound.GetMax()[1])
 def test_structural_shell_roof_and_bright_indoor_lights(self):
  shell=self.stage.GetPrimAtPath('/World/WarehouseShell');self.assertTrue(shell)
  self.assertTrue(self.stage.GetPrimAtPath('/World/WarehouseShell/Roof'))
  self.assertTrue(self.stage.GetPrimAtPath('/World/WarehouseShell/Walls'))
  bound=UsdGeom.BBoxCache(0,['default']).ComputeWorldBound(shell).ComputeAlignedRange()
  self.assertGreater(bound.GetMax()[2],8)
  self.assertGreaterEqual(len(list(self.stage.GetPrimAtPath('/World/Lighting/Indoor').GetChildren())),3)
  self.assertTrue(self.stage.GetPrimAtPath('/World/Go2/base').HasAPI(UsdPhysics.RigidBodyAPI))
 def test_extended_rows_deeper_observation_and_flat_markings(self):
  cache=UsdGeom.BBoxCache(0,['default','guide'],False,True)
  for row in self.stage.GetPrimAtPath('/World/PatrolDemo/Racks').GetChildren():
   bound=cache.ComputeWorldBound(row.GetChild('CollisionProxy')).ComputeAlignedRange()
   self.assertAlmostEqual(bound.GetMin()[1],14,places=4)
   self.assertAlmostEqual(bound.GetMax()[1],43.5,places=4)
   self.assertGreater(len([p for p in row.GetChildren() if p.GetName().startswith('Rack')]),7)
  for label in ('A1','A2','A3','RobotPark'):
   root=self.stage.GetPrimAtPath('/World/PatrolDemo/Markings/'+label)
   self.assertTrue(root,label)
   for p in Usd.PrimRange(root):self.assertFalse(p.HasAPI(UsdPhysics.CollisionAPI))
  manifest=json.loads((self.out/'BUILD_MANIFEST.json').read_text())
  self.assertEqual(manifest['incident_pose'][1],22)
  for lane in manifest['aisles']:
   self.assertEqual(lane['mouth'][1],12.3);self.assertEqual(lane['confirm'][1],18)
   self.assertEqual(lane['forward'][1],12.8)

 def test_parking_label_is_above_blue_bay(self):
  root='/World/PatrolDemo/Markings/RobotPark/'
  bay=UsdGeom.Mesh(self.stage.GetPrimAtPath(root+'Bay')).GetPointsAttr().Get()
  label=UsdGeom.Mesh(self.stage.GetPrimAtPath(root+'Label')).GetPointsAttr().Get()
  self.assertLess(max(p[2] for p in bay),min(p[2] for p in label))

 def test_self_contained_immutable_nvidia_derivative(self):
  self.assertEqual(len([l for l in self.stage.GetUsedLayers() if not l.anonymous]),1)
  self.assertFalse(self.stage.GetRootLayer().subLayerPaths)
  manifest=json.loads((self.out/'BUILD_MANIFEST.json').read_text())
  self.assertEqual(manifest['warehouse_source'],'NVIDIA Simple_Warehouse/full_warehouse.usd')
  self.assertEqual(manifest['floor_count'],1)
  old=self.path.read_bytes()
  with self.assertRaises(FileExistsError):self.builder.build(self.out,self.cfg)
  self.assertEqual(self.path.read_bytes(),old)

if __name__=='__main__':unittest.main()
