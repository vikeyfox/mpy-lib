"""P0 入口：配置 -> 会话 -> 底盘链路 -> 技能槽位 -> 运行时。"""

import json
import time

from board import make_uart
from chassis import ChassisLink, MockCodec
from logcore import Session, ensure_dir, now_ms
from runtime import Runtime
from skills import SkillContext, SkillHost
from updater import SkillUpdater


def load_config(path="config.json"):
    with open(path) as f:
        return json.load(f)


def new_session_id():
    try:
        t = time.localtime()
        if t[0] >= 2020:
            return "S%04d%02d%02d-%02d%02d%02d" % (t[0], t[1], t[2], t[3], t[4], t[5])
    except Exception:
        pass
    return "Sboot-%d" % now_ms()


def main():
    cfg = load_config()
    journal = Session(
        cfg["log"]["root"],
        new_session_id(),
        {"device": {"id": cfg.get("device_id"), "platform": "esp32-c3"}},
        cfg["log"],
    )

    uart = make_uart(cfg)
    # TODO: 拿到底盘抓包后替换 MockCodec，runtime 无需改动
    link = ChassisLink(uart, MockCodec(), timeout_ms=cfg["runtime"].get("chassis_timeout_ms", 200))

    rt_cfg = dict(cfg["runtime"])
    rt_cfg["device_id"] = cfg.get("device_id")

    updater = SkillUpdater("/")
    ctx = SkillContext(journal, link, cfg)
    ensure_dir("/STATE")
    host = SkillHost(updater, ctx, state_dir="/STATE")

    ble = None
    ble_cfg = cfg.get("ble") or {}
    if ble_cfg.get("enabled"):
        try:
            from blelink import BleUpdatePeripheral, UpdateServer

            ble = BleUpdatePeripheral(
                UpdateServer(updater),
                ble_cfg.get("name", cfg.get("device_id", "bot-c3-01")),
            )
        except Exception as exc:
            # 模式互斥或协议栈未就绪时降级为纯串口运行
            journal.emit("sys", "WARN", "ble", {"err": str(exc)})

    rt = Runtime(link, journal, rt_cfg, skill=host, poller=ble)

    # 没有底盘遥测时视为静止，便于台架首次安装技能
    ctx.safe_check = lambda: (
        rt.state != "FAULT"
        and not link.timed_out()
        and (link.last_telem is None
             or (link.last_telem.get("v") == 0 and link.last_telem.get("w") == 0))
    )

    try:
        host.load()
    except Exception:
        journal.emit("app", "ERROR", "reload", {"stage": "boot"})

    try:
        rt.run()
    except KeyboardInterrupt:
        journal.close("user")
    except Exception:
        journal.close("crash")
        raise


main()
