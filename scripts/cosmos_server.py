"""Serve the fixed incident prompt using an owned, pinned Cosmos model process.

Only main() imports Torch/Transformers or loads a checkpoint. The HTTP factory
accepts a predictor so contract tests use CPU fixtures without model downloads.
"""
import argparse
import base64
import binascii
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import math
import os
from pathlib import Path
import signal
import socket
import sys
import threading
import time
import uuid
import warnings

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'src'))
from warehouse_incident.cosmos import MODEL, REVISION, PROMPT, MAX_IMAGE, MAX_TOKENS, image_mime, parse_answer, strict_json, task_prompt, task_system

MAX_BODY = 12 * 1024 * 1024
MAX_PIXELS = 4096 * 4096


def build_model_messages(image,task='incident'):
    """Build the exact selected model chat without accepting external system text."""
    _,prompt=task_prompt(task)
    _,system=task_system(task)
    messages=[]
    if system is not None:
        messages.append({'role':'system','content':[{'type':'text','text':system}]})
    messages.append({'role':'user','content':[{'type':'image','image':image},{'type':'text','text':prompt}]})
    return messages


def _validate_payload(value, identity, prompt=PROMPT):
    if not isinstance(value, dict) or value.get('model') != identity['model']:
        raise ValueError('model does not match pinned service')
    if set(value) - {'model','messages','temperature','max_tokens'}:
        raise ValueError('unsupported request keys')
    tokens = value.get('max_tokens', MAX_TOKENS)
    if isinstance(tokens, bool) or not isinstance(tokens, int) or not 0 < tokens <= MAX_TOKENS:
        raise ValueError('invalid token bound')
    if value.get('temperature', 0) != 0:
        raise ValueError('deterministic temperature required')
    messages = value.get('messages')
    if not isinstance(messages, list) or len(messages) != 1 or not isinstance(messages[0], dict):
        raise ValueError('one user message required')
    if set(messages[0]) != {'role','content'} or messages[0]['role'] != 'user':
        raise ValueError('one user message required')
    content = messages[0]['content']
    if not isinstance(content, list) or len(content) != 2 or content[1] != {'type':'text','text':prompt}:
        raise ValueError('fixed selected task prompt and one image required')
    if not isinstance(content[0], dict) or set(content[0]) != {'type','image_url'} or content[0]['type'] != 'image_url':
        raise ValueError('embedded image required')
    image = content[0]['image_url']
    if not isinstance(image, dict) or set(image) != {'url'} or not isinstance(image['url'], str):
        raise ValueError('embedded image required')
    url = image['url']
    if not url.startswith(('data:image/png;base64,','data:image/jpeg;base64,')):
        raise ValueError('embedded PNG or JPEG required')
    pixels = base64.b64decode(url.split(',',1)[1], validate=True)
    mime = image_mime(pixels)
    if not url.startswith(f'data:{mime};base64,'):
        raise ValueError('image MIME does not match bytes')
    # Full decode rejects corrupt/truncated images before inference, with a pixel bound.
    from PIL import Image
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(pixels)) as source:
            if source.format not in ('PNG','JPEG') or source.width * source.height > MAX_PIXELS:
                raise ValueError('image exceeds pixel limit or unsupported format')
            source.load()
    return pixels


