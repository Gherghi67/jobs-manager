"""Conversations with Claude Code on this computer, for the app's Claude page.

Each message runs `claude -p` in the chat's folder and resumes the chat's Claude Code session, with the
user's own settings, CLAUDE.md files, hooks and MCP servers. Permissions use auto mode, as at the desk:
the classifier blocks risky actions, and anything that would wait for a prompt is denied."""
from __future__ import annotations
import base64
import copy
import datetime as dt
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import threading

import ai_pick as ai

ROOT = Path(__file__).resolve().parent
CHATS_FILE = Path(os.environ.get('JOBS_CHATS_FILE') or ROOT / 'chats.json')
MODEL = os.environ.get('JOBS_CHAT_MODEL') or 'claude-opus-5-5'
EFFORT = os.environ.get('JOBS_CHAT_EFFORT') or 'xhigh'
TURN_TIMEOUT = 30 * 60
MAX_RUNNING = 3
PROMPT_CHARS = 20000
TEXT_CHARS = 60000
TOOL_CHARS = 300
ITEMS_PER_TURN = 400
MAX_IMAGES = 5
# Claude takes images up to 5 MB once base64-encoded; the app shrinks photos well below that.
IMAGE_BYTES = 3_750_000
# A message with its text and every image, base64-encoded in JSON.
REQUEST_BYTES = PROMPT_CHARS * 6 + MAX_IMAGES * (IMAGE_BYTES * 4 // 3 + 64) + 4096
IMAGE_TYPES = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/gif': 'gif', 'image/webp': 'webp'}
IMAGE_NAME = re.compile(r'\d+-\d+\.(jpg|png|gif|webp)')
PHONE = ('The user is writing from the Fieldwork app on their phone, through their job service on this computer. '
         'They cannot see the terminal or answer permission prompts or questions from tools: ask in your reply instead. '
         'Keep replies short and readable on a small screen.')


class ChatError(Exception):
    pass


def enabled():
    return os.environ.get('JOBS_CLAUDE_CHAT', 'on').lower() not in ('off', '0', 'false', 'no')


def roots():
    configured = os.environ.get('JOBS_CLAUDE_ROOTS')
    paths = configured.split(os.pathsep) if configured else [str(Path.home() / 'Documents')]
    return [Path(p).expanduser().resolve() for p in paths if p.strip()]


def folders():
    """The folders a chat can work in: each root, then its visible subfolders."""
    found = []
    for root in roots():
        if not root.is_dir():
            continue
        found.append(root)
        try:
            found += sorted((p for p in root.iterdir() if p.is_dir() and not p.name.startswith('.')),
                            key=lambda p: p.name.lower())
        except OSError:
            pass
    rows = [dict(name=p.name or str(p), path=str(p)) for p in dict.fromkeys(found)]
    return rows


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def clip(text, limit):
    text = str(text or '')
    return text if len(text) <= limit else text[:limit - 1] + '…'


def image_type(data):
    """The media type from the file's first bytes, so a mislabelled upload can't pass as an image."""
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return None


def decode_images(images):
    """The app sends each image as base64; returns (bytes, media type) pairs."""
    if images is None:
        return []
    if not isinstance(images, list) or len(images) > MAX_IMAGES:
        raise ValueError(f'Send up to {MAX_IMAGES} images at a time.')
    decoded = []
    for image in images:
        if not isinstance(image, str):
            raise ValueError('An image could not be read.')
        if len(image) > IMAGE_BYTES * 4 // 3 + 4:
            raise ValueError(f'Images are limited to {IMAGE_BYTES / 1e6:.1f} MB each.')
        try:
            data = base64.b64decode(image, validate=True)
        except ValueError:
            raise ValueError('An image could not be read.')
        kind = image_type(data)
        if not kind:
            raise ValueError('Send images as JPEG, PNG, GIF or WebP.')
        decoded.append((data, kind))
    return decoded


def user_message(text, images):
    """One stream-json message: the text, then each image, as when pasting images into Claude Code.

    The text names each saved copy, so Claude can also move or attach the file."""
    paths = '\n'.join(f'[Image {n}: {path}]' for n, (path, _, _) in enumerate(images, 1))
    content = [dict(type='text', text='\n\n'.join(t for t in (text, paths) if t))]
    for _, kind, data in images:
        content.append(dict(type='image', source=dict(type='base64', media_type=kind,
                                                      data=base64.b64encode(data).decode())))
    return json.dumps(dict(type='user', message=dict(role='user', content=content))) + '\n'


def tool_summary(name, value):
    """One line for a tool call: what it does, not its whole input."""
    value = value if isinstance(value, dict) else {}
    for key in ('description', 'command', 'file_path', 'path', 'pattern', 'url', 'query', 'prompt', 'skill'):
        if isinstance(value.get(key), str) and value[key].strip():
            return clip(' '.join(value[key].split()), TOOL_CHARS)
    return ''


def apply(turn, event):
    """Folds one stream-json event from Claude Code into a turn. Returns the session id when the event has one."""
    kind = event.get('type')
    items = turn['items']
    if kind == 'stream_event':
        delta = (event.get('event') or {}).get('delta') or {}
        if delta.get('type') == 'text_delta' and not event.get('parent_tool_use_id'):
            if items and items[-1]['kind'] == 'text' and items[-1].get('live'):
                items[-1]['text'] = clip(items[-1]['text'] + str(delta.get('text', '')), TEXT_CHARS)
            elif len(items) < ITEMS_PER_TURN:
                items.append(dict(kind='text', text=clip(delta.get('text', ''), TEXT_CHARS), live=True))
    elif kind == 'assistant' and not event.get('parent_tool_use_id'):
        for block in (event.get('message') or {}).get('content') or []:
            if not isinstance(block, dict):
                continue
            if block.get('type') == 'text':
                if items and items[-1]['kind'] == 'text' and items[-1].get('live'):
                    # The finished block replaces the text streamed so far.
                    items[-1].update(text=clip(block.get('text', ''), TEXT_CHARS), live=False)
                elif len(items) < ITEMS_PER_TURN:
                    items.append(dict(kind='text', text=clip(block.get('text', ''), TEXT_CHARS)))
            elif block.get('type') == 'tool_use' and len(items) < ITEMS_PER_TURN:
                items.append(dict(kind='tool', name=clip(block.get('name', 'Tool'), 80),
                                  text=tool_summary(block.get('name'), block.get('input'))))
    elif kind == 'rate_limit_event':
        info = event.get('rate_limit_info') or {}
        if info.get('status') and info['status'] != 'allowed':
            turn['limit'] = dict(status=str(info['status']), kind=str(info.get('rateLimitType', '')),
                                 used=info.get('utilization'), resets_at=info.get('resetsAt'))
    elif kind == 'system' and event.get('subtype') == 'init':
        turn['model'] = str(event.get('model') or '')
    elif kind == 'result':
        for denial in event.get('permission_denials') or []:
            if isinstance(denial, dict) and len(items) < ITEMS_PER_TURN:
                items.append(dict(kind='blocked', name=clip(denial.get('tool_name', 'Tool'), 80),
                                  text=tool_summary(denial.get('tool_name'), denial.get('tool_input'))))
        if event.get('is_error'):
            turn['status'] = 'error'
            turn['error'] = clip(' '.join(str(event.get('result') or event.get('subtype') or 'Claude Code failed.').split()), 500)
        else:
            turn['status'] = 'done'
            if not any(i['kind'] == 'text' for i in items) and event.get('result'):
                items.append(dict(kind='text', text=clip(event['result'], TEXT_CHARS)))
        if isinstance(event.get('duration_ms'), int):
            turn['duration_ms'] = event['duration_ms']
    session = event.get('session_id')
    return session if isinstance(session, str) and session else None


def command(session_id):
    cmd = ['claude', '-p', '--input-format', 'stream-json', '--output-format', 'stream-json', '--verbose',
           '--include-partial-messages', '--permission-mode', 'auto', '--permission-prompts', 'none',
           '--model', MODEL, '--effort', EFFORT, '--append-system-prompt', PHONE]
    if session_id:
        cmd += ['--resume', session_id]
    return cmd


def summary(chat):
    last = chat['turns'][-1] if chat['turns'] else None
    return dict(id=chat['id'], title=chat['title'], cwd=chat['cwd'], folder=Path(chat['cwd']).name or chat['cwd'],
                created_at=chat['created_at'], updated_at=chat['updated_at'], turn_count=len(chat['turns']),
                running=bool(last and last['status'] == 'running'))


class ChatStore:
    def __init__(self, path=CHATS_FILE, popen=subprocess.Popen):
        self.path = Path(path)
        # Uploaded images, one folder per chat, beside the chats file.
        self.images = self.path.with_name('chat-images')
        self.popen = popen
        self.lock = threading.RLock()
        self.chats = None
        self.procs = {}

    def load(self):
        if self.chats is None:
            try:
                rows = json.loads(self.path.read_text())['chats']
            except FileNotFoundError:
                rows = []
            except (OSError, ValueError, KeyError, TypeError):
                raise ChatError(f'{self.path.name} on the service could not be read.')
            self.chats = {c['id']: c for c in rows if isinstance(c, dict) and isinstance(c.get('id'), str)}
            for chat in self.chats.values():
                for turn in chat['turns']:
                    # The service stopped while these ran.
                    if turn['status'] == 'running':
                        turn['status'] = 'interrupted'
                        for item in turn['items']:
                            item.pop('live', None)
        return self.chats

    def save(self):
        temp = self.path.with_name(self.path.name + '.tmp')
        with os.fdopen(os.open(temp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600), 'w') as f:
            json.dump({'chats': list(self.load().values())}, f, indent=1)
        os.replace(temp, self.path)

    def list(self):
        with self.lock:
            return sorted((summary(c) for c in self.load().values()), key=lambda c: c['updated_at'], reverse=True)

    def get(self, chat_id, start=0):
        """The chat with its turns from [start] on, so the app can poll only the turn that's running."""
        with self.lock:
            chat = self.load().get(chat_id)
            if chat is None:
                return None
            start = max(0, min(start, len(chat['turns'])))
            return dict(summary(chat), start=start, turns=copy.deepcopy(chat['turns'][start:]))

    def create(self, cwd, text, images=None):
        if cwd not in {f['path'] for f in folders()}:
            raise ValueError('Choose one of the folders the service offers.')
        images = decode_images(images)
        self.check_text(text, images)
        with self.lock:
            stamp = now()
            title = text.strip().splitlines()[0] if text.strip() else 'Photo' if len(images) == 1 else f'{len(images)} photos'
            chat = dict(id=secrets.token_hex(8), title=clip(title, 80), cwd=cwd,
                        session_id='', created_at=stamp, updated_at=stamp, turns=[])
            self.check_capacity()
            self.load()[chat['id']] = chat
            try:
                return self.start(chat, text, images)
            except ChatError:
                del self.chats[chat['id']]
                shutil.rmtree(self.images / chat['id'], ignore_errors=True)
                raise

    def send(self, chat_id, text, images=None):
        images = decode_images(images)
        self.check_text(text, images)
        with self.lock:
            chat = self.load().get(chat_id)
            if chat is None:
                return None
            if chat['turns'] and chat['turns'][-1]['status'] == 'running':
                raise RuntimeError('Claude is still answering. Wait, or stop it first.')
            self.check_capacity()
            return self.start(chat, text, images)

    @staticmethod
    def check_text(text, images=()):
        # A photo on its own is a message too.
        if not isinstance(text, str) or not (text.strip() or images):
            raise ValueError('Write a message first.')
        if len(text) > PROMPT_CHARS:
            raise ValueError(f'Messages are limited to {PROMPT_CHARS:,} characters.')

    def check_capacity(self):
        if len(self.procs) >= MAX_RUNNING:
            raise RuntimeError(f'{MAX_RUNNING} chats are already running. Wait for one to finish.')

    def save_images(self, chat, images):
        """Keeps each upload, so the app can show it in the chat and Claude can find it by path."""
        if not images:
            return []
        folder = self.images / chat['id']
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        saved = []
        try:
            for n, (data, kind) in enumerate(images, 1):
                path = folder / f'{len(chat["turns"])}-{n}.{IMAGE_TYPES[kind]}'
                with os.fdopen(os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600), 'wb') as f:
                    f.write(data)
                saved.append((path, kind, data))
        except OSError:
            for path, _, _ in saved:
                path.unlink(missing_ok=True)
            raise ChatError('The images could not be saved on the service computer.')
        return saved

    def image(self, chat_id, name):
        """The path of an image uploaded to a chat, or None."""
        with self.lock:
            if chat_id not in self.load() or not IMAGE_NAME.fullmatch(name):
                return None
        path = self.images / chat_id / name
        return path if path.is_file() else None

    def start(self, chat, text, images=()):
        if not ai.available():
            raise ChatError('Claude Code is not installed on the service computer.')
        if not Path(chat['cwd']).is_dir():
            raise ChatError(f'The folder {chat["cwd"]} no longer exists on the service computer.')
        saved = self.save_images(chat, images)
        turn = dict(prompt=text, at=now(), status='running', items=[])
        if saved:
            turn['images'] = [dict(name=path.name, type=kind) for path, kind, _ in saved]
        chat['turns'].append(turn)
        chat['updated_at'] = turn['at']
        try:
            # A new process group, so Stop also ends the commands Claude started.
            proc = self.popen(command(chat['session_id']), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, cwd=chat['cwd'], env=ai.clean_env(),
                              start_new_session=True)
        except OSError:
            chat['turns'].pop()
            for path, _, _ in saved:
                path.unlink(missing_ok=True)
            raise ChatError('Claude Code could not be started on the service computer.')
        self.procs[chat['id']] = proc
        self.save()
        threading.Thread(target=self.run, args=(chat, turn, proc, user_message(text, saved)), daemon=True).start()
        return self.get(chat['id'], len(chat['turns']) - 1)

    @staticmethod
    def feed(proc, message):
        try:
            proc.stdin.write(message)
            proc.stdin.close()
        except OSError:
            pass

    def run(self, chat, turn, proc, message):
        timer = threading.Timer(TURN_TIMEOUT, self.kill, args=(proc, turn, 'timeout'))
        timer.daemon = True
        timer.start()
        other = []
        try:
            # Images make the message large, so it goes in from another thread while the output is read.
            threading.Thread(target=self.feed, args=(proc, message), daemon=True).start()
            for line in proc.stdout:
                try:
                    event = json.loads(line)
                except ValueError:
                    # Not an event, such as a warning on stderr; the last ones explain a failure.
                    other = (other + [line.strip()])[-5:] if line.strip() else other
                    continue
                if isinstance(event, dict):
                    with self.lock:
                        session = apply(turn, event)
                        if session:
                            chat['session_id'] = session
            proc.wait()
        finally:
            timer.cancel()
            with self.lock:
                if turn['status'] == 'running':
                    turn['status'] = turn.pop('ending', None) or 'error'
                    if turn['status'] == 'error':
                        turn['error'] = clip(' '.join(other) or f'Claude Code stopped without an answer (exit {proc.returncode}).', 500)
                    elif turn['status'] == 'timeout':
                        turn.update(status='error', error='Stopped after 30 minutes.')
                turn.pop('ending', None)
                for item in turn['items']:
                    item.pop('live', None)
                chat['updated_at'] = now()
                self.procs.pop(chat['id'], None)
                if chat['id'] in self.load():
                    self.save()

    def kill(self, proc, turn, reason):
        with self.lock:
            if turn['status'] == 'running':
                turn['ending'] = reason
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (OSError, AttributeError):
            try:
                proc.kill()
            except OSError:
                pass

    def stop(self, chat_id):
        with self.lock:
            chat = self.load().get(chat_id)
            if chat is None:
                return None
            proc = self.procs.get(chat_id)
            if proc and chat['turns'] and chat['turns'][-1]['status'] == 'running':
                self.kill(proc, chat['turns'][-1], 'stopped')
            return self.get(chat_id, max(0, len(chat['turns']) - 1))

    def remove(self, chat_id):
        """Forgets the chat here; Claude Code keeps its own session files."""
        with self.lock:
            chat = self.load().get(chat_id)
            if chat is None:
                return False
            proc = self.procs.get(chat_id)
            if proc and chat['turns']:
                self.kill(proc, chat['turns'][-1], 'stopped')
            del self.load()[chat_id]
            self.save()
            shutil.rmtree(self.images / chat_id, ignore_errors=True)
            return True
