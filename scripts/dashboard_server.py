"""Read-only local patrol evidence dashboard; never commands robot motion."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

PROJECT = Path(__file__).resolve().parents[1]
SAFE_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*\Z')


def resolve_attempt(name, root=PROJECT):
    if not isinstance(name,str) or not SAFE_NAME.fullmatch(name):
        raise ValueError('Attempt must be one safe evidence directory name')
    evidence = (root/'evidence').resolve()
    candidate = evidence/name
    if candidate.is_symlink() or candidate.resolve().parent != evidence or not candidate.is_dir():
        raise ValueError('Attempt must be an existing direct project evidence folder')
    return candidate.resolve()


def make_server(attempt, port=8125):
    attempt = Path(attempt).resolve()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def send_bytes(self,status,body,mime):
            self.send_response(status); self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            if path == '/api/state':
                state_file=attempt/'patrol-state.json'
                if not state_file.exists(): state={'phase':'PENDING','reason':'No recorded patrol state yet','aisles':[],'complete':False}
                else:
                    try:
                        if state_file.is_symlink(): raise ValueError('State symlinks disallowed')
                        state=json.loads(state_file.read_text(),parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
                        if not isinstance(state,dict): raise ValueError('State must be an object')
                    except (OSError,ValueError): state={'phase':'ERROR','reason':'Recorded state unreadable or malformed','aisles':[],'complete':False}
                self.send_bytes(200,json.dumps(state,allow_nan=False).encode(),'application/json');return
            if path in ('/','/index.html'):
                self.send_bytes(200,(PROJECT/'dashboard/index.html').read_bytes(),'text/html; charset=utf-8');return
            if path.startswith('/media/'):
                name=path[len('/media/'):]
                if SAFE_NAME.fullmatch(name) and Path(name).suffix.lower() in ('.jpg','.jpeg','.png','.mp4'):
                    media=attempt/name
                    if not media.is_symlink() and media.resolve().parent == attempt and media.is_file():
                        self.send_bytes(200,media.read_bytes(),mimetypes.guess_type(name)[0] or 'application/octet-stream');return
            self.send_bytes(404,b'Not found','text/plain')
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True)
    parser.add_argument('--port',type=int,default=8125);args=parser.parse_args()
    if not 1 <= args.port <= 65535: parser.error('Invalid port')
    try: attempt=resolve_attempt(args.attempt)
    except ValueError as exc: parser.error(str(exc))
    server=make_server(attempt,args.port)
    print(f'PATROL_DASHBOARD http://127.0.0.1:{args.port} attempt={args.attempt}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__=='__main__':main()
