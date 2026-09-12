"""Unit tests for cuda_build_cache — no GPU or real compilation required.

Compilation and toolchain probes are stubbed; subprocess tests monkeypatch
cuda_build_cache inside the child to keep them hermetic.
"""

import contextlib
import fcntl
import io
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import cuda_build_cache as cbc

CPP = "void push();"
CU = "__global__ void k() {}"
FLAGS = ["-O3", "--use_fast_math"]
KEY = "deadbeefdeadbeefdeadbeef"
NAME = f"cusp_push_{KEY}"
TOOLCHAIN = {
    "cxx": {"command": "c++", "path": "/usr/bin/c++", "version": "g++ 13"},
    "nvcc": {"command": "/usr/local/cuda/bin/nvcc", "path": "/usr/local/cuda/bin/nvcc",
             "version": "12.9"},
    "cuda_home": "/usr/local/cuda",
}


def key(**over):
    kw = {"cpp_source": CPP, "cuda_source": CU, "extra_cuda_cflags": FLAGS,
          "toolchain": {k: (dict(v) if isinstance(v, dict) else v) for k, v in TOOLCHAIN.items()},
          "arch": "explicit:10.0"}
    kw.update(over)
    return cbc.fingerprint(**kw)


def _toolchain(**over):
    t = {k: (dict(v) if isinstance(v, dict) else v) for k, v in TOOLCHAIN.items()}
    for field, value in over.items():
        comp, _, sub = field.partition(".")
        if sub:
            t[comp][sub] = value
        else:
            t[comp] = value
    return t


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
        for change in [dict(**{"cxx.command": "g++"}), dict(**{"cxx.version": "g++ 14"}),
                       dict(**{"cxx.path": "/opt/gcc14/bin/g++"}),
                       dict(**{"nvcc.command": "/opt/cuda/bin/nvcc"}),
                       dict(**{"nvcc.path": "/opt/cuda/bin/nvcc"}),
                       dict(**{"nvcc.version": "13.0"}), {"cuda_home": "/opt/cuda"}]:
            self.assertNotEqual(base, key(toolchain=_toolchain(**change)), change)

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

    def test_compile_env_and_path_sensitivity(self):
        base = key()
        with mock.patch.dict(os.environ, {"NVCC_APPEND_FLAGS": "-Xptxas -v"}):
            self.assertNotEqual(base, key())
        with mock.patch.dict(os.environ, {"CXX": "clang++"}):
            self.assertNotEqual(base, key())
        # PATH is key material: a different PATH ordering changes the key
        with mock.patch.dict(os.environ, {"PATH": "/opt/other:" + os.environ["PATH"]}):
            self.assertNotEqual(base, key())

    def test_resolved_path_via_shutil_which(self):
        # The realpath the compiler command resolves to is recorded, not just argv[0]
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "mycxx"
            fake.write_text("#!/bin/sh\n")
            fake.chmod(0o755)
            with mock.patch.dict(os.environ, {"PATH": td + ":" + os.environ["PATH"]}):
                self.assertEqual(cbc._resolve_executable("mycxx -foo"), str(fake.resolve()))
            with self.assertRaises(RuntimeError):
                cbc._resolve_executable("definitely-not-a-compiler-xyz")

    def test_device_index_not_in_key(self):
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


_REPO = str(Path(__file__).resolve().parent.parent / "src")
_CHILD = textwrap.dedent(
    """
    import os, sys, types, pathlib, fcntl
    sys.path.insert(0, {repo!r})
    import cuda_build_cache as cbc
    cbc.fingerprint = lambda *a, **k: {key!r}
    {patch}
    cbc.load_cached_extension("cpp", "cu", 0, ["-O3"])
    """
).replace("{repo!r}", repr(_REPO)).replace("{key!r}", repr(KEY))


def _fake_load_inline_body(td):
    """Fake torch load_inline: writes <name>.so so classification sees a real artifact."""
    return textwrap.dedent(
        """
        def fake(**kw):
            so = pathlib.Path(kw["build_directory"]) / (kw["name"] + ".so")
            so.touch()
            m = types.ModuleType(kw["name"]); m.__file__ = str(so)
            return m
        cbc.load_inline = fake
        """
    )


def _run_child(tmpdir, patch, env_extra=None):
    env = dict(os.environ, CUSP_BUILD_DIR=tmpdir)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(  # noqa: PLW1510 - rc asserted by callers
        [sys.executable, "-c", _CHILD.format(patch=patch)],
        env=env, capture_output=True, text=True, timeout=120,
    )


def _patch_module(td, **fake_kw):
    """In-process load_cached_extension with stubbed fingerprint/load_inline."""
    def fake(**kw):
        fake_kw.update(kw)
        so = Path(kw["build_directory"]) / (kw["name"] + ".so")
        if not so.exists():
            so.touch()
        m = types.ModuleType(kw["name"])
        m.__file__ = str(so)
        return m
    return mock.patch.object(cbc, "fingerprint", return_value=KEY), \
        mock.patch.object(cbc, "load_inline", side_effect=fake), \
        mock.patch.dict(os.environ, {"CUSP_BUILD_DIR": td})


