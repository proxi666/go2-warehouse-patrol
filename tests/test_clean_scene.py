"""Composition contracts for the clean world; native motion is a separate gate."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from pxr import Usd, UsdGeom, UsdPhysics

ROOT = Path(__file__).resolve().parents[1]

class CleanSceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('clean_scene', ROOT/'scripts/build_clean_patrol_scene.py')
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)
        cls.temp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.temp.name)/'V50'
        cls.config = json.loads((ROOT/'config/patrol.json').read_text())
        cls.path = cls.builder.build(cls.out, cls.config)
        cls.stage = Usd.Stage.Open(str(cls.path))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_one_floor_and_no_inherited_building(self):
        self.assertEqual(self.stage.GetRootLayer().subLayerPaths, [])
        self.assertEqual(len([layer for layer in self.stage.GetUsedLayers() if not layer.anonymous]), 1)
        for name in ('site_ground','floor_slabs','office_bullpen','elevator','loading_bay','pallet_amr','Twin'):
            self.assertFalse(self.stage.GetPrimAtPath('/World/'+name))
        floors = [p for p in self.stage.Traverse() if p.GetAttribute('patrol:role').Get() == 'floor']
        self.assertEqual(len(floors), 1)
        self.assertTrue(floors[0].HasAPI(UsdPhysics.CollisionAPI))
        bounds = UsdGeom.BBoxCache(0,['default']).ComputeWorldBound(floors[0]).ComputeAlignedRange()
        self.assertAlmostEqual(bounds.GetMax()[2], 0, places=6)

    def test_four_rows_and_three_clear_approaches(self):
        rows = list(self.stage.GetPrimAtPath('/World/PatrolDemo/Racks').GetChildren())
        self.assertEqual(len(rows), 4)
        cache = UsdGeom.BBoxCache(0,['default','guide'],False,True)
        for row in rows:
            proxy = row.GetChild('CollisionProxy')
            self.assertTrue(proxy.HasAPI(UsdPhysics.CollisionAPI))
            bounds = cache.ComputeWorldBound(proxy).ComputeAlignedRange()
            self.assertAlmostEqual(bounds.GetSize()[0],1.2,places=5)
            for lane in self.config['aisles']:
                for name in ('mouth','confirm','entry','forward'):
                    p = lane[name]
                    self.assertFalse(bounds.GetMin()[0]-.3 < p[0] < bounds.GetMax()[0]+.3 and bounds.GetMin()[1]-.3 < p[1] < bounds.GetMax()[1]+.3)
        self.assertEqual(len(list(self.stage.GetPrimAtPath('/World/PatrolDemo/Lanes').GetChildren())),3)

    def test_robot_and_dynamic_carton_are_saved_in_the_usd(self):
        self.assertTrue(self.stage.GetPrimAtPath('/World/Go2/base').HasAPI(UsdPhysics.RigidBodyAPI))
        joints = [p for p in self.stage.Traverse() if p.IsA(UsdPhysics.RevoluteJoint) and str(p.GetPath()).startswith('/World/Go2/')]
        self.assertEqual(len(joints), 12)
        incident = self.stage.GetPrimAtPath('/World/IncidentCarton')
        self.assertTrue(UsdPhysics.RigidBodyAPI(incident).GetRigidBodyEnabledAttr().Get())
        self.assertEqual(UsdPhysics.MassAPI(incident).GetMassAttr().Get(),3)
        self.assertTrue(self.stage.GetPrimAtPath('/World/IncidentCarton/Body').HasAPI(UsdPhysics.CollisionAPI))
        self.assertTrue(self.stage.GetPrimAtPath('/World/PatrolDemo/ObserverCamera'))

    def test_no_hidden_library_colliders_or_external_shader_assets(self):
        prims = list(Usd.PrimRange(self.stage.GetPseudoRoot(),Usd.TraverseInstanceProxies()))
        rack_colliders = [p for p in prims if str(p.GetPath()).startswith('/World/PatrolDemo/Racks/') and p.HasAPI(UsdPhysics.CollisionAPI) and UsdPhysics.CollisionAPI(p).GetCollisionEnabledAttr().Get()]
        self.assertEqual(len(rack_colliders),4)
        for p in prims:
            for a in p.GetAttributes():
                if str(a.GetTypeName()) in ('asset','asset[]'):
                    value = a.Get()
                    self.assertFalse(value, str(a.GetPath()))

    def test_material_targets_do_not_point_to_inactive_imports(self):
        for p in Usd.PrimRange(self.stage.GetPseudoRoot(),Usd.TraverseInstanceProxies()):
            for rel in p.GetRelationships():
                if not rel.GetName().startswith('material:binding'):continue
                for target in rel.GetTargets():
                    mat=self.stage.GetPrimAtPath(target)
                    self.assertTrue(mat and mat.IsActive(),str(rel.GetPath()))

    def test_single_usd_sources_preserved_and_immutable(self):
        self.assertEqual(list(self.out.rglob('*.usd')), [self.path])
        self.assertFalse(list(self.out.rglob('*.usda')))
        self.assertEqual([dep for dep in self.stage.GetRootLayer().GetCompositionAssetDependencies() if dep], [])
        manifest = json.loads((self.out/'BUILD_MANIFEST.json').read_text())
        self.assertTrue(manifest['source_preserved'])
        self.assertEqual(manifest['floor_count'],1)
        self.assertTrue(manifest['robot_embedded'])
        original = self.path.read_bytes()
        with self.assertRaises(FileExistsError): self.builder.build(self.out,self.config)
        self.assertEqual(self.path.read_bytes(),original)

if __name__ == '__main__': unittest.main()
