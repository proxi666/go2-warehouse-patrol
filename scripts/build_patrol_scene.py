"""Immutable four-row warehouse derivative for operator inspection, not routing."""
import argparse,hashlib,json,os,sys
from pathlib import Path
from pxr import Gf,Usd,UsdGeom,UsdPhysics,UsdShade,UsdLux
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_scene import author_carton,disable_graphs,marker,metadata
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'assets/source/V39'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def reference(stage,path,asset,xyz,yaw=0):
 prim=UsdGeom.Xform.Define(stage,path)
 prim.GetPrim().GetReferences().AddReference(os.path.relpath(asset,Path(stage.GetRootLayer().realPath).parent))
 prim.AddTranslateOp().Set(Gf.Vec3d(*xyz));prim.AddRotateZOp().Set(yaw)
 return prim.GetPrim()
def build(out,cfg):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 original={str(p.relative_to(SOURCE)):sha(p) for p in SOURCE.rglob('*') if p.is_file()}
 stage=Usd.Stage.CreateNew(str(out/(out.name+'.usda')))
 stage.GetRootLayer().subLayerPaths=[os.path.relpath(SOURCE/'V39.usd',out)]
 metadata(stage,stage.GetPrimAtPath('/World'));disable_graphs(stage)
 for p in list(stage.GetPrimAtPath('/World').GetChildren()):
  if p.GetName().startswith('racks_') or p.GetName() in ('pallet_amr','LoadingStation','Actors','ROS'):
   stage.OverridePrim(p.GetPath()).SetActive(False)
 for name in ('racks','pallets','boxes','cartons','forklifts'):
  stage.OverridePrim('/World/Twin/'+name).SetActive(False)
 rack_asset=SOURCE/'library/rack/sm_rack_long_empty_a01_01.usd'
 pallet_asset=SOURCE/'library/pallet/sm_pallet_block_b02_01.usd'
 box_asset=SOURCE/'library/box/sm_box_cardboard_large_a02_01.usd'
 for i,x in enumerate(cfg['rack_x'],1):
  parent=f'/World/PatrolDemo/Racks/Row{i}'
  UsdGeom.Xform.Define(stage,parent)
  for j,y in enumerate(cfg['rack_y_modules'],1):reference(stage,parent+f'/Rack{j}',rack_asset,(x,y,0),90)
  for k,y in enumerate((14.65,16,17.35,18.65,20,21.35)):
   for level,z in enumerate((.51,2.01)):
    reference(stage,parent+f'/Pallet{k}_{level}',pallet_asset,(x,y,z),90)
    reference(stage,parent+f'/Carton{k}_{level}',box_asset,(x,y,z+.209),0)
  # Static full-row proxy: aisle clearance is physical, without costly visual-mesh cooking.
  proxy=UsdGeom.Cube.Define(stage,parent+'/CollisionProxy');proxy.CreateSizeAttr(1)
  proxy.AddTranslateOp().Set(Gf.Vec3d(x,18,1.7));proxy.AddScaleOp().Set(Gf.Vec3f(1.2,8,3.4))
  proxy.CreateVisibilityAttr('invisible');UsdPhysics.CollisionAPI.Apply(proxy.GetPrim()).CreateCollisionEnabledAttr(True)
 # Referenced visual furniture bodies stay static; the dedicated row proxies own collisions.
 for p in list(stage.Traverse()):
  if str(p.GetPath()).startswith('/World/PatrolDemo/Racks') and p.HasAPI(UsdPhysics.RigidBodyAPI):
   UsdPhysics.RigidBodyAPI(p).CreateRigidBodyEnabledAttr(False)
 paint=UsdShade.Material.Define(stage,'/World/PatrolDemo/MatteLanePaint')
 shader=UsdShade.Shader.Define(stage,'/World/PatrolDemo/MatteLanePaint/Surface');shader.CreateIdAttr('UsdPreviewSurface')
 from pxr import Sdf
 shader.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set((.12,.23,.25));shader.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(1.)
 shader.CreateInput('metallic',Sdf.ValueTypeNames.Float).Set(0.);paint.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),'surface')
 for lane in cfg['aisles']:
  marker(stage,'/World/PatrolDemo/Lanes/'+lane['id'].replace('-','_'),(lane['mouth'][0],17.75),(2.8,9.5),(.12,.23,.25))
  UsdShade.MaterialBindingAPI.Apply(stage.GetPrimAtPath('/World/PatrolDemo/Lanes/'+lane['id'].replace('-','_'))).Bind(paint)
 carton=out/'Carton.usda';author_carton(carton)
 incident=UsdGeom.Xform.Define(stage,'/World/IncidentCarton');incident.GetPrim().GetReferences().AddReference('./Carton.usda')
 incident.AddTranslateOp().Set(Gf.Vec3d(*cfg['incident_pose']))
 material=UsdShade.Material.Define(stage,'/World/PatrolDemo/GroundMaterial')
 ma=UsdPhysics.MaterialAPI.Apply(material.GetPrim());ma.CreateStaticFrictionAttr(1);ma.CreateDynamicFrictionAttr(1);ma.CreateRestitutionAttr(0)
 UsdShade.MaterialBindingAPI.Apply(stage.GetPrimAtPath('/World/site_ground')).Bind(material,materialPurpose='physics')
 light=UsdLux.RectLight.Define(stage,'/World/PatrolDemo/InspectionLight')
 light.AddTranslateOp().Set(Gf.Vec3d(0,17.5,4.4));light.CreateWidthAttr(18);light.CreateHeightAttr(14);light.CreateIntensityAttr(1800)
 camera=UsdGeom.Camera.Define(stage,'/World/PatrolDemo/ObserverCamera')
 camera.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(Gf.Vec3d(0,17.2,4.4),Gf.Vec3d(0,17.2,0),Gf.Vec3d(0,1,0)).GetInverse())
 camera.CreateProjectionAttr('orthographic');camera.CreateHorizontalApertureAttr(210);camera.CreateVerticalApertureAttr(118.125)
 camera.CreateClippingRangeAttr(Gf.Vec2f(.03,100))
 stage.GetRootLayer().customLayerData={'revision':out.name,'purpose':'Go2 aisle inspection and human clearance alerts','native_acceptance':'pending','source_revision':'V39'}
 stage.GetRootLayer().Save()
 preserved=all(sha(SOURCE/f)==h for f,h in original.items())
 manifest={'source':str(SOURCE),'source_sha256':original,'source_preserved':preserved,'stage_sha256':sha(out/(out.name+'.usda')),'carton_sha256':sha(carton),'rack_rows':len(cfg['rack_x']),'aisles':cfg['aisles'],'incident_pose':cfg['incident_pose'],'rack_proxy_size_m':[1.2,8,3.4],'rack_source':str(rack_asset),'fixture_mass_assumption_kg':3,'simready':'Carton schemas and foundation validation separate; referenced visual shelves static and row collision proxies authored; no full world certification claim'}
 (out/'BUILD_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
 if not preserved:raise RuntimeError('Cached source changed; retain failed revision')
 return out/(out.name+'.usda')
def main():
 p=argparse.ArgumentParser();p.add_argument('--revision',default='V49');args=p.parse_args()
 if not args.revision.isalnum():raise ValueError('Alphanumeric revision required')
 cfg=json.loads((ROOT/'config/patrol.json').read_text());print(build(ROOT/'assets'/args.revision,cfg))
if __name__=='__main__':main()
