"""Fingerprint-keyed persistent build cache for the fused cusp CUDA kernel."""

import fcntl
import hashlib
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import sysconfig
import time
import types
from pathlib import Path

import torch
from torch.utils.cpp_extension import CUDA_HOME, load_inline

CACHE_FORMAT_VERSION = 3

_COMPILE_ENV_VARS = (
    "PATH",
    "CC",
    "CXX",
    "PYTORCH_NVCC",
    "NVCC_PREPEND_FLAGS",
    "NVCC_APPEND_FLAGS",
    "CPATH",
    "CPLUS_INCLUDE_PATH",
    "LIBRARY_PATH",
)


def _resolve_executable(command: str) -> str:
    """Realpath of the executable a command resolves to. Raises if not found —
    toolchain identity is key material, never silently omitted."""
    exe = shlex.split(command)[0]
    found = shutil.which(exe)
    if found is None:
        raise RuntimeError(f"compiler executable {exe!r} not found on PATH")
    return str(Path(found).resolve())


def _compiler_metadata(command: str) -> dict[str, str]:
    argv = shlex.split(command) + ["--version"]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=120, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"compiler version probe failed for {argv!r}: rc={proc.returncode} {proc.stderr.strip()[:500]}"
        )
    return {
        "command": command,
        "path": _resolve_executable(command),
        "version": proc.stdout.strip(),
    }


def _toolchain_metadata() -> dict[str, object]:
    cxx = os.environ.get("CXX") or "c++"
    nvcc = os.environ.get("PYTORCH_NVCC")
    if not nvcc:
        if CUDA_HOME is None:
            raise RuntimeError("CUDA_HOME is unset and PYTORCH_NVCC is not defined")
        nvcc = os.path.join(CUDA_HOME, "bin", "nvcc")
    return {
        "cxx": _compiler_metadata(cxx),
        "nvcc": _compiler_metadata(nvcc),
        "cuda_home": str(CUDA_HOME),
    }


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
    *,
    functions: tuple[str, ...] = ("push",),
    toolchain: dict[str, object] | None = None,
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
        "functions": list(functions),
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


def _artifact_sig(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return (st.st_size, st.st_mtime_ns)


def load_cached_extension(
    cpp_source: str,
    cuda_source: str,
    device_index: int,
    extra_cuda_cflags: list[str],
    *,
    functions: tuple[str, ...] = ("push",),
) -> types.ModuleType:
    """Build or load the fused kernel under a shared fingerprint-keyed directory.

    ``device_index`` selects nothing in the key — it exists so the caller's
    signature is stable; identical workers on different GPUs share one build.
    """
    del device_index  # not part of the fingerprint or module name
    key = fingerprint(
        cpp_source, cuda_source, list(extra_cuda_cflags), functions=functions,
    )
    name = f"cusp_push_{key}"
    keydir = cache_root() / name
    keydir.mkdir(parents=True, exist_ok=True)
    flock_path = keydir / "build.flock"
    verbose = os.environ.get("CUSP_BUILD_VERBOSE") == "1"

    fd = os.open(flock_path, os.O_CREAT | os.O_RDWR)
    try:
        # Every caller for a cusp_push_<key> name must pass through this flock,
        # whose kernel release survives holder death; a FileBaton 'lock' file
        # still present at this point is therefore stale and safe to remove.
        t_wait = time.perf_counter()
        fcntl.flock(fd, fcntl.LOCK_EX)
        wait_s = time.perf_counter() - t_wait
        try:
            stale = keydir / "lock"
            if stale.exists():
                stale.unlink()
            before = _artifact_sig(keydir / f"{name}.so")
            t_build = time.perf_counter()
            module = load_inline(
                name=name,
                cpp_sources=cpp_source,
                cuda_sources=cuda_source,
                functions=list(functions),
                build_directory=str(keydir),
                extra_cuda_cflags=list(extra_cuda_cflags),
                verbose=verbose,
            )
            elapsed_s = time.perf_counter() - t_build
            if not isinstance(module, types.ModuleType):
                raise RuntimeError(  # noqa: TRY004 - RuntimeError keeps the caller's build-failure path uniform
                    f"load_inline returned invalid module for {name}: {module!r}"
                )
            try:
                module_file = module.__file__
            except AttributeError:
                module_file = None
            if not module_file:
                raise RuntimeError(f"load_inline returned invalid module for {name}: {module!r}")
            module_path = Path(module_file)
            after = _artifact_sig(module_path)
            if before is None:
                outcome = "cold-build"
            elif after != before or module_path != keydir / f"{name}.so":
                outcome = "rebuilt"
            else:
                outcome = "cache-hit"
            print(
                f"[cuda-build-cache] {outcome} {name} key={key} "
                f"build={elapsed_s:.1f}s lock-wait={wait_s:.1f}s",
                flush=True,
            )
            return module
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
