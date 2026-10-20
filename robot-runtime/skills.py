"""技能加载与安全点热重载。

契约（见 docs/debug-log-system.md 8.5）：
    setup(ctx) -> None
    step(dt_ms) -> None
    teardown() -> None
    snapshot() -> dict      # 可选
    restore(state) -> None  # 可选

槽位目录即 sys.path 根，入口模块默认 main。
"""

import json
import os
import sys

from logcore import now_ms

HEALTH_MS = 5000
MAX_FAILURES = 3


class SkillError(Exception):
    pass


def _import_entry(entry):
    mod = __import__(entry)
    for part in entry.split(".")[1:]:
        mod = getattr(mod, part)
    return mod


def _purge(base):
    """删除从该槽位导入的所有模块，避免旧代码遮蔽新代码。"""
    for name in list(sys.modules):
        if name == "__main__":
            continue
        mod = sys.modules.get(name)
        path = getattr(mod, "__file__", None)
        if path and path.startswith(base + "/"):
            try:
                del sys.modules[name]
            except KeyError:
                pass


def _purge_entry(entry):
    top = entry.split(".")[0]
    if top != "__main__" and top in sys.modules:
        try:
            del sys.modules[top]
        except KeyError:
            pass


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


class SkillContext:
    """技能唯一入口。技能不直接持有 UART / 文件句柄，跨版本资源由这里提供。"""

    def __init__(self, journal, link, cfg=None):
        self.journal = journal
        self.link = link
        self.cfg = cfg or {}
        self.params = {}
        self.slot = None
        self.version = None
        self.safe_check = None
        self.started = now_ms()

    def emit(self, ev, m=None, lvl="INFO", q="ok", src="app"):
        return self.journal.emit(src, lvl, ev, m, q)

    def telemetry(self):
        return self.link.last_telem or {}

    def drive(self, v, w):
        return self.link.drive(v, w)

    def stop(self):
        return self.link.stop()

    def param(self, key, default=None):
        return self.params.get(key, default)

    def elapsed_ms(self):
        return now_ms() - self.started

    def safe_to_reload(self):
        if self.safe_check is not None:
            try:
                return bool(self.safe_check())
            except Exception:
                return False
        telem = self.link.last_telem
        if telem is None:
            return False
        return telem.get("v") == 0 and telem.get("w") == 0


