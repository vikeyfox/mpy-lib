"""P0 主机侧测试：恢复、轮转、编解码、运行时。

运行：python3 tests/test_p0.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from chassis import ChassisLink, MockCodec, MSG_CAPS, MSG_TELEM, parse_telem
from logcore import Session
from runtime import Runtime


class FakeUart:
    def __init__(self):
        self.rx = b""
        self.tx = b""

    def read(self, n):
        data, self.rx = self.rx[:n], self.rx[n:]
        return data

    def write(self, buf):
        self.tx += buf
        return len(buf)


def telem(seq, v=100, w=5, batt=90):
    return bytes([
        seq & 0xFF, (seq >> 8) & 0xFF,
        v & 0xFF, (v >> 8) & 0xFF,
        w & 0xFF, (w >> 8) & 0xFF,
        0, batt,
    ])


class P0Tests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="p0-")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_power_loss_recovery(self):
        cfg = {"rotate_bytes": 10 ** 9, "index_every": 50, "flush_ms": 0}
        s = Session(self.root, "S1", {"device": {"id": "t"}}, cfg)
        for i in range(20):
            s.emit("test", "INFO", "sample", {"i": i})
        s.close("user")

        path = os.path.join(self.root, "S1", "events.jsonl")
        with open(path, "rb") as f:
            data = f.read()
        with open(path, "wb") as f:
            f.write(data[:-8])  # 截断 close 记录

        s2 = Session(self.root, "S1", {}, cfg)
        self.assertEqual(s2.seq, 20)
        self.assertEqual(s2.recovered, 1)
        s2.emit("test", "INFO", "after")
        s2.close("power_loss")

        with open(os.path.join(self.root, "S1", "manifest.json")) as f:
            manifest = json.load(f)
        self.assertEqual(manifest["close"]["reason"], "power_loss")

    def test_rotation_and_index(self):
        cfg = {"rotate_bytes": 600, "max_files": 2, "index_every": 1, "flush_ms": 0}
        s = Session(self.root, "S2", {}, cfg)
        for i in range(40):
            s.emit("test", "INFO", "sample", {"i": i})
        s.close("user")

        names = os.listdir(os.path.join(self.root, "S2"))
        rotated = [n for n in names if n.startswith("events.") and n != "events.jsonl"]
        self.assertTrue(rotated, "应发生轮转")
        self.assertLessEqual(len(rotated), 2)
        self.assertIn("index.jsonl", names)

    def test_codec_stream_and_noise(self):
        codec = MockCodec()
        frame = codec.encode(MSG_TELEM, telem(1))
        out = []
        for b in b"\x00\xFF" + frame:
            out += codec.feed(bytes([b]))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][0], MSG_TELEM)
        parsed = parse_telem(out[0][1])
        self.assertEqual(parsed["chassis_seq"], 1)
        self.assertEqual(parsed["v"], 100)

    def test_codec_drop_detection(self):
        codec = MockCodec()
        uart = FakeUart()
        link = ChassisLink(uart, codec, clock=lambda: 1000)
        uart.rx = codec.encode(MSG_CAPS, b"{}")
        self.assertEqual(link.poll()[0][0], "caps")
        uart.rx = codec.encode(MSG_TELEM, telem(1))
        link.poll()
        uart.rx = codec.encode(MSG_TELEM, telem(4))
        events = link.poll()
        self.assertIn(("drop", 2), events)
        self.assertEqual(link.dropped, 2)

    def test_runtime_writes_sample(self):
        cfg = {"rotate_bytes": 10 ** 9, "index_every": 10, "flush_ms": 0}
        s = Session(self.root, "S3", {}, cfg)
        codec = MockCodec()
        uart = FakeUart()
        uart.rx = codec.encode(MSG_CAPS, b"{}") + codec.encode(MSG_TELEM, telem(1))
        link = ChassisLink(uart, codec, clock=lambda: 1000)
        rt = Runtime(link, s, {"log_hz": 1, "loop_ms": 20, "device_id": "t"})
        rt.tick()
        s.close("user")

        path = os.path.join(self.root, "S3", "events.jsonl")
        with open(path) as f:
            records = [json.loads(line) for line in f if line.strip()]
        events = [r["ev"] for r in records]
        self.assertIn("boot", events)
        self.assertIn("caps", events)
        self.assertIn("sample", events)

    def test_link_timeout(self):
        codec = MockCodec()
        uart = FakeUart()
        now = [1000]
        link = ChassisLink(uart, codec, clock=lambda: now[0], timeout_ms=200)
        uart.rx = codec.encode(MSG_TELEM, telem(1))
        link.poll()
        self.assertFalse(link.timed_out())
        now[0] = 1300
        self.assertTrue(link.timed_out())


if __name__ == "__main__":
    unittest.main(verbosity=2)
