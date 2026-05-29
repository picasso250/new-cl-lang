"""Build helpers for the shared NC C runtime."""

import os
import hashlib
import shutil
import subprocess
import tempfile

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
RUNTIME_DIR = os.path.join(ROOT_DIR, "runtime")
NCRT_C = os.path.join(RUNTIME_DIR, "ncrt.c")
NCRT_H = os.path.join(RUNTIME_DIR, "ncrt.h")
NCRT_CACHE_DIR = os.path.join(tempfile.gettempdir(), "nc-ncrt-cache")
_NCRT_CACHE: dict[str, str] = {}


def _ncrt_cache_key() -> str:
    digest = hashlib.sha256()
    for path in (NCRT_C, NCRT_H):
        with open(path, "rb") as f:
            digest.update(f.read())
    return digest.hexdigest()


def _cached_ncrt_obj() -> str:
    key = _ncrt_cache_key()
    cached = _NCRT_CACHE.get(key)
    if cached and os.path.exists(cached):
        return cached

    os.makedirs(NCRT_CACHE_DIR, exist_ok=True)
    obj_path = os.path.join(NCRT_CACHE_DIR, f"ncrt-{key}.obj")
    if not os.path.exists(obj_path):
        tmp_path = os.path.join(NCRT_CACHE_DIR, f"ncrt-{key}.tmp.obj")
        result = subprocess.run(
            ["gcc", "-c", NCRT_C, "-o", tmp_path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise RuntimeError(f"ncrt compilation failed:\n{result.stderr}")
        os.replace(tmp_path, obj_path)
    _NCRT_CACHE[key] = obj_path
    return obj_path


def build_ncrt_obj(out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    obj_path = os.path.join(out_dir, "ncrt.obj")
    shutil.copyfile(_cached_ncrt_obj(), obj_path)
    return obj_path


def copy_ncrt_header(out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    header_path = os.path.join(out_dir, "ncrt.h")
    shutil.copyfile(NCRT_H, header_path)
    return header_path
