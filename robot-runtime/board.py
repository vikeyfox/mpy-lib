"""板级初始化：引脚与 UART 只在这里出现，便于从 C3 迁移到 S3。"""


def make_uart(cfg):
    from machine import UART

    u = cfg.get("uart", {})
    kwargs = {"baudrate": u.get("baud", 115200)}
    if u.get("tx") is not None:
        kwargs["tx"] = u["tx"]
    if u.get("rx") is not None:
        kwargs["rx"] = u["rx"]
    return UART(u.get("id", 1), **kwargs)


def make_led(cfg):
    from machine import Pin

    pin = cfg.get("led")
    if pin is None:
        return None
    return Pin(pin, Pin.OUT)
