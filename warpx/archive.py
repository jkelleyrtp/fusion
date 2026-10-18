#!/usr/bin/env python3
"""Keep every campaign's run data in the archive bucket, and check that what is there is what was written.

    archive.py push NAME [--only PREFIX] [--running]    copy each finished case not yet archived, and the campaign's own files
    archive.py check NAME [--sample N]                  list the bucket against every manifest; re-read and hash N files
    archive.py scrub NAME [--only PREFIX] [--running]   delete archived snapshots and checkpoints from shared storage, each
                                                        only after its copy in the bucket is read back and its hash matches
    archive.py status NAME                              what is archived and how large it is

The copy runs on a cluster node (`archive_on_node.py`), straight from shared storage to the bucket, so it needs
one of our jobs to be running, as `campaign.py sync` does. `check` runs here and reads the bucket only. Layout:

    cusp/campaigns/NAME/index.json            one entry per case: deck, settings, state, measurements, size
    cusp/campaigns/NAME/MANIFEST.json         the campaign's own files: case list, logs, decks and reducers each job carried
    cusp/campaigns/NAME/CASE/MANIFEST.json    size and SHA-256 of every file of the case
    cusp/campaigns/NAME/CASE/...              the case directory as WarpX and the worker left it

The keys are read from FUSION_R2_ACCESS_KEY_ID and FUSION_R2_SECRET_ACCESS_KEY and passed to the node on standard
input; they are not written to shared storage or to a job.
"""

import argparse
import hashlib
import json
import os
import random
import shlex
import subprocess
import tempfile
from pathlib import Path

import campaign

BUCKET = "fusion-research-devin"
ENDPOINT = "https://e6828ac217f9b2cf1903e08e369f352b.r2.cloudflarestorage.com"
BASE = "cusp/campaigns"
HELPER = f"{campaign.SHARED}/archive_on_node.py"


def keys() -> tuple[str, str]:
    return os.environ["FUSION_R2_ACCESS_KEY_ID"], os.environ["FUSION_R2_SECRET_ACCESS_KEY"]


def aws(*words: str, text: str | None = None) -> str:
    key, secret = keys()
    env = {**os.environ, "AWS_ACCESS_KEY_ID": key, "AWS_SECRET_ACCESS_KEY": secret, "AWS_DEFAULT_REGION": "auto",
           "AWS_REQUEST_CHECKSUM_CALCULATION": "when_required", "AWS_RESPONSE_CHECKSUM_VALIDATION": "when_required"}
    return subprocess.run(["aws", "--endpoint-url", ENDPOINT, *words], env=env, input=text, capture_output=True, text=True, check=True).stdout


def read_json(key: str) -> dict | None:
    try:
        return json.loads(aws("s3", "cp", f"s3://{BUCKET}/{key}", "-"))
    except subprocess.CalledProcessError:
        return None


def listing(prefix: str) -> dict[str, int]:
    """Size of every object under a prefix."""
    out = aws("s3api", "list-objects-v2", "--bucket", BUCKET, "--prefix", prefix, "--query", "Contents[].[Key,Size]", "--output", "json")
    return {key: size for key, size in (json.loads(out) or [])}


def on_node(directory: str, prefix: str, flag: str = "") -> dict:
    command = f"python3 {HELPER} {shlex.quote(directory)} {BUCKET} {shlex.quote(prefix)} {ENDPOINT} {flag}"
    pods = [pod for pod in campaign.my_pods() if "Running" in campaign.shell(f"kubectl --context {campaign.CONTEXT} get pod {pod} --no-headers")]
    assert pods, "no job of ours is running, so shared storage cannot be read right now"
    done = subprocess.run(f"kubectl --context {campaign.CONTEXT} exec -i {pods[0]} -- bash -c {shlex.quote(command)}", shell=True,
                          input="\n".join(keys()) + "\n", capture_output=True, text=True, check=False)
    assert done.stdout.strip(), f"copy of {directory} gave no report: {done.stderr[-600:]}"
    return json.loads(done.stdout.strip().split("\n")[-1])


def push(args: argparse.Namespace) -> None:
    camp = f"{campaign.SHARED}/campaigns/{args.name}"
    campaign.on_cluster(f"cat > {HELPER}", given=(campaign.ROOT / "archive_on_node.py").read_text())
    states = campaign.on_cluster(
        f"cd {camp} && while read -r name rest; do echo \"$name|$(cat $name/DONE 2>/dev/null)|$(cat $name/ARCHIVED 2>/dev/null)|"
        f"$(stat -c %Y $name/measured.json 2>/dev/null)|$(stat -c %Y $name/ARCHIVED 2>/dev/null)\"; done < all_cases.txt")
    for line in states.strip().split("\n"):
        name, done, archived, measured, when = line.split("|")
        if not name.startswith(args.only or "") or (not done and not args.running):
            continue
        if archived and not args.again and not args.resend and int(measured or 0) <= int(when or 0):
            continue
        report = on_node(f"{camp}/{name}", f"{BASE}/{args.name}/{name}", "--resend" if args.resend else "")
        print(f"{name}: {report['files']} files, {report['bytes'] / 1e9:.2f} GB, {report['uploaded']} uploaded"
              + (f", NOT ARCHIVED, wrong size in bucket: {report['wrong']}" if report["wrong"] else ""), flush=True)
    report = on_node(camp, f"{BASE}/{args.name}", "--top")
    print(f"campaign files: {report['files']} files, {report['bytes'] / 1e6:.1f} MB, {report['uploaded']} uploaded")
    index(args.name)


