"""Cache the exact NVIDIA 6.0 Go2 example assets; hash every downloaded file."""
from pathlib import Path
import hashlib
import json
import urllib.request
from urllib.parse import urljoin, urlsplit, unquote
from pxr import Sdf
ROOT=Path(__file__).resolve().parents[1]
BASE='https://omniverse-content-staging.s3-us-west-2.amazonaws.com/Assets/Isaac/4.5/'
CACHE=ROOT/'assets/vendor/training-nvidia'

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
    fetch(BASE+'Isaac/IsaacLab/Robots/Unitree/Go2/go2.usd')
    output=ROOT/'assets/vendor/training_manifest.json'
    if output.exists() and json.loads(output.read_text())!=manifest:
        raise RuntimeError('Vendor files changed; preserve manifest and create new vendor revision')
    if not output.exists():
        with output.open("x") as handle:json.dump(manifest,handle,indent=2)
if __name__=='__main__':main()
