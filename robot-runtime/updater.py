"""技能包更新器：分块接收、sha256 校验、语法检查、A/B 切换与回滚。

不依赖 BLE 传输：BLE/UART/文件回放都只需依次调用
begin -> begin_file -> write -> end_file -> commit。

槽位布局（base 可为 "/" 或测试用临时目录）：
    <base>/app_a/、<base>/app_b/、<base>/app_stage/
    <base>/current.json
"""

import hashlib
import json
import os

STATE_IDLE = "idle"
STATE_RECEIVING = "receiving"


class UpdateError(Exception):
    pass


def _is_dir(path):
    try:
        os.listdir(path)
        return True
    except OSError:
        return False


def _rmtree(path):
    if not _is_dir(path):
        return
    try:
        names = os.listdir(path)
    except OSError:
        return
    for name in names:
        child = path + "/" + name
        if _is_dir(child):
            _rmtree(child)
        else:
            try:
                os.remove(child)
            except OSError:
                pass
    try:
        os.rmdir(path)
    except OSError:
        pass


def _mkdirs(path):
    if path in ("", "/"):
        return
    cur = "/" if path.startswith("/") else ""
    for part in [p for p in path.split("/") if p]:
        if cur.endswith("/"):
            cur = cur + part
        elif cur:
            cur = cur + "/" + part
        else:
            cur = part
        try:
            os.mkdir(cur)
        except OSError:
            pass


def _read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(json.dumps(obj))
    try:
        os.rename(tmp, path)
    except OSError:
        try:
            os.remove(path)
        except OSError:
            pass
        os.rename(tmp, path)


def _check_path(path):
    if not path or path.startswith("/") or "\\" in path:
        raise UpdateError("非法路径: %s" % path)
    for part in path.split("/"):
        if part in ("", ".", ".."):
            raise UpdateError("非法路径: %s" % path)