def scrub(args: argparse.Namespace) -> None:
    camp = f"{campaign.SHARED}/campaigns/{args.name}"
    campaign.on_cluster(f"cat > {HELPER}", given=(campaign.ROOT / "archive_on_node.py").read_text())
    states = campaign.on_cluster(f"cd {camp} && while read -r name rest; do echo \"$name|$(cat $name/DONE 2>/dev/null)|"
                                 f"$(cat $name/ARCHIVED 2>/dev/null)|$(find $name/CLAIM -mmin -10 2>/dev/null)\"; done < all_cases.txt")
    freed = 0
    for line in states.strip().split("\n"):
        name, done, archived, worked_on = line.split("|")  # a worker touches CLAIM every minute while it runs a case
        if not name.startswith(args.only or "") or not archived or worked_on or (not done and not args.running):
            continue
        report = on_node(f"{camp}/{name}", f"{BASE}/{args.name}/{name}", "--scrub")
        freed += report["bytes"]
        print(f"{name}: {report['checked']} files read back, {report['deleted']} deleted, {report['bytes'] / 1e9:.2f} GB freed"
              + (f", {report['left_in_diags']} files not in the archive left in place" if report["left_in_diags"] and not report["wrong"] else "")
              + (f", NOTHING DELETED, copies differ: {report['wrong']}" if report["wrong"] else ""), flush=True)
    print(f"{args.name}: {freed / 1e9:.2f} GB freed")


def index(name: str) -> None:
    """One entry per case, from the case list, each case's state on shared storage and its manifest in the bucket."""
    camp = f"{campaign.SHARED}/campaigns/{name}"
    rows = campaign.on_cluster(
        f"cd {camp} && while read -r name deck rest; do echo \"$name|$deck|$rest|$(cat $name/DONE 2>/dev/null)|$(cat $name/WALL_S 2>/dev/null)|"
        f"$(cat $name/TRIES 2>/dev/null)|$(cat $name/ARCHIVED 2>/dev/null)|$(cat $name/measured.json 2>/dev/null)\"; done < all_cases.txt")
    revision = campaign.shell("git rev-parse HEAD", cwd=str(campaign.ROOT)).strip()
    cases = {}
    for row in rows.strip().split("\n"):
        case, deck, settings, done, wall, tries, archived, measured = row.split("|", 7)
        cases[case] = {"deck": deck, "settings": settings.split(), "state": done or "not finished", "run_seconds": int(wall or 0),
                       "tries": int(tries or 0), "archived": archived or None, "measured": json.loads(measured) if measured.strip() else None}
    entry = campaign.registry().get(name, {})
    body = {"campaign": name, "question": entry.get("question"), "jobs": entry.get("jobs"), "indexed_at_revision": revision,
            "warpx_build": campaign.BUILD, "bucket": f"s3://{BUCKET}/{BASE}/{name}", "cases": cases}
    aws("s3", "cp", "-", f"s3://{BUCKET}/{BASE}/{name}/index.json", text=json.dumps(body, indent=1))
    print(f"index.json: {len(cases)} cases, {sum(1 for c in cases.values() if c['archived'])} archived")


def check(args: argparse.Namespace) -> None:
    held = listing(f"{BASE}/{args.name}/")
    manifests = sorted(key for key in held if key.endswith("/MANIFEST.json"))
    expected, bad = {}, []
    for key in manifests:
        folder = key[: -len("MANIFEST.json")]
        for file, (size, digest) in read_json(key)["files"].items():
            expected[folder + file] = (size, digest)
            if held.get(folder + file) != size:
                bad.append(f"{folder + file}: manifest says {size} bytes, bucket has {held.get(folder + file)}")
    random.seed(args.seed)
    for key in random.sample(sorted(expected), min(args.sample, len(expected))):
        with tempfile.NamedTemporaryFile() as copy:
            aws("s3", "cp", f"s3://{BUCKET}/{key}", copy.name)
            if hashlib.sha256(Path(copy.name).read_bytes()).hexdigest() != expected[key][1]:
                bad.append(f"{key}: SHA-256 of the copy read back differs from the manifest")
    print(f"{args.name}: {len(manifests)} manifests, {len(expected)} files, {sum(size for size, _ in expected.values()) / 1e9:.2f} GB; "
          f"sizes compared for all, {min(args.sample, len(expected))} read back and hashed; {len(bad)} wrong")
    for line in bad:
        print("  " + line)
    assert not bad


def status(args: argparse.Namespace) -> None:
    body = read_json(f"{BASE}/{args.name}/index.json")
    assert body, f"{args.name} has no index in the bucket"
    for case, entry in body["cases"].items():
        print(f"{case}: {entry['state']}; {entry['archived'] or 'not archived'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for function in (push, scrub, check, status):
        sub = commands.add_parser(function.__name__)
        sub.add_argument("name")
        sub.set_defaults(run=function)
    for name in ("push", "scrub"):
        commands.choices[name].add_argument("--only")
        commands.choices[name].add_argument("--running", action="store_true", help="also take cases that never finished")
    commands.choices["push"].add_argument("--again", action="store_true", help="hash and compare cases already marked archived")
    commands.choices["push"].add_argument("--resend", action="store_true", help="upload every file again, whatever the manifest says")
    commands.choices["check"].add_argument("--sample", type=int, default=20)
    commands.choices["check"].add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    args.run(args)
