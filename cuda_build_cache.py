"""Persistent, fingerprint-keyed build cache for the fused cusp CUDA kernel.

Workers on different GPUs (or different broker jobs) share one build directory per
fingerprint instead of each compiling under ``/tmp``. The fingerprint covers
everything that changes the compiled artifact: sources, bindings, flags, platform,
Python SOABI, Torch build identity, CUDA toolkit/compiler identity, the compile
environment, and the target architecture request. GPU ordinal is deliberately NOT
part of the key — identical workers share one directory and one extension module.

Locking: GPU-image torch (2.11) uses the existence-based ``FileBaton`` whose
stale ``lock`` file deadlocks later callers forever. All callers here first take a
kernel-released POSIX advisory ``flock`` on ``<keydir>/build.flock`` covering the
whole ``load_inline`` call (source generation included); once it is held, any
leftover ``<keydir>/lock`` is by definition stale and is removed before calling
``load_inline``, which then uses ninja for artifact freshness. This is safe only
because every caller for a ``cusp_push_<key>`` name goes through this module —
never point another ``load_inline`` at the same directory.
"""

import fcntl
import hashlib
import json
import os
import platform
import shlex
import subprocess
import sys
import sysconfig
import types
from pathlib import Path

import torch
from torch.utils.cpp_extension import CUDA_HOME, load_inline

CACHE_FORMAT_VERSION = 2

_FUNCTIONS = ["push"]
_COMPILE_ENV_VARS = (
    "CC",
    "CXX",
    "PYTORCH_NVCC",
    "NVCC_PREPEND_FLAGS",
    "NVCC_APPEND_FLAGS",
    "CPATH",
    "CPLUS_INCLUDE_PATH",
    "LIBRARY_PATH",
)


def _run_compiler_version(command: str) -> str:
    """Return ``<cmd> --version`` output. Raises on failure — compiler identity is
    key material, never silently omitted."""
    argv = shlex.split(command) + ["--version"]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=120, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"compiler version probe failed for {argv!r}: rc={proc.returncode} {proc.stderr.strip()[:500]}"
        )
    return proc.stdout.strip()


def _toolchain_metadata() -> dict[str, str]:
    meta: dict[str, str] = {}
    cxx = os.environ.get("CXX") or "c++"
    meta["cxx"] = cxx
    meta["cxx_version"] = _run_compiler_version(cxx)
    nvcc = os.environ.get("PYTORCH_NVCC")
    if not nvcc:
        if CUDA_HOME is None:
            raise RuntimeError("CUDA_HOME is unset and PYTORCH_NVCC is not defined")
        nvcc = os.path.join(CUDA_HOME, "bin", "nvcc")
    meta["nvcc"] = nvcc
    meta["nvcc_version"] = _run_compiler_version(nvcc)
    meta["cuda_home"] = str(CUDA_HOME)
    return meta


def _arch_request() -> str:
    explicit = os.environ.get("TORCH_CUDA_ARCH_LIST")
    if explicit:
        return f"explicit:{explicit}"
    if torch.cuda.is_available():
        caps = sorted(
            f"{torch.cuda.get_device_capability(i)[0]}.{torch.cuda.get_device_capability(i)[1]}"
            for i in range(torch.cuda.device_count())
        )
    else:
        caps = []
    return "auto:" + ",".join(caps) + "|" + ",".join(torch.cuda.get_arch_list())


def fingerprint(
    cpp_source: str,
    cuda_source: str,
    extra_cuda_cflags: list[str],
    toolchain: dict[str, str] | None = None,
    arch: str | None = None,
) -> str:
    """Deterministic 24-hex-char key for the extension build inputs. ``toolchain``
    and ``arch`` are injectable for tests; the rest is explicit environment reads."""
    if toolchain is None:
        toolchain = _toolchain_metadata()
    if arch is None:
        arch = _arch_request()
    key_material = {
        "cache_format": CACHE_FORMAT_VERSION,
        "cpp_source": cpp_source,
        "cuda_source": cuda_source,
        "functions": _FUNCTIONS,
        "extra_cuda_cflags": list(extra_cuda_cflags),
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "libc": "-".join(platform.libc_ver()),
        },
        "python": {
            "cache_tag": sys.implementation.cache_tag,
            "soabi": sysconfig.get_config_var("SOABI") or "",
        },
        "torch": {
            "version": torch.__version__,
            "git_version": torch.version.git_version,
            "cxx11_abi": torch._C._GLIBCXX_USE_CXX11_ABI,
            "cuda": torch.version.cuda,
            "install_path": os.path.dirname(torch.__file__),
            "debug": torch.version.debug,
            "build_config": torch.__config__.show(),
        },
        "toolchain": toolchain,
        "arch": arch,
        "env": {v: os.environ.get(v, "") for v in _COMPILE_ENV_VARS},
    }
    blob = json.dumps(key_material, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def cache_root() -> Path:
    """CUSP_BUILD_DIR if set, else ~/.cache/cusp_build."""
    return Path(os.environ.get("CUSP_BUILD_DIR") or Path.home() / ".cache" / "cusp_build")


def load_cached_extension(
    cpp_source: str,
    cuda_source: str,
    device_index: int,
    extra_cuda_cflags: list[str],
) -> types.ModuleType:
    """Build or load the fused kernel under a shared fingerprint-keyed directory.

    ``device_index`` selects nothing in the key — it exists so the caller's
    signature is stable; identical workers on different GPUs share one build.
    """
    del device_index  # not part of the fingerprint or module name
    key = fingerprint(cpp_source, cuda_source, list(extra_cuda_cflags))
    name = f"cusp_push_{key}"
    keydir = cache_root() / name
    keydir.mkdir(parents=True, exist_ok=True)
    flock_path = keydir / "build.flock"
    verbose = os.environ.get("CUSP_BUILD_VERBOSE") == "1"

    fd = os.open(flock_path, os.O_CREAT | os.O_RDWR)
    try:
        # Kernel releases this flock if the holder dies; a stale FileBaton 'lock'
        # left by a killed build is removed only while we hold the flock, which
        # every caller of these module names must pass through first.
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            stale = keydir / "lock"
            if stale.exists():
                stale.unlink()
            return load_inline(
                name=name,
                cpp_sources=cpp_source,
                cuda_sources=cuda_source,
                functions=_FUNCTIONS,
                build_directory=str(keydir),
                extra_cuda_cflags=list(extra_cuda_cflags),
                verbose=verbose,
            )
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
