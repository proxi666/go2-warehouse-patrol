"""Strict image-only incident assessment against one pinned local Cosmos service."""
import base64
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from .core import Assessment

MODEL = 'nvidia/Cosmos-Reason2-2B'
REVISION = '9ce19a195e423419c349abfc86fd07178b230561'
ENDPOINT = 'http://127.0.0.1:8124/v1/chat/completions'
MAX_IMAGE = 8 * 1024 * 1024
MAX_RESPONSE = 1024 * 1024
MAX_TOKENS = 1024
PROMPT = '''Judge whether the turquoise floor lane visible nearest the camera is empty
or occupied by an object. A solid object resting on this lane is an obstruction
even when turquoise floor remains visible in front of it or around its sides.
An object beyond the far end of the painted lane is outside the inspected lane.
Classify an occupied lane as blocked and an empty lane as clear. Return only one JSON object with exactly two keys: "status" and "reason".
status must be "clear", "blocked", or "uncertain"; reason must be a short description
of visible evidence. Use uncertain if the image cannot establish whether the lane
is occupied. Do not give coordinates or commands.'''


PATROL_PROMPT = '''Check the actual visible image. If it shows only a flat floor surface with no
separate object standing on it, the floor is clear. Do not invent objects. Use
blocked only for a visible freestanding box, carton, or other physical obstacle
resting on the floor. Stored objects supported by shelves and objects outside the
painted floor lane are not obstacles in that lane. Use uncertain if floor placement
cannot be determined. Return one JSON object with exactly keys "status" and "reason". status must be "clear", "blocked", or "uncertain". reason must describe only visible evidence. Do not give coordinates or commands.
The reason must support the selected status. For blocked, name the visible object
and its floor placement, such as "brown carton on floor". Never describe the floor
as empty or clear when status is blocked. For clear, describe the unobstructed
visible floor. Before returning JSON, check that status and reason agree.'''

PATROL_SYSTEM = 'You are a helpful assistant.'


def task_prompt(task='incident'):
    """Return the literal name/text for a known task, never a freeform prompt."""
    if not isinstance(task,str) or task not in ('incident','patrol'):
        raise ValueError('task must be incident or patrol')
    return ('PROMPT',PROMPT) if task=='incident' else ('PATROL_PROMPT',PATROL_PROMPT)


def task_system(task='incident'):
    """Return the fixed model-only system message; incident has no system message."""
    task_prompt(task)
    return (None,None) if task=='incident' else ('PATROL_SYSTEM',PATROL_SYSTEM)


