"""Serve the built control room, with compressed application assets."""

import argparse
import mimetypes
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from os import PathLike, fspath
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


class ViewerHandler(SimpleHTTPRequestHandler):
    compressed = False

    def choose_encoding(self) -> None:
        self.compressed = False
        parts = urlsplit(self.path)
        if parts.path.endswith((".js", ".css")) and "gzip" in self.headers.get("Accept-Encoding", ""):
            candidate = Path(self.translate_path(parts.path) + ".gz")
            if candidate.is_file():
                self.path = urlunsplit(parts._replace(path=parts.path + ".gz"))
                self.compressed = True

    def do_GET(self) -> None:
        self.choose_encoding()
        super().do_GET()

    def do_HEAD(self) -> None:
        self.choose_encoding()
        super().do_HEAD()

    def guess_type(self, path: str | PathLike[str]) -> str:
        path = fspath(path)
        if self.compressed:
            return mimetypes.guess_type(path[:-3])[0] or "application/octet-stream"
        return super().guess_type(path)

    def end_headers(self) -> None:
        if self.compressed:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        if self.path.endswith(".cspz"):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parents[1] / "web" / "dist")
    args = parser.parse_args()
    if not (args.directory / "index.html").is_file():
        parser.error("Build the viewer first: cd web && npm ci && npm run build")
    server = ThreadingHTTPServer((args.host, args.port), partial(ViewerHandler, directory=str(args.directory)))
    print(f"Fusion Control Room on {args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
