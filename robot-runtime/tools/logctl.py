"""上位机侧日志工具（纯 CPython，不依赖设备）。

用法：
    python3 tools/logctl.py verify  /LOG/S20261016-142530
    python3 tools/logctl.py summary /LOG/S20261016-142530
    python3 tools/logctl.py tail    /LOG/S20261016-142530 -n 20
"""

import argparse
import json
import os


def event_files(session_dir):
    items = []
    for name in os.listdir(session_dir):
        if name == "events.jsonl":
            items.append((1, 0, name))
        elif name.startswith("events.") and name.endswith(".jsonl"):
            try:
                items.append((0, int(name[7:-6]), name))
            except ValueError:
                pass
    items.sort()
    return [name for _, _, name in items]


def iter_records(session_dir):
    for name in event_files(session_dir):
        path = os.path.join(session_dir, name)
        with open(path, "rb") as f:
            for lineno, line in enumerate(f, 1):
                if not line.endswith(b"\n"):
                    yield name, lineno, None, "truncated line"
                    continue
                try:
                    yield name, lineno, json.loads(line.decode()), None
                except Exception as exc:
                    yield name, lineno, None, "parse error: %s" % exc


def cmd_verify(args):
    total = 0
    bad = 0
    gaps = 0
    last_seq = None
    for name, lineno, rec, err in iter_records(args.session):
        total += 1
        if err:
            bad += 1
            print("%s:%d %s" % (name, lineno, err))
            continue
        seq = rec.get("seq")
        if not isinstance(seq, int):
            bad += 1
            print("%s:%d missing seq" % (name, lineno))
            continue
        if last_seq is not None and seq != last_seq + 1:
            gaps += 1
            print("%s:%d seq %d -> %d" % (name, lineno, last_seq, seq))
        last_seq = seq
    print("records=%d bad=%d gaps=%d last_seq=%s" % (total, bad, gaps, last_seq))
    return 0 if bad == 0 else 1


def cmd_summary(args):
    manifest = {}
    path = os.path.join(args.session, "manifest.json")
    if os.path.exists(path):
        with open(path) as f:
            manifest = json.load(f)
    levels = {}
    first_t = None
    last_t = None
    total = 0
    size = 0
    for name in event_files(args.session):
        size += os.path.getsize(os.path.join(args.session, name))
    for _, _, rec, err in iter_records(args.session):
        if err:
            continue
        total += 1
        levels[rec.get("lvl", "?")] = levels.get(rec.get("lvl", "?"), 0) + 1
        t = rec.get("t")
        if isinstance(t, (int, float)):
            first_t = t if first_t is None else first_t
            last_t = t
    print("session=%s state=%s" % (manifest.get("session"), manifest.get("state")))
    print("records=%d bytes=%d" % (total, size))
    print("levels=%s" % json.dumps(levels, sort_keys=True))
    if first_t is not None:
        print("duration_s=%.1f" % ((last_t - first_t) / 1000.0))
    close = manifest.get("close")
    if close:
        print("close=%s" % json.dumps(close, sort_keys=True))
    return 0


def cmd_tail(args):
    records = []
    for _, _, rec, err in iter_records(args.session):
        if err is None:
            records.append(rec)
    for rec in records[-args.n:]:
        print(json.dumps(rec, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("verify")
    p.add_argument("session")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("summary")
    p.add_argument("session")
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("tail")
    p.add_argument("session")
    p.add_argument("-n", type=int, default=20)
    p.set_defaults(func=cmd_tail)

    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