class LoadCachedExtensionTests(unittest.TestCase):
    def test_same_key_shared_dir_and_device_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            fp, li, env = _patch_module(td)
            with fp, li, env:
                m0 = cbc.load_cached_extension(CPP, CU, 0, FLAGS)
                m7 = cbc.load_cached_extension(CPP, CU, 7, FLAGS)
            self.assertEqual(m0.__name__, NAME)
            self.assertEqual(m7.__name__, NAME)
            self.assertTrue((Path(td) / NAME / f"{NAME}.so").exists())

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
                    m = types.ModuleType(kw["name"]); m.__file__ = str(so)
                    return m
                cbc.load_inline = fake
                """
            )
            procs = [subprocess.Popen(
                [sys.executable, "-c", _CHILD.format(patch=patch)],
                env=dict(os.environ, CUSP_BUILD_DIR=td),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                for _ in range(2)]
            for p in procs:
                _out, err = p.communicate(timeout=120)
                self.assertEqual(p.returncode, 0, err)
            self.assertEqual(counter.read_text(), "1")

    def test_stale_torch_lock_after_holder_death(self):
        with tempfile.TemporaryDirectory() as td:
            keydir = Path(td) / NAME
            keydir.mkdir(parents=True)
            ready = Path(td) / "holder-ready"
            # Child acquires the outer flock, leaves the torch FileBaton 'lock'
            # file behind, signals readiness, then blocks until killed.
            holder = textwrap.dedent(
                f"""
                import fcntl, os, pathlib, time
                fd = os.open({str(keydir / 'build.flock')!r}, os.O_CREAT | os.O_RDWR)
                fcntl.flock(fd, fcntl.LOCK_EX)
                pathlib.Path({str(keydir / 'lock')!r}).touch()
                pathlib.Path({str(ready)!r}).touch()
                time.sleep(60)
                """
            )
            proc = subprocess.Popen([sys.executable, "-c", holder])
            try:
                for _ in range(300):
                    if ready.exists():
                        break
                    time.sleep(0.02)
                self.assertTrue(ready.exists(), "holder never signalled")
                # Outer lock is genuinely held: nonblocking acquire must fail.
                fd = os.open(keydir / "build.flock", os.O_RDWR)
                try:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    os.close(fd)
            finally:
                proc.kill()
                proc.wait(timeout=30)
            # Kernel released the flock on death; only the stale 'lock' remains.
            self.assertTrue((keydir / "lock").exists())
            r = _run_child(td, _fake_load_inline_body(td))
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
            flock_path = Path(td) / NAME / "build.flock"
            fd = os.open(flock_path, os.O_RDWR)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # raises if still held
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def test_outcome_classification(self):
        with tempfile.TemporaryDirectory() as td:
            keydir = Path(td) / NAME
            so = keydir / f"{NAME}.so"
            keydir.mkdir()
            # cold-build: no artifact beforehand, fake creates it
            fp, li, env = _patch_module(td)
            out = io.StringIO()
            with fp, li, env, contextlib.redirect_stdout(out):
                cbc.load_cached_extension(CPP, CU, 0, FLAGS)
            self.assertIn("cold-build", out.getvalue())
            self.assertIn(f"key={KEY}", out.getvalue())
            # cache-hit: artifact stat unchanged after a no-op "rebuild"
            out = io.StringIO()
            fp, li, env = _patch_module(td)
            with fp, li, env, contextlib.redirect_stdout(out):
                cbc.load_cached_extension(CPP, CU, 0, FLAGS)
            self.assertIn("cache-hit", out.getvalue())
            # rebuilt: artifact content changes during the call
            def rebuild(**kw):
                so.write_bytes(b"new")  # different size/mtime
                m = types.ModuleType(kw["name"]); m.__file__ = str(so)
                return m
            out = io.StringIO()
            fp, _li, env = _patch_module(td)
            with fp, mock.patch.object(cbc, "load_inline", side_effect=rebuild), env, \
                    contextlib.redirect_stdout(out):
                cbc.load_cached_extension(CPP, CU, 0, FLAGS)
            self.assertIn("rebuilt", out.getvalue())

    def test_invalid_module_raises(self):
        with tempfile.TemporaryDirectory() as td:
            fp, _li, env = _patch_module(td)
            bad = types.ModuleType("m")  # __file__ is None
            with fp, mock.patch.object(cbc, "load_inline", return_value=bad), env, \
                    self.assertRaises(RuntimeError):
                cbc.load_cached_extension(CPP, CU, 0, FLAGS)

    def test_verbose_flag_passthrough(self):
        with tempfile.TemporaryDirectory() as td:
            seen = []

            def fake(**kw):
                seen.append(kw["verbose"])
                so = Path(kw["build_directory"]) / (kw["name"] + ".so")
                so.touch()
                m = types.ModuleType(kw["name"]); m.__file__ = str(so)
                return m
            fp, _li, _env = _patch_module(td)
            env_m = mock.patch.dict(os.environ, {"CUSP_BUILD_DIR": td, "CUSP_BUILD_VERBOSE": "1"})
            with fp, mock.patch.object(cbc, "load_inline", side_effect=fake), env_m:
                cbc.load_cached_extension(CPP, CU, 0, FLAGS)
            self.assertEqual(seen, [True])


if __name__ == "__main__":
    unittest.main()
