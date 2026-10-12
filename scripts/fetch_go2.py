"""Cache the exact NVIDIA 6.0 Go2 example assets; hash every downloaded file."""
from pathlib import Path
import hashlib
import json
import urllib.request
from urllib.parse import urljoin, urlsplit, unquote
from pxr import Sdf
ROOT=Path(__file__).resolve().parents[1]
BASE='https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/'
CACHE=ROOT/'assets/vendor/nvidia'

def main():
    manifest={}
    def fetch(url):
        if url in manifest:return
        if not url.startswith(BASE):raise ValueError('Unexpected asset origin: '+url)
        rel=unquote(url[len(BASE):]);target=CACHE/rel
        if '..' in Path(rel).parts:raise ValueError('Asset path traversal')
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():data=target.read_bytes()
        else:
            with urllib.request.urlopen(url,timeout=60) as response:data=response.read()
            tmp=target.with_suffix(target.suffix+'.partial');tmp.write_bytes(data);tmp.replace(target)
        manifest[url]={'path':str(target.relative_to(ROOT)),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
        print(rel,len(data),flush=True)
        if target.suffix.lower() in {'.usd','.usda','.usdc'}:
            layer=Sdf.Layer.FindOrOpen(str(target))
            if not layer:raise RuntimeError('Unreadable USD '+str(target))
            for dep in sorted(set(layer.GetCompositionAssetDependencies())|set(layer.GetExternalAssetDependencies())):
                if dep:fetch(urljoin(url,dep))
    fetch(BASE+'Isaac/Samples/Mujoco_Menagerie/unitree_go2/go2/go2.usda')
    for name in ['physx_policy.pt','physx_env.yaml']:fetch(BASE+'Isaac/Samples/Policies/go2/'+name)
    output=ROOT/'assets/vendor/manifest.json'
    if output.exists() and json.loads(output.read_text())!=manifest:
        raise RuntimeError('Vendor files changed; preserve manifest and create new vendor revision')
    if not output.exists():
        with output.open("x") as handle:json.dump(manifest,handle,indent=2)
if __name__=='__main__':main()
