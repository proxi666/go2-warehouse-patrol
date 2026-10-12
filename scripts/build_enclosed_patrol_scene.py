"""Immutable enclosed patrol using genuine NVIDIA full_warehouse geometry."""
import argparse,hashlib,json
from pathlib import Path
import shutil,sys,tempfile
from pxr import Gf,Usd,UsdGeom,UsdLux
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_clean_patrol_scene import build as clean_build, camera
from floor_markings import author as author_markings
ROOT=Path(__file__).resolve().parents[1]
SHELL=ROOT/'assets/vendor/warehouse-shell-001/warehouse_shell.usd'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def build(out,config):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 with tempfile.TemporaryDirectory() as temporary:
  base=clean_build(Path(temporary)/'Base',config)
  stage=Usd.Stage.Open(str(base))
  stage.RemovePrim('/World/Ground')
  shell=UsdGeom.Xform.Define(stage,'/World/WarehouseShell')
  shell.GetPrim().GetReferences().AddReference(str(SHELL.resolve()))
  stage.GetPrimAtPath('/World/Lighting/Inspection').SetActive(False)
  dome=UsdLux.DomeLight(stage.GetPrimAtPath('/World/Lighting/Dome'));dome.CreateIntensityAttr(200)
  UsdGeom.Scope.Define(stage,'/World/Lighting/Indoor')
  for i,y in enumerate((12,19,26,33,40),1):
   light=UsdLux.RectLight.Define(stage,f'/World/Lighting/Indoor/Panel{i}')
   light.AddTranslateOp().Set(Gf.Vec3d(0,y,8))
   light.CreateWidthAttr(20);light.CreateHeightAttr(8);light.CreateIntensityAttr(2500)
   light.CreateEnableColorTemperatureAttr(True);light.CreateColorTemperatureAttr(6500)
  author_markings(stage,config)
  stage.RemovePrim('/World/OverviewCamera')
  camera(stage,'/World/OverviewCamera',(-10,7,4.8),(0,18,1.5))
  stage.GetRootLayer().customLayerData={'revision':out.name,'purpose':'Bright enclosed Go2 warehouse patrol','warehouse_source':'NVIDIA Simple_Warehouse/full_warehouse.usd','certification':'Selected checks only; full scene certification not claimed'}
  flat=stage.Flatten();path=out/(out.name+'.usd');flat.Export(str(path))
  manifest=json.loads((base.parent/'BUILD_MANIFEST.json').read_text())
  manifest.update(revision=out.name,stage_file=path.name,stage_sha256=sha(path),warehouse_source='NVIDIA Simple_Warehouse/full_warehouse.usd',warehouse_shell_sha256=sha(SHELL),warehouse_shell_manifest=json.loads((SHELL.parent/'BUILD_MANIFEST.json').read_text()),floor_count=1,composition='Single flattened USD with genuine NVIDIA floor, walls and roof; no external asset files')
  (out/'BUILD_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
  for name in ('RACK_LICENSE.txt','BOX_LICENSE.txt','ATTRIBUTION.txt'):shutil.copy2(base.parent/name,out/name)
  with (out/'ATTRIBUTION.txt').open('a') as file:file.write('Warehouse enclosure: NVIDIA Isaac Sim6.0 full_warehouse structural geometry, with source URLs/checksums retained in build provenance. Upstream NVIDIA asset distribution terms apply.\n')
 return path

def main():
 p=argparse.ArgumentParser();p.add_argument('--revision',default='V55');args=p.parse_args()
 if not args.revision.isalnum():p.error('Alphanumeric revision required')
 print(build(ROOT/'assets'/args.revision,json.loads((ROOT/'config/patrol.json').read_text())))

if __name__=='__main__':main()
