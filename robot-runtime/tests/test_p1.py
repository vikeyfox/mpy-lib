"""P1 主机侧测试：技能包、A/B 槽位、安全点重载、BLE 帧。

运行：python3 tests/test_p1.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pkgctl
from blelink import CMD_COMMIT, CMD_CONFIRM, CMD_INFO, UpdateServer
from logcore import Session
from skills import SkillContext, SkillHost
from updater import SkillUpdater, UpdateError


def write_slot(base, name, files):
    slot = os.path.join(base, name)
    for rel, text in files.items():
        path = os.path.join(slot, rel)
        parent = os.path.dirname(path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        with open(path, "w") as f:
            f.write(text)
    return slot


def read_records(session):
    session.sync(force=True)
    path = os.path.join(session.dir, "events.jsonl")
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


class FakeLink:
    def __init__(self, telem=None):
        self.last_telem = telem if telem is not None else {"v": 0, "w": 0}
        self.writes = []

    def drive(self, v, w):
        self.writes.append((v, w))
        return True

    def stop(self):
        return self.drive(0, 0)


SKILL_OK = '''
_ctx = None

def setup(ctx):
    global _ctx
    _ctx = ctx
    ctx.setup_seen = ctx.param("gain", 1)
    ctx.emit("skill_setup", {"gain": ctx.setup_seen})

def step(dt_ms):
    n = getattr(_ctx, "steps", 0) + 1
    _ctx.steps = n
    if n == 1:
        _ctx.drive(0, 0)
        _ctx.emit("skill_step", {"dt": dt_ms})

def teardown():
    pass
'''

SKILL_BAD = '''
def setup(ctx):
    raise RuntimeError("boom")

def step(dt_ms):
    pass
'''


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="p1-")

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def make_pkg(self, files, version="1.0.0"):
        src = os.path.join(self.base, "src")
        for rel, text in files.items():
            path = os.path.join(src, rel)
            parent = os.path.dirname(path)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent)
            with open(path, "w") as f:
                f.write(text)
        return src, pkgctl.build(src, version, "main", "", "0.1.0", None)

    def test_stream_update_commits(self):
        src, manifest = self.make_pkg({"main.py": SKILL_OK, "params.json": '{"gain": 3}'})
        updater = SkillUpdater(self.base)
        server = UpdateServer(updater)
        stream = b"".join(pkgctl.iter_stream(manifest, src, 40))
        replies = server.feed(stream)
        self.assertTrue(all(r[2] == 0x80 for r in replies))
        self.assertNotIn(b'"ok": false', b"".join(replies))

        doc = updater.current()
        self.assertEqual(doc["slot"], "app_a")
        self.assertTrue(doc["pending"])
        self.assertEqual(doc["version"], "1.0.0")
        self.assertTrue(os.path.exists(os.path.join(self.base, "app_a", "main.py")))

        replies = server.feed(pkgctl.encode_frame(CMD_CONFIRM))
        self.assertIn(b'"ok": true', replies[0])
        self.assertFalse(updater.current()["pending"])

    def test_hash_mismatch_rejected(self):
        src, manifest = self.make_pkg({"main.py": SKILL_OK})
        updater = SkillUpdater(self.base)
        updater.begin(manifest)
        updater.begin_file("main.py")
        updater.write(b"x" * manifest["files"][0]["size"])
        with self.assertRaises(UpdateError):
            updater.end_file()
        updater.abort()

    def test_syntax_error_rejected(self):
        src = os.path.join(self.base, "src")
        os.makedirs(src, exist_ok=True)
        with open(os.path.join(src, "main.py"), "w") as f:
            f.write("def setup(:\n  pass\n")
        with self.assertRaises(SystemExit):
            pkgctl.build(src, "1.0.0", "main", "", "0.1.0", None)

    def test_boot_rollback_after_three_failures(self):
        write_slot(self.base, "app_a", {"main.py": SKILL_OK})
        write_slot(self.base, "app_b", {"main.py": SKILL_OK})
        with open(os.path.join(self.base, "current.json"), "w") as f:
            json.dump({"slot": "app_a", "prev": "app_b", "pending": True,
                       "bootcnt": 3, "entry": "main", "version": "1.0.0"}, f)

        updater = SkillUpdater(self.base)
        self.assertEqual(updater.boot_select(), "app_b")
        self.assertFalse(updater.current()["pending"])

    def test_path_traversal_rejected(self):
        updater = SkillUpdater(self.base)
        with self.assertRaises(UpdateError):
            updater.begin({"files": [{"path": "../evil.py", "size": 1,
                                      "sha256": "0" * 64}]})


class SkillHostTests(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="p1-skill-")
        self.log_root = os.path.join(self.base, "LOG")
        self.session = Session(self.log_root, "S1", {"device": {"id": "t"}},
                               {"flush_ms": 0, "rotate_bytes": 10 ** 9, "index_every": 50})
        self.link = FakeLink()
        self.updater = SkillUpdater(self.base)
        self.ctx = SkillContext(self.session, self.link)
        self.host = SkillHost(self.updater, self.ctx)

    def tearDown(self):
        self.host._unload()
        self.session.close("user")
        shutil.rmtree(self.base, ignore_errors=True)

    def test_load_step_and_params(self):
        write_slot(self.base, "app_a", {
            "main.py": SKILL_OK,
            "params.json": '{"gain": 7}',
        })
        self.assertTrue(self.host.load(slot="app_a"))
        self.assertEqual(self.ctx.params["gain"], 7)
        self.host.tick(20)
        self.host.tick(20)
        self.assertEqual(self.ctx.steps, 2)
        self.assertEqual(self.link.writes, [(0, 0)])

        events = [r["ev"] for r in read_records(self.session)]
        self.assertIn("reload", events)
        self.assertIn("skill_setup", events)
        self.assertIn("skill_step", events)

    def test_failed_setup_rolls_back(self):
        write_slot(self.base, "app_a", {"main.py": SKILL_BAD})
        write_slot(self.base, "app_b", {"main.py": SKILL_OK})
        with open(os.path.join(self.base, "current.json"), "w") as f:
            json.dump({"slot": "app_a", "prev": "app_b", "pending": True,
                       "bootcnt": 0, "entry": "main", "version": "bad"}, f)

        self.assertTrue(self.host.load())
        self.assertEqual(self.host.slot, "app_b")
        self.assertFalse(self.updater.current()["pending"])

        levels = [r["lvl"] for r in read_records(self.session)]
        self.assertIn("CRIT", levels)
        self.assertIn("WARN", levels)

    def test_healthy_run_confirms_pending(self):
        write_slot(self.base, "app_a", {"main.py": SKILL_OK})
        write_slot(self.base, "app_b", {"main.py": SKILL_OK})
        with open(os.path.join(self.base, "current.json"), "w") as f:
            json.dump({"slot": "app_a", "prev": "app_b", "pending": True,
                       "bootcnt": 1, "entry": "main", "version": "1.1.0"}, f)

        self.assertTrue(self.host.load(slot="app_a"))
        for _ in range(20):
            self.host.tick(250)
        doc = self.updater.current()
        self.assertFalse(doc["pending"])
        self.assertEqual(doc["bootcnt"], 0)

    def test_pending_applies_only_at_safe_point(self):
        write_slot(self.base, "app_a", {"main.py": SKILL_OK})
        write_slot(self.base, "app_b", {"main.py": SKILL_OK})
        with open(os.path.join(self.base, "current.json"), "w") as f:
            json.dump({"slot": "app_a", "prev": None, "pending": False,
                       "bootcnt": 0, "entry": "main", "version": "1.0.0"}, f)
        self.assertTrue(self.host.load(slot="app_a"))
        self.assertEqual(self.ctx.version, "1.0.0")

        with open(os.path.join(self.base, "current.json"), "w") as f:
            json.dump({"slot": "app_b", "prev": "app_a", "pending": True,
                       "bootcnt": 0, "entry": "main", "version": "2.0.0"}, f)

        safe = [False]
        self.ctx.safe_check = lambda: safe[0]
        self.host.tick(20)
        self.assertEqual(self.host.slot, "app_a")

        safe[0] = True
        self.host.tick(20)
        self.assertEqual(self.host.slot, "app_b")
        self.assertEqual(self.ctx.version, "2.0.0")

    def test_runtime_step_failure_recovers(self):
        write_slot(self.base, "app_b", {"main.py": SKILL_OK})
        write_slot(self.base, "app_a", {"main.py": '''
def setup(ctx):
    pass

def step(dt_ms):
    raise RuntimeError("step failed")
'''})
        with open(os.path.join(self.base, "current.json"), "w") as f:
            json.dump({"slot": "app_a", "prev": "app_b", "pending": True,
                       "bootcnt": 1, "entry": "main", "version": "broken"}, f)

        self.assertTrue(self.host.load(slot="app_a"))
        for _ in range(3):
            self.host.tick(20)
        self.assertEqual(self.host.slot, "app_b")

    def test_ble_info_reply(self):
        updater = SkillUpdater(self.base)
        server = UpdateServer(updater)
        replies = server.feed(pkgctl.encode_frame(CMD_INFO))
        self.assertIn(b'"ok": true', replies[0])
        self.assertIn(b'"kernel"', replies[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
