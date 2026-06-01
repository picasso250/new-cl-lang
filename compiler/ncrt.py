"""Build helpers for the shared NC C runtime."""

import os
import hashlib
import shutil
import subprocess
import tempfile
import uuid

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
RUNTIME_DIR = os.path.join(ROOT_DIR, "runtime")
NCRT_C = os.path.join(RUNTIME_DIR, "ncrt.c")
NCRT_H = os.path.join(RUNTIME_DIR, "ncrt.h")
NCRT_CACHE_DIR = os.path.join(tempfile.gettempdir(), "nc-ncrt-cache")
SUPPORT_CACHE_DIR = os.path.join(tempfile.gettempdir(), "nc-support-c-cache")
_NCRT_CACHE: dict[str, str] = {}
_SUPPORT_CACHE: dict[str, str] = {}


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
        tmp_path = os.path.join(NCRT_CACHE_DIR, f"ncrt-{key}.{os.getpid()}.{uuid.uuid4().hex}.tmp.obj")
        result = subprocess.run(
            ["gcc", "-c", NCRT_C, "-o", tmp_path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise RuntimeError(f"ncrt compilation failed:\n{result.stderr}")
        if os.path.exists(obj_path):
            os.remove(tmp_path)
        else:
            os.replace(tmp_path, obj_path)
    _NCRT_CACHE[key] = obj_path
    return obj_path


def build_ncrt_obj(out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    obj_path = os.path.join(out_dir, "ncrt.obj")
    shutil.copyfile(_cached_ncrt_obj(), obj_path)
    return obj_path


def _support_cache_key(label: str, c_path: str, include_dirs: list[str]) -> str:
    digest = hashlib.sha256()
    digest.update(label.encode("utf-8"))
    cmd = ["gcc", "-c", os.path.abspath(c_path), *[f"-I{os.path.abspath(d)}" for d in include_dirs]]
    digest.update("\0".join(cmd).encode("utf-8"))
    paths = [os.path.abspath(c_path), NCRT_H]
    c_dir = os.path.dirname(os.path.abspath(c_path))
    paths.extend(
        os.path.join(c_dir, name)
        for name in sorted(os.listdir(c_dir))
        if name.endswith(".h")
    )
    for path in paths:
        digest.update(os.path.abspath(path).encode("utf-8"))
        with open(path, "rb") as f:
            digest.update(f.read())
    return digest.hexdigest()


def _cached_c_obj(label: str, c_path: str, include_dirs: list[str]) -> str:
    c_path = os.path.abspath(c_path)
    key = _support_cache_key(label, c_path, include_dirs)
    cached = _SUPPORT_CACHE.get(key)
    if cached and os.path.exists(cached):
        return cached

    os.makedirs(SUPPORT_CACHE_DIR, exist_ok=True)
    obj_path = os.path.join(SUPPORT_CACHE_DIR, f"{label}-{key}.obj")
    if not os.path.exists(obj_path):
        tmp_path = os.path.join(SUPPORT_CACHE_DIR, f"{label}-{key}.{os.getpid()}.{uuid.uuid4().hex}.tmp.obj")
        cmd = ["gcc", "-c", c_path, "-o", tmp_path] + [f"-I{d}" for d in include_dirs]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise RuntimeError(f"{label} support C compilation failed:\n{result.stderr}")
        if os.path.exists(obj_path):
            os.remove(tmp_path)
        else:
            os.replace(tmp_path, obj_path)
    _SUPPORT_CACHE[key] = obj_path
    return obj_path


def build_support_c_objs(out_dir: str, support_c_sources: list[str] | None) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    result = []
    seen: set[str] = set()
    for c_path in support_c_sources or []:
        abs_path = os.path.abspath(c_path)
        if abs_path in seen:
            continue
        seen.add(abs_path)
        label = os.path.splitext(os.path.basename(abs_path))[0]
        include_dirs = [RUNTIME_DIR, os.path.dirname(abs_path)]
        obj_path = os.path.join(out_dir, f"{label}.obj")
        shutil.copyfile(_cached_c_obj(label, abs_path, include_dirs), obj_path)
        result.append(obj_path)
    return result

def copy_ncrt_header(out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    header_path = os.path.join(out_dir, "ncrt.h")
    shutil.copyfile(NCRT_H, header_path)
    return header_path
