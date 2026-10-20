"""底盘协议适配层。

真实底盘协议未知时用 MockCodec 联调；拿到抓包后只替换 codec，
runtime 不感知帧格式。

Mock 帧：AA 55 | type | len | payload | crc8
"""

import time

FRAME_HEAD = b"\xAA\x55"

MSG_HELLO = 0x01
MSG_CAPS = 0x02
MSG_TELEM = 0x03
MSG_FAULT = 0x04


def _now_ms():
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.monotonic() * 1000)


def crc8(data):
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def _s16(value):
    return value - 0x10000 if value & 0x8000 else value


class FrameCodec:
    def feed(self, buf):
        raise NotImplementedError

    def encode(self, msg_type, payload=b""):
        raise NotImplementedError


class MockCodec(FrameCodec):
    def __init__(self):
        self.buf = b""

    def feed(self, data):
        self.buf += data
        out = []
        while True:
            i = self.buf.find(FRAME_HEAD)
            if i < 0:
                # 保留可能的帧头首字节，避免逐字节到达时被误丢
                self.buf = b"\xAA" if self.buf.endswith(b"\xAA") else b""
                break
            if i > 0:
                self.buf = self.buf[i:]
            if len(self.buf) < 5:
                break
            length = self.buf[3]
            total = 5 + length
            if len(self.buf) < total:
                break
            body = self.buf[2:4 + length]
            if crc8(body) != self.buf[4 + length]:
                self.buf = self.buf[1:]
                continue
            out.append((self.buf[2], self.buf[4:4 + length]))
            self.buf = self.buf[total:]
        return out

    def encode(self, msg_type, payload=b""):
        body = bytes([msg_type, len(payload)]) + payload
        return FRAME_HEAD + body + bytes([crc8(body)])


def parse_telem(payload):
    """seq(2) v(2) w(2) flags(1) batt(1)，单位由底盘文档决定。"""
    if len(payload) < 8:
        return None
    return {
        "chassis_seq": payload[0] | (payload[1] << 8),
        "v": _s16(payload[2] | (payload[3] << 8)),
        "w": _s16(payload[4] | (payload[5] << 8)),
        "flags": payload[6],
        "batt": payload[7],
    }


class ChassisLink:
    def __init__(self, uart, codec, clock=None, timeout_ms=200):
        self.uart = uart
        self.codec = codec
        self.clock = clock or _now_ms
        self.timeout_ms = timeout_ms
        self.state = "WAIT_CAPS"
        self.caps = None
        self.last_telem = None
        self.last_rx = None
        self.last_seq = None
        self.dropped = 0

    def hello(self):
        self.uart.write(self.codec.encode(MSG_HELLO, b"\x01"))

    def poll(self):
        data = self.uart.read(64)
        if not data:
            return []
        self.last_rx = self.clock()
        events = []
        for msg_type, payload in self.codec.feed(data):
            if msg_type == MSG_CAPS:
                self.caps = payload
                self.state = "READY"
                events.append(("caps", payload))
            elif msg_type == MSG_TELEM:
                telem = parse_telem(payload)
                if telem is None:
                    continue
                seq = telem["chassis_seq"]
                if self.last_seq is not None:
                    gap = (seq - self.last_seq - 1) & 0xFFFF
                    if gap:
                        self.dropped += gap
                        events.append(("drop", gap))
                self.last_seq = seq
                self.last_telem = telem
                events.append(("telem", telem))
            elif msg_type == MSG_FAULT:
                self.state = "FAULT"
                events.append(("fault", payload))
        return events

    def timed_out(self):
        if self.last_rx is None:
            return False
        return (self.clock() - self.last_rx) > self.timeout_ms
