#!/usr/bin/env python3
"""Run on a cluster node by archive.py: copy one directory of shared storage to the archive bucket and check it.

    archive_on_node.py DIRECTORY BUCKET PREFIX ENDPOINT [--top | --scrub | --resend]    (two lines on standard input: key id, secret key)

Every file is hashed, uploaded if the bucket's manifest does not already list it with that hash (`--resend`: uploaded
regardless, for when a copy in the bucket turned out wrong), and then the
bucket is listed and each object's size compared with the file's. Only if all agree is MANIFEST.json uploaded
and ARCHIVED written beside the files. `--top` takes a campaign's own files (case list, logs, the decks and
reducers each job carried) and leaves the case directories to their own calls. The keys are never written down.

`--scrub` frees shared storage once a case is archived. It takes the snapshots and checkpoints (everything under
diags/ but reducedfiles), reads each back from the bucket and hashes it, hashes the file on disk again, and deletes
only if every one of them gives the hash in the manifest three ways. Otherwise it deletes nothing. What is left is
what `campaign.py` reads: DONE, logs, inputs, measurements and the reduced histories.
"""

import concurrent.futures
import datetime
import hashlib
import json
import socket
import sys
import time
from pathlib import Path

import boto3
from boto3.exceptions import S3UploadFailedError
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

SKIP = {"CLAIM", "ARCHIVED", "SCRUBBED", "MANIFEST.json", "lock"}


def wanted(root: Path, top: bool) -> list[Path]:
    """Files to keep. WarpX renames a snapshot it is about to overwrite to NAME.old.N; those are left out."""
    if top:
        files = [p for p in root.iterdir() if p.is_file()]
        for folder in [*root.glob("files-*"), root / "logs"]:
            files += [p for p in folder.rglob("*") if p.is_file()]
    else:
        files = [p for p in root.rglob("*") if p.is_file()]
    return sorted(p for p in files if p.name not in SKIP and ".old." not in str(p.relative_to(root)) and not p.name.startswith("busy."))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as data:
        while block := data.read(1 << 24):
            digest.update(block)
    return digest.hexdigest()


def scrub(s3, root: Path, bucket: str, prefix: str) -> None:
    listed = json.loads(s3.get_object(Bucket=bucket, Key=f"{prefix}/MANIFEST.json")["Body"].read())["files"]
    bulky = sorted(name for name in listed
                   if name.startswith("diags/") and not name.startswith("diags/reducedfiles/") and (root / name).is_file())

    def in_bucket(name: str) -> str:
        for attempt in range(5):
            try:
                digest = hashlib.sha256()
                for block in s3.get_object(Bucket=bucket, Key=f"{prefix}/{name}")["Body"].iter_chunks(1 << 24):
                    digest.update(block)
                return digest.hexdigest()
            except (BotoCoreError, ClientError, OSError) as error:
                print(f"{name}: read {attempt + 1} failed: {str(error)[-200:]}", file=sys.stderr)
                time.sleep(10)
        return "could not be read"

    with concurrent.futures.ThreadPoolExecutor(24) as pool:
        there = list(pool.map(in_bucket, bulky))
        here = list(pool.map(lambda name: sha256(root / name), bulky))
    wrong = sorted(name for name, a, b in zip(bulky, there, here) if not a == b == listed[name][1])
    freed = sum(listed[name][0] for name in bulky)
    if not wrong and bulky:
        for name in bulky:
            (root / name).unlink()
        for folder in sorted((p for p in (root / "diags").rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
            if not any(folder.iterdir()):
                folder.rmdir()
        with open(root / "SCRUBBED", "a") as note:
            note.write(f"{datetime.datetime.now(datetime.UTC).isoformat(timespec='seconds')} {len(bulky)} snapshot and checkpoint files, "
                       f"{freed} bytes, deleted here after each was read back from s3://{bucket}/{prefix} and its SHA-256 matched\n")
    left = sum(1 for p in (root / "diags").rglob("*") if p.is_file() and "reducedfiles" not in p.parts) if (root / "diags").is_dir() else 0
    print(json.dumps({"directory": str(root), "checked": len(bulky), "deleted": 0 if wrong else len(bulky), "bytes": 0 if wrong else freed,
                      "wrong": wrong[:20], "left_in_diags": left}))
    sys.exit(1 if wrong else 0)


def main() -> None:
    root, bucket, prefix, endpoint = Path(sys.argv[1]), sys.argv[2], sys.argv[3].rstrip("/"), sys.argv[4]
    top = "--top" in sys.argv
    key, secret = sys.stdin.readline().strip(), sys.stdin.readline().strip()
    s3 = boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=key, aws_secret_access_key=secret, region_name="auto",
                      config=Config(max_pool_connections=64, retries={"max_attempts": 10, "mode": "adaptive"},
                                    request_checksum_calculation="when_required", response_checksum_validation="when_required"))
    if "--scrub" in sys.argv:
        scrub(s3, root, bucket, prefix)
    files = wanted(root, top)
    with concurrent.futures.ThreadPoolExecutor(32) as pool:
        hashes = list(pool.map(sha256, files))
    now = {str(p.relative_to(root)): [p.stat().st_size, digest] for p, digest in zip(files, hashes)}
    try:
        before = json.loads(s3.get_object(Bucket=bucket, Key=f"{prefix}/MANIFEST.json")["Body"].read())["files"]
    except s3.exceptions.NoSuchKey:
        before = {}
    changed = [name for name, entry in now.items() if before.get(name) != entry or "--resend" in sys.argv]
    if (root / "SCRUBBED").exists():  # files deleted here after archiving are still in the bucket and stay in the manifest
        now = {**{name: entry for name, entry in before.items() if name not in now}, **now}

    def upload(name: str) -> None:
        """The bucket drops a connection now and then in the middle of a large file; the file is then sent again."""
        for attempt in range(5):
            try:
                s3.upload_file(str(root / name), bucket, f"{prefix}/{name}", ExtraArgs={"Metadata": {"sha256": now[name][1]}},
                               Config=TransferConfig(max_concurrency=4, multipart_chunksize=64 << 20))
                return
            except (BotoCoreError, ClientError, S3UploadFailedError) as error:
                print(f"{name}: try {attempt + 1} failed: {str(error)[-200:]}", file=sys.stderr)
                if attempt == 4:
                    raise
                time.sleep(10)

    with concurrent.futures.ThreadPoolExecutor(12) as pool:
        list(pool.map(upload, changed))
    held = {}
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix + "/"):
        for item in page.get("Contents", []):
            held[item["Key"][len(prefix) + 1:]] = item["Size"]
    if top:  # the listing under a campaign also holds its cases; only this call's files are compared
        held = {name: size for name, size in held.items() if name in now}
    wrong = sorted(name for name, (size, _) in now.items() if held.get(name) != size)
    report = {"directory": str(root), "files": len(now), "bytes": sum(size for size, _ in now.values()), "uploaded": len(changed), "wrong": wrong[:20]}
    if not wrong:
        manifest = {"directory": str(root), "archived_utc": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
                    "copied_from": socket.gethostname(), "files": now}
        s3.put_object(Bucket=bucket, Key=f"{prefix}/MANIFEST.json", Body=json.dumps(manifest, indent=1).encode())
        if not top:
            (root / "ARCHIVED").write_text(f"{manifest['archived_utc']} {len(now)} files {report['bytes']} bytes s3://{bucket}/{prefix}\n")
    print(json.dumps(report))
    sys.exit(1 if wrong else 0)


if __name__ == "__main__":
    main()
