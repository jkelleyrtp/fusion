"""Unit tests for cuda_build_cache — no GPU or real compilation required.

Compilation and toolchain probes are stubbed; subprocess tests monkeypatch
cuda_build_cache inside the child to keep them hermetic.
"""

import fcntl
import os
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cuda_build_cache as cbc

CPP = "void push();"
CU = "__global__ void k() {}"
FLAGS = ["-O3", "--use_fast_math"]
TOOLCHAIN = {"cxx": "c++", "cxx_version": "g++ 13", "nvcc": "/usr/local/cuda/bin/nvcc",
             "nvcc_version": "12.9", "cuda_home": "/usr/local/cuda"}


def key(**over):
    kw = {"cpp_source": CPP, "cuda_source": CU, "extra_cuda_cflags": FLAGS,
          "toolchain": dict(TOOLCHAIN), "arch": "explicit:10.0"}
    kw.update(over)
    return cbc.fingerprint(**kw)


class FingerprintTests(unittest.TestCase):
    def test_identical_inputs_same_key(self):
        self.assertEqual(key(), key())
        self.assertEqual(len(key()), 24)
        int(key(), 16)  # valid hex

    def test_source_and_flag_sensitivity(self):
        base = key()
        self.assertNotEqual(base, key(cpp_source=CPP + "//x"))
        self.assertNotEqual(base, key(cuda_source=CU + "//x"))
        self.assertNotEqual(base, key(extra_cuda_cflags=FLAGS + ["-lineinfo"]))
        self.assertNotEqual(base, key(extra_cuda_cflags=["-O2", "--use_fast_math"]))

    def test_toolchain_sensitivity(self):
        base = key()
        for field, value in [("cxx", "g++"), ("cxx_version", "g++ 14"),
                             ("nvcc", "/opt/cuda/bin/nvcc"), ("nvcc_version", "13.0"),
                             ("cuda_home", "/opt/cuda")]:
            t = dict(TOOLCHAIN, **{field: value})
            self.assertNotEqual(base, key(toolchain=t), field)

    def test_arch_sensitivity(self):
        base = key()
        self.assertNotEqual(base, key(arch="explicit:9.0"))
        self.assertNotEqual(base, key(arch="auto:10.0|sm_100"))

    def test_platform_python_torch_sensitivity(self):
        base = key()
        with mock.patch.object(cbc.platform, "machine", return_value="aarch64"):
            self.assertNotEqual(base, key())
        with mock.patch.object(cbc.sysconfig, "get_config_var", return_value="cpython-313"):
            self.assertNotEqual(base, key())
        with mock.patch.object(cbc.torch, "__version__", "2.12.0"):
            self.assertNotEqual(base, key())
        with mock.patch.object(cbc.torch.version, "cuda", "13.0"):
            self.assertNotEqual(base, key())

    def test_compile_env_sensitivity(self):
        base = key()
        with mock.patch.dict(os.environ, {"NVCC_APPEND_FLAGS": "-Xptxas -v"}):
            self.assertNotEqual(base, key())
        with mock.patch.dict(os.environ, {"CXX": "clang++"}):
            self.assertNotEqual(base, key())

    def test_device_index_not_in_key(self):
        # identical GPUs with different ordinals share one key
        self.assertEqual(key(arch="auto:10.0,10.0|sm_100"),
                         key(arch="auto:10.0,10.0|sm_100"))


class CacheRootTests(unittest.TestCase):
    def test_explicit_root(self):
        with mock.patch.dict(os.environ, {"CUSP_BUILD_DIR": "/x/cache"}):
            self.assertEqual(cbc.cache_root(), Path("/x/cache"))

    def test_default_root(self):
        env = dict(os.environ)
        env.pop("CUSP_BUILD_DIR", None)
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(cbc.cache_root(), Path.home() / ".cache" / "cusp_build")


_CHILD = textwrap.dedent(
    """
    import os, sys, types, pathlib, fcntl
    sys.path.insert(0, {repo!r})
    import cuda_build_cache as cbc
    cbc.fingerprint = lambda *a, **k: "deadbeefdeadbeefdeadbeef"
    {patch}
    cbc.load_cached_extension("cpp", "cu", 0, ["-O3"])
    """
)


