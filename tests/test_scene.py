"""Static construction contract; these checks do not prove locomotion."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from pxr import Usd, UsdGeom, UsdPhysics
ROOT=Path(__file__).resolve().parents[1]

class SceneTests(unittest.TestCase):
    def test_carton_is_single_dynamic_body_with_enabled_collider(self):
        spec=importlib.util.spec_from_file_location('scene',ROOT/'scripts/build_scene.py')
        self.assertTrue(spec and spec.loader)
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'carton.usda';mod.author_carton(path)
            s=Usd.Stage.Open(str(path));root=s.GetDefaultPrim()
            self.assertTrue(root.HasAPI(UsdPhysics.RigidBodyAPI))
            colliders=[p for p in s.Traverse() if p.HasAPI(UsdPhysics.CollisionAPI)]
            self.assertEqual(len(colliders),1)
            self.assertTrue(UsdPhysics.CollisionAPI(colliders[0]).GetCollisionEnabledAttr().Get())
            self.assertAlmostEqual(UsdPhysics.MassAPI(root).GetMassAttr().Get(),3.)
            bounds=UsdGeom.BBoxCache(0,['default']).ComputeWorldBound(root).ComputeAlignedRange()
            self.assertAlmostEqual(bounds.GetSize()[0],.8)

    def test_disabling_graphs_does_not_access_expired_descendants(self):
        spec=importlib.util.spec_from_file_location('scene',ROOT/'scripts/build_scene.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        s=Usd.Stage.CreateInMemory();s.DefinePrim('/World','Xform')
        s.DefinePrim('/World/Clock','OmniGraph');s.DefinePrim('/World/Clock/tick','OmniGraphNode')
        s.DefinePrim('/World/Second','OmniGraph');s.DefinePrim('/World/Second/node','OmniGraphNode')
        mod.disable_graphs(s)
        self.assertFalse(s.GetPrimAtPath('/World/Clock').IsActive())
        self.assertFalse(s.GetPrimAtPath('/World/Second').IsActive())

    def test_carton_has_real_isaac_composition(self):
        spec=importlib.util.spec_from_file_location('scene',ROOT/'scripts/build_scene.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'Carton.usda';mod.author_carton(path)
            stage=Usd.Stage.Open(str(path));prim=stage.GetDefaultPrim()
            self.assertTrue(prim.HasAuthoredReferences())
            for name in ['base.usda','geometries.usd','materials.usda','instances.usda']:
                self.assertTrue((path.parent/'payloads'/name).is_file(),name)