def strict_json(text):
    """Reject duplicate keys and non-JSON constants instead of silently accepting."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('non-JSON numeric constant')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def parse_answer(text):
    if not isinstance(text, str) or len(text) > MAX_RESPONSE:
        raise ValueError('invalid Cosmos answer text')
    text = text.rsplit('</think>', 1)[-1].strip()
    if text.startswith('<answer>') and text.endswith('</answer>'):
        text = text[len('<answer>'):-len('</answer>')].strip()
    fence = re.fullmatch(r'```json\s*(.*?)\s*```', text, flags=re.DOTALL)
    if fence:
        text = fence.group(1)
    value = strict_json(text)
    if not isinstance(value, dict) or set(value) != {'status', 'reason'}:
        raise ValueError('Cosmos answer must match incident schema exactly')
    if not isinstance(value['status'], str) or not isinstance(value['reason'], str) or len(value['reason']) > 2048:
        raise ValueError('incident status and reason must be bounded strings')
    # Reject only whole observed empty-floor claims, never substring/object NLP.
    empty_claim = ' '.join(value['reason'].casefold().split()).rstrip('.!? ')
    if value['status']=='blocked' and empty_claim in ('the floor is clear of any objects','the floor is clear','empty floor'):
        raise ValueError('blocked status contradicts explicit empty-floor reason')
    return Assessment(**value)


def image_mime(image):
    if not isinstance(image, bytes) or not 0 < len(image) <= MAX_IMAGE:
        raise ValueError('image must be nonempty bytes at most 8 MiB')
    if image.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if image.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    raise ValueError('embedded PNG or JPEG required')


def _endpoint(value):
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost')
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path != '/v1/chat/completions'):
        raise ValueError('local HTTP chat-completions endpoint required')
    return parsed


def _timeout(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError('timeout must be positive and finite')
    return value


class CosmosServiceError(Exception):
    """HTTP failure with safe diagnostics and optional server evidence correlation."""
    def __init__(self, status, request_id=None, error='model service request failed'):
        self.status = status
        self.request_id = request_id if (isinstance(request_id, str)
            and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', request_id)) else None
        if not isinstance(error, str) or not error.strip():
            error = 'model service request failed'
        # Never echo HTTPError.url, raw response bodies, or embedded camera URLs.
        error = re.sub(r'(?:[a-zA-Z][a-zA-Z0-9+.-]*://|data:)\S+', '[redacted]', error)
        self.error = ' '.join(error.split())[:512]
        message = f'Cosmos service HTTP {status}: {self.error}'
        if self.request_id is not None:
            message += f' (request_id={self.request_id})'
        super().__init__(message)


def _service_error(response):
    value = {}
    try:
        with response:
            body = response.read(MAX_RESPONSE + 1)
            if len(body) <= MAX_RESPONSE:
                parsed = strict_json(body)
                if isinstance(parsed, dict):
                    value = parsed
    except (ValueError, UnicodeError, OSError):
        # Preserve HTTP status even if its error body is truncated or malformed.
        pass
    return CosmosServiceError(response.code, value.get('id'), value.get('error'))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _request(request, timeout):
    # No environment proxy or HTTP redirect may move camera data off localhost.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=_timeout(timeout)) as response:
            body = response.read(MAX_RESPONSE + 1)
            if len(body) > MAX_RESPONSE:
                raise ValueError('model response exceeds size limit')
    except urllib.error.HTTPError as response:
        raise _service_error(response) from None
    value = strict_json(body)
    if not isinstance(value, dict):
        raise ValueError('model service response must be an object')
    return value


def _identity(value, health=False):
    revision_key = 'revision' if health else 'model_revision'
    if value.get('model') != MODEL or value.get(revision_key) != REVISION:
        raise ValueError('model service identity does not match pinned Cosmos checkpoint')


def _task_identity(value,task,require_prompt=False):
    name,prompt = task_prompt(task)
    if value.get('task','incident') != task:
        raise ValueError('Cosmos service task does not match client task')
    if value.get('prompt_name', 'PROMPT' if task=='incident' else None) != name:
        raise ValueError('Cosmos service prompt name does not match client task')
    import hashlib
    expected=hashlib.sha256(prompt.encode()).hexdigest()
    if (require_prompt or 'prompt_sha256' in value or task=='patrol') and value.get('prompt_sha256') != expected:
        raise ValueError('Cosmos service prompt does not match selected client task')
    system_name,system_text=task_system(task)
    system_hash=hashlib.sha256(system_text.encode()).hexdigest() if system_text is not None else None
    if value.get('system_prompt_name')!=system_name or value.get('system_prompt_sha256')!=system_hash:
        raise ValueError('Cosmos service system prompt identity does not match selected client task')


def health_check(endpoint=ENDPOINT, timeout=5, task='incident'):
    """Return current ready identity; errors and checkpoint mismatch raise."""
    name,prompt = task_prompt(task)
    parsed = _endpoint(endpoint)
    value = _request(urllib.request.Request(urllib.parse.urlunsplit(parsed._replace(path='/health'))), timeout)
    _identity(value, health=True)
    if value.get('status') != 'ready':
        raise ValueError('Cosmos service is not ready')
    _task_identity(value,task,require_prompt=True)
    return value


class CosmosClient:
    def __init__(self, endpoint=ENDPOINT, timeout=90, task='incident'):
        _endpoint(endpoint)
        _timeout(timeout)
        self.prompt_name,self.prompt = task_prompt(task)
        self.endpoint, self.timeout, self.task = endpoint, timeout, task
        self.last_metadata = None

    def health_check(self, timeout=5):
        return health_check(self.endpoint, timeout, task=self.task)

    def assessment(self, image: bytes) -> Assessment:
        self.last_metadata = None
        mime = image_mime(image)
        payload = {'model':MODEL, 'max_tokens':MAX_TOKENS, 'temperature':0,
                   'messages':[{'role':'user','content':[
                       {'type':'image_url','image_url':{'url':f'data:{mime};base64,'+base64.b64encode(image).decode('ascii')}},
                       {'type':'text','text':self.prompt}]}]}
        request = urllib.request.Request(self.endpoint, data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
        value = _request(request, self.timeout)
        _identity(value)
        _task_identity(value,self.task)
        try:
            choices = value['choices']
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError('exactly one model choice required')
            message = choices[0]['message']
            if message.get('role') != 'assistant':
                raise ValueError('assistant message required')
            result = parse_answer(message['content'])
        except (KeyError, TypeError, AttributeError, IndexError) as error:
            raise ValueError('invalid model service answer envelope') from error
        self.last_metadata = {key:value.get(key) for key in ('id','model','model_revision','latency_s','task','prompt_name','prompt_sha256','system_prompt_name','system_prompt_sha256')}
        return result


def assessment(image: bytes, endpoint=ENDPOINT, timeout=90, task='incident') -> Assessment:
    """Assess one camera frame. Failures raise; no fallback to clear."""
    return CosmosClient(endpoint, timeout, task=task).assessment(image)