class SkillHost:
    """负责加载、运行、健康确认与失败回滚。"""

    def __init__(self, updater, ctx, state_dir=None):
        self.updater = updater
        self.ctx = ctx
        self.state_dir = state_dir
        self.mod = None
        self.slot = None
        self.base = None
        self.failures = 0
        self.healthy_ms = 0
        self.last_error = None
        self._failed_token = None

    def status(self):
        return {
            "slot": self.slot,
            "version": self.ctx.version,
            "failures": self.failures,
            "healthy_ms": self.healthy_ms,
            "error": self.last_error,
        }

    def _unload(self):
        if self.mod is not None:
            teardown = getattr(self.mod, "teardown", None)
            if teardown is not None:
                try:
                    teardown()
                except Exception as exc:
                    self.ctx.emit("reload", {"stage": "teardown", "err": str(exc)}, "ERROR")
        self.mod = None
        self.healthy_ms = 0
        self.failures = 0
        if self.base is not None:
            try:
                sys.path.remove(self.base)
            except ValueError:
                pass
            _purge(self.base)
            self.base = None

    def _load_params(self, base):
        self.ctx.params = {}
        try:
            with open(base + "/params.json") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.ctx.params = data
        except Exception:
            pass

    def _save_state(self, state):
        if not self.state_dir:
            return
        try:
            with open(self.state_dir + "/state.json", "w") as f:
                f.write(json.dumps(state))
        except Exception:
            pass

    def load(self, slot=None, allow_rollback=True):
        """加载指定槽位；slot 为空时按 current.json 选择。"""
        state = {}
        if self.mod is not None:
            snapshot = getattr(self.mod, "snapshot", None)
            if snapshot is not None:
                try:
                    state = snapshot() or {}
                except Exception as exc:
                    self.ctx.emit("reload", {"stage": "snapshot", "err": str(exc)}, "ERROR")
                    state = {}
        self._unload()

        if slot is None:
            slot = self.updater.boot_select()
        if not slot:
            return False

        base = self.updater.slot_path(slot)
        if not base:
            return False
        doc = self.updater.current() or {}
        entry = doc.get("entry") or "main"
        entry_file = base + "/" + entry.replace(".", "/") + ".py"
        if not _exists(entry_file) and not _exists(entry_file[:-3] + "/__init__.py"):
            self.last_error = "入口不存在: %s" % entry_file
            self.ctx.emit("reload", {"stage": "entry", "slot": slot,
                                     "err": self.last_error}, "CRIT")
            if allow_rollback:
                new_slot = self._rollback(slot)
                if new_slot:
                    return self.load(slot=new_slot, allow_rollback=False)
            return False

        self.base = base
        sys.path.insert(0, base)
        try:
            self._load_params(base)
            _purge_entry(entry)
            mod = _import_entry(entry)
            setup = getattr(mod, "setup", None)
            step = getattr(mod, "step", None)
            if setup is None or step is None:
                raise SkillError("入口 %s 缺少 setup/step" % entry)
            setup(self.ctx)
            restore = getattr(mod, "restore", None)
            if restore is not None and state:
                restore(state)
        except Exception as exc:
            self.last_error = str(exc)
            self.ctx.emit("reload", {
                "stage": "setup", "slot": slot, "entry": entry, "err": str(exc),
            }, "CRIT")
            self._unload()
            if allow_rollback:
                new_slot = self._rollback(slot)
                if new_slot:
                    return self.load(slot=new_slot, allow_rollback=False)
            return False

        self.mod = mod
        self.slot = slot
        self.ctx.slot = slot
        self.ctx.version = doc.get("version")
        self.healthy_ms = 0
        self.failures = 0
        self._save_state(state)
        self.ctx.emit("reload", {
            "slot": slot, "version": doc.get("version"), "entry": entry,
        }, "INFO")
        return True

    def _rollback(self, from_slot):
        doc = self.updater.current() or {}
        if not doc.get("prev"):
            return None
        try:
            new_slot = self.updater.rollback()
        except Exception as exc:
            self.last_error = str(exc)
            return None
        self.ctx.emit("reload", {
            "stage": "rollback", "from": from_slot, "to": new_slot,
        }, "WARN")
        return new_slot

    def _recover(self):
        failed = self.slot
        self._unload()
        new_slot = self._rollback(failed)
        if new_slot:
            self.load(slot=new_slot, allow_rollback=False)

    def maybe_apply(self):
        """有 pending 版本且当前处于安全点时切换。"""
        doc = self.updater.current() or {}
        slot = doc.get("slot")
        if not (doc.get("pending") and slot and slot != self.slot):
            return
        token = (slot, doc.get("version"))
        if token == self._failed_token:
            return
        # 尚未加载任何技能时不存在运行中的动作，可直接应用
        if self.slot is None or self.ctx.safe_to_reload():
            if not self.load(slot=slot, allow_rollback=True):
                self._failed_token = token

    def tick(self, dt_ms):
        self.maybe_apply()
        if self.mod is None:
            return

        try:
            self.mod.step(dt_ms)
        except Exception as exc:
            self.failures += 1
            self.last_error = str(exc)
            self.ctx.emit("reload", {
                "stage": "step", "slot": self.slot, "err": str(exc), "n": self.failures,
            }, "ERROR")
            if self.failures >= MAX_FAILURES:
                self._recover()
            return

        self.healthy_ms += dt_ms
        self.failures = 0
        doc = self.updater.current() or {}
        if (doc.get("pending") and self.slot == doc.get("slot")
                and self.healthy_ms >= HEALTH_MS):
            self.updater.confirm()
            self.ctx.emit("reload", {
                "stage": "confirm", "slot": self.slot, "version": doc.get("version"),
            }, "INFO")