def _run_child(tmpdir, patch, env_extra=None):
    env = dict(os.environ, CUSP_BUILD_DIR=tmpdir)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(  # noqa: PLW1510 - rc asserted by callers
        [sys.executable, "-c", _CHILD.format(repo=str(Path(__file__).resolve().parent.parent), patch=patch)],
        env=env, capture_output=True, text=True, timeout=120,
    )


class LoadCachedExtensionTests(unittest.TestCase):
    def test_same_key_shared_dir_and_device_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            calls = []

            def fake(**kw):
                calls.append(kw["name"])
                m = types.ModuleType(kw["name"])
                return m

            with mock.patch.object(cbc, "fingerprint", return_value="deadbeefdeadbeefdeadbeef"), \
                 mock.patch.object(cbc, "load_inline", side_effect=fake), \
                 mock.patch.dict(os.environ, {"CUSP_BUILD_DIR": td}):
                m0 = cbc.load_cached_extension(CPP, CU, 0, FLAGS)
                m7 = cbc.load_cached_extension(CPP, CU, 7, FLAGS)
            self.assertEqual(calls, ["cusp_push_deadbeefdeadbeefdeadbeef"] * 2)
            self.assertEqual(m0.__name__, m7.__name__)
            self.assertTrue((Path(td) / "cusp_push_deadbeefdeadbeefdeadbeef").is_dir())

    def test_concurrent_processes_compile_once(self):
        with tempfile.TemporaryDirectory() as td:
            counter = Path(td) / "compiles"
            patch = textwrap.dedent(
                f"""
                import time
                def fake(**kw):
                    # emulate torch/ninja: a completed artifact makes later loads no-ops
                    so = pathlib.Path(kw["build_directory"]) / (kw["name"] + ".so")
                    if not so.exists():
                        p = pathlib.Path({str(counter)!r})
                        n = int(p.read_text() or "0") if p.exists() else 0
                        p.write_text(str(n + 1))
                        time.sleep(0.5)  # widen the race window
                        so.touch()
                    return types.ModuleType(kw["name"])
                cbc.load_inline = fake
                """
            )
            procs = [subprocess.Popen(
                [sys.executable, "-c",
                 _CHILD.format(repo=str(Path(__file__).resolve().parent.parent), patch=patch)],
                env=dict(os.environ, CUSP_BUILD_DIR=td),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                for _ in range(2)]
            for p in procs:
                _out, err = p.communicate(timeout=120)
                self.assertEqual(p.returncode, 0, err)
            self.assertEqual(counter.read_text(), "1")

    def test_stale_torch_lock_after_holder_death(self):
        with tempfile.TemporaryDirectory() as td:
            keydir = Path(td) / "cusp_push_deadbeefdeadbeefdeadbeef"
            keydir.mkdir(parents=True)
            # A killed builder leaves the FileBaton 'lock' file behind; flock is
            # kernel-released on death, so only the stale baton remains.
            (keydir / "lock").touch()
            patch = "cbc.load_inline = lambda **kw: types.ModuleType(kw['name'])"
            r = _run_child(td, patch)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse((keydir / "lock").exists(), "stale baton not removed")

    def test_build_failure_releases_lock_and_propagates(self):
        with tempfile.TemporaryDirectory() as td:
            patch = textwrap.dedent(
                """
                def fake(**kw):
                    raise RuntimeError("nvcc exploded")
                cbc.load_inline = fake
                """
            )
            r = _run_child(td, patch)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("nvcc exploded", r.stderr)
            flock_path = Path(td) / "cusp_push_deadbeefdeadbeefdeadbeef" / "build.flock"
            fd = os.open(flock_path, os.O_RDWR)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # raises if still held
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def test_verbose_flag_passthrough(self):
        with tempfile.TemporaryDirectory() as td:
            seen = []
            with mock.patch.object(cbc, "fingerprint", return_value="deadbeefdeadbeefdeadbeef"), \
                 mock.patch.object(cbc, "load_inline", side_effect=lambda **kw: seen.append(kw["verbose"]) or types.ModuleType("m")), \
                 mock.patch.dict(os.environ, {"CUSP_BUILD_DIR": td, "CUSP_BUILD_VERBOSE": "1"}):
                cbc.load_cached_extension(CPP, CU, 0, FLAGS)
            self.assertEqual(seen, [True])


if __name__ == "__main__":
    unittest.main()
