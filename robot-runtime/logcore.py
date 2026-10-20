"""P0 日志内核：会话目录、追加写、掉电恢复。

同时兼容 MicroPython 与 CPython（主机侧测试）。
设计约定见 docs/debug-log-system.md 第 3 / 4 章。
"""

import json
import os
import time

from sink import FileSink

SCHEMA = 1
LEVELS = ("DEBUG", "INFO", "WARN", "ERROR", "CRIT")


def now_ms():
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.monotonic() * 1000)


def epoch_s():
    try:
        value = int(time.time())
    except Exception:
        return None
    # 未同步的 RTC 常从 1970 / 2000 起算，视为无效
    return value if value >= 1600000000 else None


def sleep_ms(ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(ms)
    else:
        time.sleep(ms / 1000.0)


def ensure_dir(path):
    try:
        os.mkdir(path)
    except OSError:
        pass


def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def fs_sync():
    if hasattr(os, "sync"):
        try:
            os.sync()
        except OSError:
            pass


def _dumps(obj):
    return json.dumps(obj)


def _fmt_ts(ts):
    if ts is None:
        return "-"
    try:
        t = time.localtime(ts)
        return "%04d-%02d-%02d %02d:%02d:%02d" % (t[0], t[1], t[2], t[3], t[4], t[5])
    except Exception:
        return str(ts)


class Session:
    """一个会话目录：/LOG/<sid>/{manifest.json,events.jsonl,index.jsonl}。"""

    def __init__(self, root, sid, meta=None, log_cfg=None):
        self.root = root
        self.sid = sid
        self.dir = root + "/" + sid
        cfg = log_cfg or {}
        self.flush_ms = cfg.get("flush_ms", 1000)
        self.rotate_bytes = cfg.get("rotate_bytes", 262144)
        self.max_files = cfg.get("max_files", 4)
        self.index_every = cfg.get("index_every", 100)

        self.seq = 0
        self.offset = 0
        self.file_no = 0
        self.recovered = 0
        self.dropped = 0
        self.last_flush = now_ms()
        self.last_fs_sync = self.last_flush
        self.events = None
        self.index = None
        self.device = (meta or {}).get("device", {}).get("id")
        self.stats = {
            "total": 0,
            "levels": {},
            "first_t": None,
            "last_t": None,
            "chassis_drop": 0,
            "errors": [],
        }

        ensure_dir(root)
        ensure_dir(self.dir)
        self._open(meta or {})

    def _path(self, name):
        return self.dir + "/" + name

    @staticmethod
    def _events_name(no):
        return "events.jsonl" if no == 0 else "events.%d.jsonl" % no

    def _next_file_no(self):
        top = 0
        try:
            for name in os.listdir(self.dir):
                if name.startswith("events.") and name.endswith(".jsonl"):
                    try:
                        top = max(top, int(name[7:-6]))
                    except ValueError:
                        pass
        except OSError:
            pass
        return top

    def _open(self, meta):
        self.file_no = self._next_file_no()
        path = self._path("events.jsonl")
        if exists(path):
            last_seq, valid_end, truncated = self._recover(path)
            self.seq = last_seq
            self.offset = valid_end
            self.recovered = 1 if truncated else 0
        self.events = FileSink(path, "ab")
        self.index = FileSink(self._path("index.jsonl"), "ab")
        if not exists(self._path("manifest.json")):
            self._write_manifest(meta, running=True)

    @staticmethod
    def _recover(path):
        """顺序扫描，遇到坏行或半行即截断到上一个完整记录之后。"""
        last_seq = 0
        valid_end = 0
        truncated = False
        with open(path, "rb") as f:
            while True:
                line = f.readline()
                if not line:
                    break
                if not line.endswith(b"\n"):
                    truncated = True
                    break
                try:
                    rec = json.loads(line.decode())
                    seq = int(rec["seq"])
                    if seq <= last_seq:
                        raise ValueError("seq not increasing")
                except Exception:
                    truncated = True
                    break
                last_seq = seq
                valid_end += len(line)
        if truncated:
            try:
                with open(path, "r+b") as f:
                    f.truncate(valid_end)
            except Exception:
                pass
        return last_seq, valid_end, truncated

    def emit(self, src, lvl="INFO", ev="sample", m=None, q="ok"):
        if lvl not in LEVELS:
            lvl = "INFO"
        self.seq += 1
        rec = {
            "v": SCHEMA,
            "seq": self.seq,
            "t": now_ms(),
            "ts": epoch_s(),
            "src": src,
            "lvl": lvl,
            "ev": ev,
        }
        if m is not None:
            rec["m"] = m
        if q != "ok":
            rec["q"] = q
        line = (_dumps(rec) + "\n").encode()
        self.events.write(line)
        self.offset += len(line)

        st = self.stats
        st["total"] += 1
        st["levels"][lvl] = st["levels"].get(lvl, 0) + 1
        if st["first_t"] is None:
            st["first_t"] = rec["t"]
        st["last_t"] = rec["t"]
        if ev == "drop" and m:
            st["chassis_drop"] += int(m.get("n", 0))
        if lvl in ("ERROR", "CRIT"):
            st["errors"].append({"t": rec["t"], "src": src, "ev": ev, "m": m})
            if len(st["errors"]) > 5:
                st["errors"].pop(0)

        if self.seq % self.index_every == 0:
            self._index(rec)
        if self.offset >= self.rotate_bytes:
            self.rotate()
        return rec

    def _index(self, rec):
        item = {
            "seq": rec["seq"],
            "f": self._events_name(self.file_no),
            "off": self.offset,
            "t": rec["t"],
            "lvl": rec["lvl"],
        }
        self.index.write((_dumps(item) + "\n").encode())

    def sync(self, force=False):
        if not force and (now_ms() - self.last_flush) < self.flush_ms:
            return
        self.events.sync()
        self.index.sync()
        # os.sync 会提交整个文件系统，代价明显，低频执行即可
        if force or (now_ms() - self.last_fs_sync) >= 5000:
            fs_sync()
            self.last_fs_sync = now_ms()
        self.last_flush = now_ms()

    def rotate(self):
        self.sync(force=True)
        self.events.close()
        self.file_no += 1
        try:
            os.rename(self._path("events.jsonl"), self._path(self._events_name(self.file_no)))
        except OSError:
            pass
        self.events = FileSink(self._path("events.jsonl"), "ab")
        self.offset = 0
        self._cleanup()
        self.emit("log", "INFO", "rotate", {"n": self.file_no})

    def _cleanup(self):
        old = self.file_no - self.max_files
        if old > 0:
            try:
                os.remove(self._path(self._events_name(old)))
            except OSError:
                pass

    def close(self, reason="user"):
        try:
            self.emit("sys", "INFO", "close", {"reason": reason})
        except Exception:
            pass
        self.sync(force=True)
        self.events.close()
        self.index.close()
        self._write_summary(reason)
        self._write_manifest(
            {"close": {"reason": reason, "ts": epoch_s(), "t": now_ms()}},
            running=False,
        )

    def _write_summary(self, reason):
        st = self.stats
        first = st["first_t"]
        last = st["last_t"]
        duration = 0 if first is None else (last - first) / 1000.0
        levels = ", ".join("%s=%d" % (k, st["levels"][k]) for k in LEVELS if k in st["levels"])

        lines = [
            "# %s" % self.sid,
            "",
            "- 设备: %s" % (self.device or "-"),
            "- 状态: closed",
            "- 结束原因: %s" % reason,
            "- 记录数: %d（本次运行）" % st["total"],
            "- 级别: %s" % (levels or "-"),
            "- 时长: %.1f s" % duration,
            "- 底盘丢帧: %d" % st["chassis_drop"],
            "",
            "## 最近错误",
            "",
        ]
        if st["errors"]:
            for item in st["errors"]:
                lines.append("- t=%s src=%s ev=%s m=%s" % (
                    item["t"], item["src"], item["ev"], _dumps(item["m"])))
        else:
            lines.append("无")
        lines.append("")

        try:
            with open(self._path("LOG.md"), "w") as f:
                f.write("\n".join(lines))
        except OSError:
            pass

    def _write_manifest(self, meta, running):
        path = self._path("manifest.json")
        doc = {}
        if exists(path):
            try:
                with open(path) as f:
                    doc = json.load(f)
            except Exception:
                doc = {}
        doc.setdefault("session", self.sid)
        doc.setdefault("schema", SCHEMA)
        doc.update(meta)
        doc["state"] = "running" if running else "closed"
        doc["files"] = {"events": "events.jsonl", "index": "index.jsonl"}
        doc["limits"] = {
            "rotate_bytes": self.rotate_bytes,
            "max_files": self.max_files,
            "index_every": self.index_every,
        }
        doc["stats"] = {
            "records": self.stats["total"],
            "levels": self.stats["levels"],
            "duration_ms": 0 if self.stats["first_t"] is None
            else self.stats["last_t"] - self.stats["first_t"],
            "chassis_drop": self.stats["chassis_drop"],
        }
        if not running:
            doc["files"]["summary"] = "LOG.md"
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(_dumps(doc))
        try:
            os.rename(tmp, path)
        except OSError:
            try:
                os.remove(path)
            except OSError:
                pass
            os.rename(tmp, path)
