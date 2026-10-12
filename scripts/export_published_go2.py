"""Export the pinned already-trained checkpoint; verify and preserve cached exports."""
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from fetch_published_go2 import SOURCE_SHA256, validate_checkpoint

ROOT = Path(__file__).resolve().parents[1]
MAX_EXPORT_ERROR = 1e-6


def verify_export(folder):
    folder = Path(folder)
    path, record_path = folder / 'policy.pt', folder / 'EXPORT.json'
    if not path.exists() and not record_path.exists():
        return None
    if not path.is_file() or not record_path.is_file():
        raise RuntimeError('Incomplete published export; preserve existing files')
    record = json.loads(record_path.read_text())
    error = record.get('max_export_error')
    if (record.get('source_sha256') != SOURCE_SHA256
            or hashlib.sha256(path.read_bytes()).hexdigest() != record.get('policy_sha256')
            or isinstance(error,bool) or not isinstance(error,(int,float))
            or not math.isfinite(error) or not 0 <= error <= MAX_EXPORT_ERROR
            or record.get('training_performed') is not False):
        raise RuntimeError('Published export failed identity/error verification; preserve files')
    return record


def main():
    folder = ROOT / 'assets/vendor/isaaclab-pretrained'
    source = validate_checkpoint(folder)
    cached = verify_export(folder)
    if cached is not None:
        print(json.dumps({'path':str(folder / 'policy.pt'),'export_error':cached['max_export_error'],'cached':True}))
        return
    import torch
    checkpoint = torch.load(source,map_location='cpu',weights_only=False)
    state = checkpoint['actor_state_dict']
    # Official Go2 flat RSL-RL actor: 48 inputs, 128/128/128 ELU, 12 outputs.
    model = torch.nn.Sequential(torch.nn.Linear(48,128),torch.nn.ELU(),torch.nn.Linear(128,128),torch.nn.ELU(),torch.nn.Linear(128,128),torch.nn.ELU(),torch.nn.Linear(128,12))
    model.load_state_dict({k.removeprefix('mlp.'):v for k,v in state.items() if k.startswith('mlp.')},strict=True)
    model.eval()
    sample = torch.randn((16,48),generator=torch.Generator().manual_seed(7))
    with tempfile.TemporaryDirectory(dir=folder,prefix='policy-export-') as temporary:
        exported = Path(temporary) / 'policy.pt'
        torch.jit.script(model).save(str(exported))
        with torch.inference_mode():
            error = (model(sample)-torch.jit.load(str(exported))(sample)).abs().max().item()
        if not math.isfinite(error) or error > MAX_EXPORT_ERROR:
            raise RuntimeError(f'Published export numerical verification failed: {error}')
        record = {'source_sha256':SOURCE_SHA256,'policy_sha256':hashlib.sha256(exported.read_bytes()).hexdigest(),
                  'training_iteration':checkpoint['iter'],'architecture':'48 -> 128 ELU -> 128 ELU -> 128 ELU ->12',
                  'normalizer':'none in actor_state_dict','max_export_error':error,'training_performed':False}
        os.link(exported,folder / 'policy.pt')
        with (folder / 'EXPORT.json').open('x') as output:
            json.dump(record,output,indent=2)
    print(json.dumps({'path':str(folder / 'policy.pt'),'export_error':error,'cached':False}))


if __name__ == '__main__':main()