class SkillUpdater:
    def __init__(self, base="/"):
        self.base = base.rstrip("/") or "/"
        self.stage = self.base + "/app_stage"
        self.pointer = self.base + "/current.json"
        self.state = STATE_IDLE
        self.manifest = None
        self.expected = {}
        self.done = {}
        self.fh = None
        self.cur_path = None
        self.cur_size = 0
        self.cur_hash = None

    def _slot(self, name):
        return self.base + "/" + name

    def current(self):
        return _read_json(self.pointer)

    def begin(self, manifest):
        if self.state != STATE_IDLE:
            raise UpdateError("已有更新在进行")
        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise UpdateError("manifest.files 为空")
        expected = {}
        for item in files:
            path = item.get("path")
            _check_path(path)
            size = int(item.get("size", -1))
            digest = str(item.get("sha256", "")).lower()
            if size < 0 or len(digest) != 64:
                raise UpdateError("文件描述无效: %s" % path)
            if path in expected:
                raise UpdateError("重复文件: %s" % path)
            expected[path] = (size, digest)

        _rmtree(self.stage)
        _mkdirs(self.stage)
        self.manifest = manifest
        self.expected = expected
        self.done = {}
        self.entry = self._entry(manifest)
        entry_path = self.entry.replace(".", "/")
        if (entry_path + ".py" not in expected
                and entry_path + "/__init__.py" not in expected):
            raise UpdateError("入口不在包内: %s" % self.entry)
        self.state = STATE_RECEIVING

    @staticmethod
    def _entry(manifest):
        entry = str(manifest.get("entry", "main")).strip()
        if not entry or entry.startswith("/"):
            raise UpdateError("非法入口: %s" % entry)
        for part in entry.split("."):
            if part in ("", ".", ".."):
                raise UpdateError("非法入口: %s" % entry)
        return entry

    def begin_file(self, path):
        if self.state != STATE_RECEIVING:
            raise UpdateError("未开始更新")
        if self.fh is not None:
            raise UpdateError("上一个文件未结束")
        if path not in self.expected:
            raise UpdateError("未声明的文件: %s" % path)
        size, digest = self.expected[path]
        full = self.stage + "/" + path
        parent = full.rsplit("/", 1)[0]
        _mkdirs(parent)
        self.fh = open(full, "ab")
        self.cur_path = path
        self.cur_size = 0
        self.cur_hash = hashlib.sha256()
        self.cur_expected = (size, digest)

    def write(self, chunk):
        if self.fh is None:
            raise UpdateError("当前没有打开的文件")
        if not isinstance(chunk, (bytes, bytearray)):
            raise UpdateError("chunk 必须是 bytes")
        limit = self.cur_expected[0]
        if self.cur_size + len(chunk) > limit:
            raise UpdateError("文件超出声明大小: %s" % self.cur_path)
        self.fh.write(chunk)
        self.cur_hash.update(chunk)
        self.cur_size += len(chunk)

    def end_file(self):
        if self.fh is None:
            raise UpdateError("当前没有打开的文件")
        path = self.cur_path
        full = self.stage + "/" + path
        self.fh.flush()
        self.fh.close()
        self.fh = None

        size, digest = self.cur_expected
        if self.cur_size != size:
            raise UpdateError("大小不符: %s" % path)
        if self.cur_hash.hexdigest() != digest:
            raise UpdateError("哈希不符: %s" % path)

        if path.endswith(".py"):
            try:
                with open(full) as f:
                    source = f.read()
                compile(source, path, "exec")
            except Exception as exc:
                raise UpdateError("语法错误 %s: %s" % (path, exc))
        self.done[path] = True
        self.cur_path = None

    def abort(self):
        if self.fh is not None:
            try:
                self.fh.close()
            except Exception:
                pass
        self.fh = None
        _rmtree(self.stage)
        self.manifest = None
        self.expected = {}
        self.done = {}
        self.state = STATE_IDLE

    def commit(self):
        if self.state != STATE_RECEIVING:
            raise UpdateError("未开始更新")
        if self.fh is not None:
            raise UpdateError("还有文件未结束")
        if len(self.done) != len(self.expected):
            raise UpdateError("文件未全部接收")

        doc = self.current() or {}
        cur = doc.get("slot")
        if cur == "app_a":
            target = "app_b"
        else:
            target = "app_a"
        slot_path = self._slot(target)
        _rmtree(slot_path)
        os.rename(self.stage, slot_path)

        _write_json(self.pointer, {
            "slot": target,
            "prev": cur,
            "pending": True,
            "bootcnt": 0,
            "id": self.manifest.get("id"),
            "version": self.manifest.get("version"),
            "entry": self.entry,
            "note": self.manifest.get("note"),
            "kernel_min": self.manifest.get("kernel_min"),
            "files": self.manifest.get("files"),
        })
        self.state = STATE_IDLE
        return target

    def confirm(self):
        """新版本运行健康后调用，清除 pending 与 bootcnt。"""
        doc = self.current()
        if not doc:
            return
        doc["pending"] = False
        doc["bootcnt"] = 0
        _write_json(self.pointer, doc)

    def rollback(self):
        doc = self.current() or {}
        prev = doc.get("prev")
        if not prev or not _is_dir(self._slot(prev)):
            raise UpdateError("没有可回滚的槽位")
        doc["slot"] = prev
        doc["prev"] = None
        doc["pending"] = False
        doc["bootcnt"] = 0
        _write_json(self.pointer, doc)
        return prev

    def boot_select(self):
        """启动时调用：返回应加载的槽位名；连续 3 次未确认则回滚。"""
        doc = self.current()
        if not doc:
            return None
        if doc.get("pending"):
            if int(doc.get("bootcnt", 0)) >= 3:
                try:
                    return self.rollback()
                except UpdateError:
                    pass
            doc["bootcnt"] = int(doc.get("bootcnt", 0)) + 1
            _write_json(self.pointer, doc)
        return doc.get("slot")

    def slot_path(self, name=None):
        if name is None:
            doc = self.current() or {}
            name = doc.get("slot")
        if not name:
            return None
        return self._slot(name)
