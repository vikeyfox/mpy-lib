"""设备侧技能包接收端。

UpdateServer 与传输无关，可在主机侧直接测试；
BleUpdatePeripheral 只在设备上实例化（依赖 MicroPython bluetooth 模块）。

帧格式：AA 55 | type(1) | len(2, 小端) | payload | crc8(type+len+payload)
"""

import json

from chassis import crc8
from updater import UpdateError

FRAME_HEAD = b"\xAA\x55"

CMD_INFO = 0x10
CMD_BEGIN = 0x20
CMD_FILE = 0x21
CMD_DATA = 0x22
CMD_END_FILE = 0x23
CMD_COMMIT = 0x24
CMD_ABORT = 0x25
CMD_CONFIRM = 0x26
CMD_ROLLBACK = 0x27
REPLY = 0x80

NOTIFY_CHUNK = 20  # 未协商 MTU 时的安全长度

UUID_SERVICE = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UUID_RX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
UUID_TX = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"


def encode_frame(msg_type, payload=b""):
    if len(payload) > 65535:
        raise ValueError("payload 过长")
    body = bytes([msg_type, len(payload) & 0xFF, (len(payload) >> 8) & 0xFF]) + payload
    return FRAME_HEAD + body + bytes([crc8(body)])


class FrameDecoder:
    def __init__(self):
        self.buf = b""

    def feed(self, data):
        self.buf += data
        out = []
        while True:
            i = self.buf.find(FRAME_HEAD)
            if i < 0:
                self.buf = b"\xAA" if self.buf.endswith(b"\xAA") else b""
                break
            if i > 0:
                self.buf = self.buf[i:]
            if len(self.buf) < 6:
                break
            length = self.buf[3] | (self.buf[4] << 8)
            total = 6 + length
            if len(self.buf) < total:
                break
            body = self.buf[2:5 + length]
            if crc8(body) != self.buf[5 + length]:
                self.buf = self.buf[1:]
                continue
            out.append((self.buf[2], self.buf[5:5 + length]))
            self.buf = self.buf[total:]
        return out


def _reply(cmd, obj=None, err=None):
    doc = {"cmd": cmd, "ok": err is None}
    if err is not None:
        doc["err"] = err
    elif obj is not None:
        doc.update(obj)
    payload = json.dumps(doc).encode()
    # 单条回复控制在 1 KB 内，超长时退化为错误回复
    if len(payload) > 1000:
        payload = json.dumps({"cmd": cmd, "ok": False, "err": "reply_too_large"}).encode()
    return encode_frame(REPLY, bytes([cmd, 0 if err is None else 1]) + payload)


def _version_tuple(text):
    out = []
    for part in str(text or "0").split("."):
        digits = ""
        for ch in part:
            if ch.isdigit():
                digits += ch
            else:
                break
        out.append(int(digits or 0))
    return tuple(out)


def _kernel_ok(required, current):
    if not required:
        return True
    return _version_tuple(required) <= _version_tuple(current)


