"""Fetch the pinned official Isaac Lab Go2 checkpoint without replacing a cache."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/IsaacLab/PretrainedCheckpoints/rsl_rl/Isaac-Velocity-Flat-Unitree-Go2-v0/checkpoint.pt'
SOURCE_SHA256 = '32039715f0892650691aa8d5c50233e7c4b858469d87114ef92794e2c65b59c0'
TASK = 'Isaac-Velocity-Flat-Unitree-Go2-v0'
MAX_BYTES = 16 * 1024 * 1024


def validate_checkpoint(folder):
    source = Path(folder) / 'checkpoint.pt'
    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise RuntimeError('Published checkpoint identity changed or missing; preserve cache')
    return source


def main():
    folder = ROOT / 'assets/vendor/isaaclab-pretrained'
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / 'manifest.json'
    manifest = {'url':URL, 'sha256':SOURCE_SHA256, 'task':TASK}
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        raise RuntimeError('Published checkpoint manifest changed; preserve cache')
    target = folder / 'checkpoint.pt'
    if not target.exists():
        # Leave a failed partial download for diagnosis, never substitute it for a checkpoint.
        with tempfile.NamedTemporaryFile(dir=folder, prefix='checkpoint-', suffix='.partial', delete=False) as partial:
            with urllib.request.urlopen(URL, timeout=60) as response:
                data = response.read(MAX_BYTES + 1)
            partial.write(data)
            temporary = Path(partial.name)
        if len(data) > MAX_BYTES or hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
            raise RuntimeError(f'Published checkpoint download failed size/hash validation; evidence: {temporary}')
        os.link(temporary, target)  # Exclusive publication: never replace another cache writer.
        temporary.unlink()
    validate_checkpoint(folder)
    if not manifest_path.exists():
        with manifest_path.open('x') as output:
            json.dump(manifest, output, indent=2)
    print(json.dumps({'checkpoint':str(target), 'sha256':SOURCE_SHA256, 'verified':True}))


if __name__ == '__main__':main()
