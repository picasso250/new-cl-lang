"""项目级测试：目录即同模块，多文件自动互见。"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def run_nc(*args, cwd=ROOT):
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "nc.py"), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_multifile_function_run():
    result = run_nc("run", os.path.join("test_cases", "project_095_multifile"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "5"


def test_multifile_struct_run():
    result = run_nc("run", os.path.join("test_cases", "project_096_multifile_struct"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "7"


def test_build_outputs_generated_c_and_exe():
    with tempfile.TemporaryDirectory() as tmp:
        project = os.path.join(ROOT, "test_cases", "project_095_multifile")
        build = run_nc("build", project, cwd=tmp)
        assert build.returncode == 0, build.stderr
        c_path = os.path.join(tmp, "build", "main.c")
        exe_path = os.path.join(tmp, "build", "main.exe")
        assert os.path.exists(c_path)
        assert os.path.exists(exe_path)
