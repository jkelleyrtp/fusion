"""Coverage for selecting which CUDA functions enter a cached extension."""

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import cuda_build_cache as cbc

CPP = "void push(); void deposit(); void gather(); void drift(); void boris();"
CU = "__global__ void k() {}"
FLAGS = ["-O3", "--fmad=false"]
KEY = "deadbeefdeadbeefdeadbeef"
TOOLCHAIN: dict[str, object] = {
    "cxx": {"command": "c++", "path": "/usr/bin/c++", "version": "g++ 13"},
    "nvcc": {"command": "/usr/local/cuda/bin/nvcc", "path": "/usr/local/cuda/bin/nvcc",
             "version": "12.9"},
    "cuda_home": "/usr/local/cuda",
}
EXPORTS = ("deposit", "gather", "drift", "boris")


def key(functions: tuple[str, ...] = ("push",)) -> str:
    return cbc.fingerprint(
        CPP,
        CU,
        FLAGS,
        functions=functions,
        toolchain={
            key: dict(value) if isinstance(value, dict) else value
            for key, value in TOOLCHAIN.items()
        },
        arch="explicit:10.0",
    )


class CacheExportTests(unittest.TestCase):
    def test_default_and_explicit_push_key_match(self) -> None:
        self.assertEqual(key(), key(("push",)))

    def test_positional_toolchain_and_arch_match_keyword_call(self) -> None:
        self.assertEqual(
            cbc.fingerprint(CPP, CU, FLAGS, TOOLCHAIN, "explicit:10.0"),
            key(),
        )

    def test_export_names_and_order_change_key(self) -> None:
        base = key()
        self.assertNotEqual(base, key(EXPORTS))
        self.assertNotEqual(key(EXPORTS), key(tuple(reversed(EXPORTS))))

    def test_loader_passes_functions_to_fingerprint_and_load_inline(self) -> None:
        fingerprint_calls = []
        load_calls = []

        def fingerprint(*args: object, **kwargs: object) -> str:
            fingerprint_calls.append((args, kwargs))
            return KEY

        def load_inline(**kwargs: object) -> types.ModuleType:
            load_calls.append(kwargs)
            path = Path(str(kwargs["build_directory"])) / f"{kwargs['name']}.so"
            path.touch()
            module = types.ModuleType(str(kwargs["name"]))
            module.__file__ = str(path)
            return module

        with tempfile.TemporaryDirectory() as directory:
            env = mock.patch.dict(os.environ, {"CUSP_BUILD_DIR": directory})
            with env, mock.patch.object(cbc, "fingerprint", side_effect=fingerprint), \
                    mock.patch.object(cbc, "load_inline", side_effect=load_inline):
                cbc.load_cached_extension(CPP, CU, 0, FLAGS, functions=EXPORTS)

        self.assertEqual(len(fingerprint_calls), 1)
        self.assertEqual(fingerprint_calls[0][1]["functions"], EXPORTS)
        self.assertEqual(load_calls[0]["functions"], list(EXPORTS))


if __name__ == "__main__":
    unittest.main()
