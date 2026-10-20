"""P0 入口：配置 -> 会话 -> 底盘链路 -> 运行时。"""

import json
import time

from board import make_uart
from chassis import ChassisLink, MockCodec
from logcore import Session, now_ms
from runtime import Runtime


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
    rt = Runtime(link, journal, rt_cfg)

    try:
        rt.run()
    except KeyboardInterrupt:
        journal.close("user")
    except Exception:
        journal.close("crash")
        raise


main()
