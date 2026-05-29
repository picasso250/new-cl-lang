"""Build helpers for the shared NC C runtime."""

import os
import shutil
import subprocess

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
RUNTIME_DIR = os.path.join(ROOT_DIR, "runtime")
NCRT_C = os.path.join(RUNTIME_DIR, "ncrt.c")
NCRT_H = os.path.join(RUNTIME_DIR, "ncrt.h")


def build_ncrt_obj(out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    obj_path = os.path.join(out_dir, "ncrt.obj")
    result = subprocess.run(
        ["gcc", "-c", NCRT_C, "-o", obj_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ncrt compilation failed:\n{result.stderr}")
    return obj_path


def copy_ncrt_header(out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    header_path = os.path.join(out_dir, "ncrt.h")
    shutil.copyfile(NCRT_H, header_path)
    return header_path
