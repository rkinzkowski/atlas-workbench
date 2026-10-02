"""Local provider settings. Windows DPAPI binds saved secrets to this OS user."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import threading

import connectors

ALLOWED = set(connectors.CREDENTIAL_ENVS) | {'OPENAI_MODEL'}


def crypt(data, decrypt=False):
    if os.name != 'nt':
        raise ValueError('Persistent key storage requires Windows. Use session-only settings or environment variables on this system.')
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    library = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    function = library.CryptUnprotectData if decrypt else library.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise ValueError('Windows could not unlock or save the key store for this user.')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


class Settings:
    def __init__(self, directory):
        self.path = Path(directory) / 'credentials.dpapi'
        self.lock = threading.RLock()
        self.saved = {}
        self.error = None
        if self.path.exists():
            try:
                decoded = json.loads(crypt(self.path.read_bytes(), decrypt=True))
                self.saved = {k: v for k, v in decoded.items() if k in ALLOWED and isinstance(v, str)}
                for key, value in self.saved.items():
                    os.environ.setdefault(key, value)
            except Exception:
                self.error = 'Saved keys could not be opened by this Windows user. Re-enter them or use session-only settings.'

    def status(self):
        return {'persistent_storage_available': os.name == 'nt', 'storage_error': self.error,
                'fields': [{'name': k, 'configured': bool(os.environ.get(k)), 'saved': k in self.saved,
                            'secret': k != 'OPENAI_MODEL'} for k in sorted(ALLOWED)],
                'model': os.environ.get('OPENAI_MODEL', '')}

    def update(self, values, remove=None, persist=True):
        remove = [] if remove is None else remove
        if not isinstance(values, dict) or not isinstance(remove, list):
            raise ValueError('Invalid settings request.')
        if set(values) - ALLOWED or set(remove) - ALLOWED:
            raise ValueError('Unknown provider setting.')
        if any(not isinstance(v, str) or len(v) > 16000 or '\x00' in v or '\n' in v or '\r' in v for v in values.values()):
            raise ValueError('Provider settings must be single-line text under 16,000 characters.')
        values = {k: v.strip() for k, v in values.items() if v.strip()}
        with self.lock:
            saved = {k: v for k, v in self.saved.items() if k not in remove}
            # Session-only replacement also removes any older saved value of that key.
            for key in values:
                saved.pop(key, None)
            if persist:
                saved.update(values)
            if persist or saved != self.saved:
                encrypted = crypt(json.dumps(saved).encode())
                temporary = self.path.with_suffix('.tmp')
                temporary.write_bytes(encrypted)
                os.replace(temporary, self.path)
            self.saved = saved
            for key in remove:
                os.environ.pop(key, None)
            os.environ.update(values)
            self.error = None
            return self.status()