class UpdateServer:
    """把 BLE 帧翻译为 SkillUpdater 调用，不关心底层是 BLE 还是串口。"""

    def __init__(self, updater, kernel_version="0.1.0"):
        self.updater = updater
        self.kernel_version = kernel_version
        self.decoder = FrameDecoder()

    def feed(self, data):
        replies = []
        for ctype, payload in self.decoder.feed(data):
            replies.append(self.handle(ctype, payload))
        return replies

    def handle(self, ctype, payload):
        try:
            if ctype == CMD_INFO:
                return _reply(ctype, self._info())
            if ctype == CMD_BEGIN:
                manifest = json.loads(payload.decode())
                if not isinstance(manifest, dict):
                    raise UpdateError("manifest 必须是对象")
                required = manifest.get("kernel_min")
                if not _kernel_ok(required, self.kernel_version):
                    raise UpdateError("需要内核 %s，当前 %s" % (required, self.kernel_version))
                self.updater.begin(manifest)
                return _reply(ctype, {"files": len(manifest.get("files", []))})
            if ctype == CMD_FILE:
                doc = json.loads(payload.decode())
                self.updater.begin_file(doc.get("path"))
                return _reply(ctype, {"path": doc.get("path")})
            if ctype == CMD_DATA:
                self.updater.write(payload)
                return _reply(ctype, {"n": len(payload)})
            if ctype == CMD_END_FILE:
                self.updater.end_file()
                return _reply(ctype, {"done": len(self.updater.done)})
            if ctype == CMD_COMMIT:
                slot = self.updater.commit()
                return _reply(ctype, {"slot": slot, "pending": True})
            if ctype == CMD_ABORT:
                self.updater.abort()
                return _reply(ctype, {"state": "idle"})
            if ctype == CMD_CONFIRM:
                self.updater.confirm()
                return _reply(ctype, self._info())
            if ctype == CMD_ROLLBACK:
                slot = self.updater.rollback()
                return _reply(ctype, {"slot": slot})
            return _reply(ctype, err="unknown_cmd")
        except Exception as exc:
            return _reply(ctype, err=str(exc))

    def _info(self):
        doc = self.updater.current() or {}
        return {
            "slot": doc.get("slot"),
            "version": doc.get("version"),
            "id": doc.get("id"),
            "entry": doc.get("entry"),
            "pending": bool(doc.get("pending")),
            "bootcnt": doc.get("bootcnt", 0),
            "kernel": self.kernel_version,
        }


def _uuid_bytes(text):
    return bytes(reversed(bytes.fromhex(text.replace("-", ""))))


class BleUpdatePeripheral:
    """NUS 风格 GATT：RX 接收上位机写入，TX 通知回复。"""

    def __init__(self, server, name="bot-c3-01"):
        import bluetooth

        self.server = server
        self.name = name
        self.conn = None
        self._rx = bytearray(4096)
        self._rx_len = 0
        self._rx_pending = False
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq)

        service = (
            bluetooth.UUID(UUID_SERVICE),
            (
                (bluetooth.UUID(UUID_RX),
                 bluetooth.FLAG_WRITE | bluetooth.FLAG_WRITE_NO_RESPONSE),
                (bluetooth.UUID(UUID_TX), bluetooth.FLAG_NOTIFY),
            ),
        )
        ((self.rx, self.tx),) = self.ble.gatts_register_services((service,))
        try:
            self.ble.gatts_set_buffer(self.rx, 512, False)
        except Exception:
            pass
        self.advertise()

    def _irq(self, event, data):
        if event == 1:  # central 连接
            self.conn = data[0]
        elif event == 2:  # 断开后继续广播，方便重连续传
            self.conn = None
            self.advertise()
        elif event == 3:  # GATTS 写入：只拷贝到预分配缓冲，落盘留给主循环
            conn, attr, value = data
            if attr == self.rx and conn == self.conn:
                n = len(value)
                if self._rx_len + n <= len(self._rx):
                    self._rx[self._rx_len:self._rx_len + n] = value
                    self._rx_len += n
                    self._rx_pending = True
                else:
                    # 溢出说明主循环阻塞过久，丢弃整段让上位机重传
                    self._rx_len = 0
                    self._rx_pending = False

    def poll(self):
        """由主循环调用；中断里不做文件 I/O 与哈希计算。"""
        if not self._rx_pending:
            return
        data = bytes(self._rx[:self._rx_len])
        self._rx_len = 0
        self._rx_pending = False
        for frame in self.server.feed(data):
            self._send(frame)

    def _send(self, frame):
        if self.conn is None:
            return
        for i in range(0, len(frame), NOTIFY_CHUNK):
            try:
                self.ble.gatts_notify(self.conn, self.tx, frame[i:i + NOTIFY_CHUNK])
            except Exception:
                break

    def advertise(self):
        name = self.name.encode()[:29]
        svc = _uuid_bytes(UUID_SERVICE)
        # 广播包只放 flags + 128 位服务，名字放扫描响应，避免超过 31 字节
        adv = bytearray(b"\x02\x01\x06")
        adv += bytes([len(svc) + 1, 0x07]) + svc
        resp = bytes([len(name) + 1, 0x09]) + name
        try:
            self.ble.gap_advertise(100000, adv_data=bytes(adv), resp_data=resp)
        except Exception:
            pass

    def close(self):
        try:
            self.ble.active(False)
        except Exception:
            pass