def make_owned_server(port, predict, identity, evidence_directory, read_timeout=20, inference_timeout=80, task='incident'):
    """Local single-flight service; close joins owned request and inference workers.

    HTTP inference timeout does not interrupt an unsafe Torch call. Its worker
    retains the single-flight lock until completion, persists timeout evidence,
    and is joined on close. No late success can turn that request into clear.
    """
    prompt_name,selected_prompt = task_prompt(task)
    system_name,selected_system=task_system(task)
    system_hash=hashlib.sha256(selected_system.encode()).hexdigest() if selected_system is not None else None
    for value in (read_timeout, inference_timeout):
        if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or value <= 0:
            raise ValueError('timeouts must be positive and finite')
    if not isinstance(identity, dict) or not all(isinstance(identity.get(key), str) for key in ('model','revision')):
        raise ValueError('service identity requires model and revision')
    evidence = Path(evidence_directory)
    evidence.mkdir(parents=True, exist_ok=True)
    identity = dict(identity)
    if identity.get('task',task)!=task or identity.get('prompt_name',prompt_name)!=prompt_name:
        raise ValueError('service identity task/prompt name does not match selected task')
    if identity.get('prompt_sha256',hashlib.sha256(selected_prompt.encode()).hexdigest()) != hashlib.sha256(selected_prompt.encode()).hexdigest():
        raise ValueError('service identity prompt SHA256 does not match selected task')
    if identity.get('system_prompt_name',system_name)!=system_name or identity.get('system_prompt_sha256',system_hash)!=system_hash:
        raise ValueError('service identity system prompt does not match selected task')
    identity.setdefault('system_prompt_name',system_name)
    identity.setdefault('system_prompt_sha256',system_hash)
    identity.setdefault('task',task)
    identity.setdefault('prompt_name',prompt_name)
    identity.setdefault('prompt_sha256',hashlib.sha256(selected_prompt.encode()).hexdigest())
    identity.setdefault('source_sha256',{p:hashlib.sha256((PROJECT / p).read_bytes()).hexdigest()
        for p in ('scripts/cosmos_server.py','src/warehouse_incident/cosmos.py','src/warehouse_incident/core.py')})
    lock = threading.Lock()
    workers, worker_lock = set(), threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(read_timeout)

        def log_message(self, *_):
            pass

        def respond(self, code, value):
            encoded = json.dumps(value, allow_nan=False).encode()
            self.send_response(code)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(encoded)))
            self.send_header('Connection','close')
            self.end_headers()
            try:
                self.wfile.write(encoded)
            except (BrokenPipeError, ConnectionResetError, socket.timeout):
                pass

        def do_GET(self):
            if self.path != '/health':
                return self.respond(404, {'error':'unknown endpoint'})
            self.respond(200, {**identity, 'status':'ready', 'busy':lock.locked()})

        def do_POST(self):
            if self.path != '/v1/chat/completions':
                return self.respond(404, {'error':'unknown endpoint'})
            try:
                if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type','').split(';')[0] != 'application/json':
                    raise ValueError('JSON with bounded Content-Length required')
                lengths = self.headers.get_all('Content-Length', [])
                if len(lengths) != 1:
                    raise ValueError('exactly one Content-Length required')
                count = int(lengths[0])
                if not 0 < count <= MAX_BODY:
                    raise ValueError('invalid request size')
                body = self.rfile.read(count)
                if len(body) != count:
                    raise ValueError('incomplete request')
                pixels = _validate_payload(strict_json(body), identity, selected_prompt)
            except socket.timeout:
                return self.respond(408, {'error':'request read timed out'})
            except (ValueError, KeyError, TypeError, IndexError, binascii.Error, OSError, Warning) as error:
                return self.respond(400, {'error':str(error)})
            if not lock.acquire(blocking=False):
                return self.respond(503, {'error':'model busy; retry a fresh observation'})
            request_id = str(uuid.uuid4())
            started = time.monotonic()
            completed = threading.Event()
            result = {}
            # Shared state guard resolves the deadline race before evidence is written.
            state_lock = threading.Lock()
            state = {'timed_out':False}
            record = {**identity, 'request_id':request_id, 'started_at':time.time(),
                      'image_sha256':hashlib.sha256(pixels).hexdigest(),
                      'prompt_sha256':hashlib.sha256(selected_prompt.encode()).hexdigest(),
                      'task':task, 'prompt_name':prompt_name,
                      'system_prompt_name':system_name, 'system_prompt_sha256':system_hash,
                      'acceptance':'visual model response only; no physical execution'}

            def infer():
                try:
                    raw = predict(pixels)
                    record['raw_response'] = raw
                    answer = parse_answer(raw)
                    record.update(status='inferred', assessment={'status':answer.status,'reason':answer.reason})
                    response = {'id':request_id, 'model':identity['model'], 'model_revision':identity['revision'],
                                'task':task, 'prompt_name':prompt_name,
                                'system_prompt_name':system_name, 'system_prompt_sha256':system_hash,
                                'prompt_sha256':hashlib.sha256(selected_prompt.encode()).hexdigest(),
                                'choices':[{'message':{'role':'assistant','content':json.dumps(record['assessment'])}}]}
                    code = 200
                except Exception as error:
                    record.update(status='failed', error=f'{type(error).__name__}: {error}')
                    response, code = {'id':request_id,'error':'inference or assessment validation failed'}, 502
                try:
                    with state_lock:
                        record['latency_s'] = time.monotonic() - started
                        if state['timed_out'] or record['latency_s'] > inference_timeout:
                            record['status'] = 'timed_out'
                            record.pop('assessment', None)
                            response, code = {'id':request_id,'error':'inference timed out'}, 504
                        try:
                            with (evidence / f'{request_id}.json').open('x') as output:
                                json.dump(record, output, indent=2, allow_nan=False)
                        except (OSError, TypeError, ValueError):
                            response, code = {'id':request_id,'error':'required inference evidence could not be persisted'}, 500
                        result.update(code=code, response={**response,'latency_s':record['latency_s']})
                        completed.set()
                finally:
                    lock.release()
                    with worker_lock:
                        workers.discard(threading.current_thread())

            worker = threading.Thread(target=infer, name=f'cosmos-incident-{request_id}', daemon=False)
            with worker_lock:
                workers.add(worker)
            try:
                worker.start()
            except Exception:
                with worker_lock:
                    workers.discard(worker)
                lock.release()
                return self.respond(500, {'error':'inference worker could not start'})
            if not completed.wait(inference_timeout):
                with state_lock:
                    if not completed.is_set():
                        state['timed_out'] = True
                        return self.respond(504, {'id':request_id,'error':'inference timed out'})
            self.respond(result['code'], result['response'])

    class OwnedServer(ThreadingHTTPServer):
        daemon_threads = False
        block_on_close = True
        def server_close(self):
            super().server_close()
            with worker_lock:
                remaining = list(workers)
            for worker in remaining:
                worker.join()

    server = OwnedServer(('127.0.0.1',port), Handler)
    server.timeout = .5
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8124)
    parser.add_argument('--revision', choices=[REVISION], default=REVISION)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--device', choices=['cpu','cuda'], default='cuda')
    parser.add_argument('--task',choices=['incident','patrol'],default='incident')
    parser.add_argument('--max-new-tokens', type=int, default=MAX_TOKENS)
    parser.add_argument('--inference-timeout', type=float, default=80)
    parser.add_argument('--read-timeout', type=float, default=20)
    args = parser.parse_args()
    prompt_name,selected_prompt=task_prompt(args.task)
    system_name,selected_system=task_system(args.task)
    system_hash=hashlib.sha256(selected_system.encode()).hexdigest() if selected_system is not None else None
    if not 1 <= args.max_new_tokens <= MAX_TOKENS:
        parser.error(f'--max-new-tokens must be within 1..{MAX_TOKENS}')
    if not args.attempt or Path(args.attempt).name != args.attempt or args.attempt in ('.','..'):
        parser.error('--attempt must be one directory name')
    if not all(math.isfinite(v) and v > 0 for v in (args.inference_timeout,args.read_timeout)):
        parser.error('timeouts must be positive and finite')
    out = PROJECT / 'evidence' / args.attempt
    out.mkdir(parents=True, exist_ok=False)
    import torch
    import transformers
    from huggingface_hub import HfApi
    from PIL import Image
    revision = HfApi().model_info(MODEL,revision=REVISION).sha
    if revision != REVISION:
        raise ValueError('service requires exact pinned model commit')
    if args.device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA requested but unavailable')
    device = 'cuda:0' if args.device == 'cuda' else 'cpu'
    identity = {'model':MODEL, 'revision':revision, 'torch':torch.__version__,
                'transformers':transformers.__version__, 'device':device,
                'gpu':torch.cuda.get_device_name(0) if args.device == 'cuda' else None,
                'pid':os.getpid(), 'max_new_tokens':args.max_new_tokens,
                'inference_timeout':args.inference_timeout,
                'task':args.task, 'prompt_name':prompt_name,
                'system_prompt_name':system_name, 'system_prompt_sha256':system_hash,
                'prompt_sha256':hashlib.sha256(selected_prompt.encode()).hexdigest(),
                'source_sha256':{p:hashlib.sha256((PROJECT / p).read_bytes()).hexdigest()
                    for p in ('scripts/cosmos_server.py','src/warehouse_incident/cosmos.py','src/warehouse_incident/core.py')}}
    (out / 'identity.json').write_text(json.dumps(identity,indent=2))
    model = transformers.Qwen3VLForConditionalGeneration.from_pretrained(
        MODEL,revision=revision,dtype=torch.bfloat16 if args.device == 'cuda' else torch.float32,
        attn_implementation='sdpa').to(device).eval()
    processor = transformers.AutoProcessor.from_pretrained(MODEL,revision=revision)

    def predict(pixels):
        with Image.open(io.BytesIO(pixels)) as source:
            image = source.convert('RGB')
            # Keep laptop VRAM bounded; preserve aspect ratio, avoid upscaling.
            image.thumbnail((960,960))
        messages = build_model_messages(image,task=args.task)
        inputs = processor.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,
            return_dict=True,return_tensors='pt').to(device)
        with torch.inference_mode():
            ids = model.generate(**inputs,max_new_tokens=args.max_new_tokens,do_sample=False,
                                 max_time=args.inference_timeout)
        return processor.batch_decode(ids[:,inputs.input_ids.shape[1]:],skip_special_tokens=True)[0]

    server = make_owned_server(args.port,predict,identity,out / 'requests',args.read_timeout,args.inference_timeout,task=args.task)
    stopping = False
    def stop(*_):
        nonlocal stopping
        stopping = True
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,stop)
    print('COSMOS_INCIDENT_READY '+json.dumps(identity),flush=True)
    try:
        while not stopping:
            server.handle_request()
    finally:
        server.server_close()
        (out / 'shutdown.json').write_text(json.dumps({'stopped_at':time.time(),'owned_shutdown':True}))


if __name__ == '__main__':main()
