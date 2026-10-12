"""New rack layout contracts; no claim of native sensor/robot acceptance."""
import importlib.util,json,tempfile,unittest
from pathlib import Path
from pxr import Usd,UsdGeom,UsdPhysics
ROOT=Path(__file__).resolve().parents[1]
class PatrolSceneTests(unittest.TestCase):
 def setUp(self):
  spec=importlib.util.spec_from_file_location('patrol_scene',ROOT/'scripts/build_patrol_scene.py')
  self.mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.mod)
  self.cfg=json.loads((ROOT/'config/patrol.json').read_text())
 def test_four_physical_rows_three_accessible_aisles_and_no_amr(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'V44';self.mod.build(out,self.cfg)
   s=Usd.Stage.Open(str(out/'V44.usda'))
   rows=list(s.GetPrimAtPath('/World/PatrolDemo/Racks').GetChildren());self.assertEqual(len(rows),4)
   self.assertFalse(s.GetPrimAtPath('/World/pallet_amr').IsActive())
   self.assertEqual(len(self.cfg['aisles']),3)
   cache=UsdGeom.BBoxCache(0,['default'])
   bounds=[]
   for row in rows:
    collider=row.GetChild('CollisionProxy');self.assertTrue(collider.HasAPI(UsdPhysics.CollisionAPI))
    bounds.append(cache.ComputeWorldBound(collider).ComputeAlignedRange())
   for aisle in self.cfg['aisles']:
    for pose in [aisle['mouth'],aisle['confirm']]:
     self.assertFalse(any(b.GetMin()[0]-.3<pose[0]<b.GetMax()[0]+.3 and b.GetMin()[1]-.3<pose[1]<b.GetMax()[1]+.3 for b in bounds))
   m=json.loads((out/'BUILD_MANIFEST.json').read_text());self.assertTrue(m['source_preserved']);self.assertEqual(m['rack_rows'],4)
 def test_revision_cannot_overwrite_existing_asset(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'V44';out.mkdir();sentinel=out/'user.usda';sentinel.write_text('user asset')
   with self.assertRaises(FileExistsError):self.mod.build(out,self.cfg)
   self.assertEqual(sentinel.read_text(),'user asset')
