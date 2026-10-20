"""P0 运行时：握手、遥测降采样、事件落盘、链路超时。"""

from logcore import now_ms, sleep_ms


class Runtime:
    def __init__(self, link, journal, cfg=None, skill=None, poller=None):
        self.link = link
        self.log = journal
        self.skill = skill
        self.poller = poller
        cfg = cfg or {}
        self.loop_ms = cfg.get("loop_ms", 20)
        self.log_hz = cfg.get("log_hz", 1)
        self.device_id = cfg.get("device_id", "unknown")
        self.log_mode = cfg.get("log_mode", "periodic")
        self.log_min_ms = cfg.get("log_min_ms", 200)
        self.log_max_ms = cfg.get("log_max_ms", 60000)
        self.v_delta = cfg.get("v_delta", 10)
        self.w_delta = cfg.get("w_delta", 20)
        self.batt_delta = cfg.get("batt_delta", 1)

        self.state = "BOOT"
        self.started = now_ms()
        self.next_log = 0
        self.last_logged = None
        self.last_log_t = 0
        self.link_lost = False
        self.handshake_logged = False

    def tick(self):
        if self.poller is not None:
            self.poller.poll()

        if self.state == "BOOT":
            self.link.hello()
            self.state = "HANDSHAKE"
            self.log.emit("sys", "INFO", "boot", {"device": self.device_id})

        for kind, value in self.link.poll():
            if kind == "caps":
                self.state = "READY"
                self.log.emit("chassis", "INFO", "caps", {"bytes": len(value)})
            elif kind == "drop":
                self.log.emit("chassis", "WARN", "drop", {"n": value})
            elif kind == "fault":
                self.state = "FAULT"
                self.log.emit("chassis", "ERROR", "fault", {"code": value[0] if value else None})
            elif kind == "telem" and self.state != "FAULT":
                self.state = "READY"

        if self.state == "HANDSHAKE" and not self.handshake_logged:
            if (now_ms() - self.started) > 3000:
                self.handshake_logged = True
                self.log.emit("sys", "ERROR", "link", {"reason": "no_caps"})

        lost = self.link.timed_out()
        if lost and not self.link_lost:
            self.link_lost = True
            self.log.emit("sys", "ERROR", "link", {"reason": "uart_timeout"})
        elif not lost and self.link_lost:
            self.link_lost = False
            self.log.emit("sys", "INFO", "link", {"reason": "restored"})

        if self.state != "FAULT" and self.skill is not None:
            self.skill.tick(self.loop_ms)

        if self.state == "READY" and self.link.last_telem is not None:
            t = now_ms()
            if self._due(t, self.link.last_telem):
                self.last_log_t = t
                self.last_logged = dict(self.link.last_telem)
                self.log.emit("chassis", "INFO", "sample", self.link.last_telem)

        self.log.sync()

    def _due(self, t, telem):
        if self.log_mode != "on_change":
            if t >= self.next_log:
                period = int(1000 / self.log_hz) if self.log_hz else 1000
                self.next_log = t + period
                return True
            return False

        if self.last_logged is None:
            return True
        elapsed = t - self.last_log_t
        if elapsed < self.log_min_ms:
            return False
        if elapsed >= self.log_max_ms:
            return True
        return (
            abs(telem["v"] - self.last_logged["v"]) >= self.v_delta
            or abs(telem["w"] - self.last_logged["w"]) >= self.w_delta
            or abs(telem["batt"] - self.last_logged["batt"]) >= self.batt_delta
        )

    def run(self):
        while True:
            self.tick()
            sleep_ms(self.loop_ms)
