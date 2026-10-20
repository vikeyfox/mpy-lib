"""上位机技能包工具：打包、查看、状态查询、BLE 安装、文件回放。

用法：
    python3 tools/pkgctl.py build   ./skill --version 1.0.1 --note "降低避障阈值"
    python3 tools/pkgctl.py show    ./skill
    python3 tools/pkgctl.py status  --name bot-c3-01
    python3 tools/pkgctl.py install ./skill --name bot-c3-01
    python3 tools/pkgctl.py push    ./skill --transport replay --out update.stream

包内不生成字节码，设备侧 import 时由 MicroPython 编译。
"""

import argparse
import ast
import asyncio
import hashlib
import json
import os
import sys
import time
from contextlib import asynccontextmanager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from blelink import (  # noqa: E402
    CMD_BEGIN, CMD_COMMIT, CMD_DATA, CMD_END_FILE, CMD_FILE, CMD_INFO,
    UUID_RX, UUID_TX, FrameDecoder, encode_frame,
)

MAX_FILE = 32 * 1024
MAX_PKG = 256 * 1024
MANIFEST = "update.json"
SKIP_DIRS = {".git", "__pycache__", "node_modules"}


def iter_files(src):
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = sorted(
            d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
        )
        for name in sorted(filenames):
            if name.startswith(".") or name == MANIFEST:
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, src).replace(os.sep, "/")
            yield rel, full


def build(src, version, entry, note, kernel_min, pkg_id):
    files = []
    total = 0
    for rel, full in iter_files(src):
        with open(full, "rb") as f:
            data = f.read()
        if len(data) > MAX_FILE:
            raise SystemExit("文件过大: %s (%d > %d)" % (rel, len(data), MAX_FILE))
        if rel.endswith(".py"):
            try:
                ast.parse(data.decode("utf-8"), rel)
            except SyntaxError as exc:
                raise SystemExit("语法错误 %s:%s %s" % (rel, exc.lineno, exc.msg))
        total += len(data)
        files.append({
            "path": rel,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })

    if not files:
        raise SystemExit("目录为空: %s" % src)
    if total > MAX_PKG:
        raise SystemExit("整包过大: %d > %d" % (total, MAX_PKG))

    entry = str(entry or "main").strip()
    if entry.startswith("/") or ".." in entry.split(".") or "/" in entry:
        raise SystemExit("非法入口: %s" % entry)
    paths = {item["path"] for item in files}
    epath = entry.replace(".", "/")
    if epath + ".py" not in paths and epath + "/__init__.py" not in paths:
        raise SystemExit("入口不在包内: %s" % entry)

    manifest = {
        "id": pkg_id or os.path.basename(os.path.abspath(src)),
        "version": version,
        "entry": entry,
        "note": note,
        "kernel_min": kernel_min,
        "files": files,
    }
    with open(os.path.join(src, MANIFEST), "w") as f:
        f.write(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def load_manifest(src):
    path = os.path.join(src, MANIFEST)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def cmd_build(args):
    old = load_manifest(args.src) or {}
    manifest = build(
        args.src,
        args.version or old.get("version") or "0.0.0",
        args.entry or old.get("entry") or "main",
        args.note if args.note is not None else old.get("note", ""),
        args.kernel_min or old.get("kernel_min") or "0.1.0",
        args.id or old.get("id"),
    )
    total = sum(item["size"] for item in manifest["files"])
    print("built %s v%s: %d files, %d bytes" % (
        manifest["id"], manifest["version"], len(manifest["files"]), total))
    return 0


def cmd_show(args):
    manifest = load_manifest(args.src)
    if not manifest:
        print("缺少 %s，请先 build" % MANIFEST)
        return 1
    print("id=%s version=%s entry=%s kernel_min=%s" % (
        manifest.get("id"), manifest.get("version"),
        manifest.get("entry"), manifest.get("kernel_min")))
    if manifest.get("note"):
        print("note=%s" % manifest["note"])
    total = 0
    for item in manifest.get("files", []):
        total += item.get("size", 0)
        print("  %-40s %6d  %s" % (item["path"], item["size"], item["sha256"][:12]))
    print("files=%d bytes=%d" % (len(manifest.get("files", [])), total))
    return 0


def iter_stream(manifest, src, chunk):
    """生成完整更新流，供文件回放与测试使用。"""
    yield encode_frame(CMD_BEGIN, json.dumps(manifest).encode())
    for item in manifest["files"]:
        path = item["path"]
        yield encode_frame(CMD_FILE, json.dumps({"path": path}).encode())
        with open(os.path.join(src, path), "rb") as f:
            while True:
                buf = f.read(chunk)
                if not buf:
                    break
                yield encode_frame(CMD_DATA, buf)
        yield encode_frame(CMD_END_FILE)
    yield encode_frame(CMD_COMMIT)


def push_replay(manifest, src, out, chunk):
    count = 0
    with open(out, "wb") as f:
        for frame in iter_stream(manifest, src, chunk):
            f.write(frame)
            count += 1
    print("wrote %d frames -> %s" % (count, out))
    return 0


class BleChannel:
    def __init__(self, client, rx_uuid, tx_uuid):
        self.client = client
        self.rx_uuid = rx_uuid
        self.tx_uuid = tx_uuid
        self.decoder = FrameDecoder()
        self.replies = []

    def on_notify(self, _handle, data):
        for _ctype, payload in self.decoder.feed(bytes(data)):
            try:
                self.replies.append(json.loads(payload[1:].decode()))
            except Exception:
                pass

    async def send(self, frame, expect=None, timeout=20):
        await self.client.write_gatt_char(self.rx_uuid, frame, response=True)
        if expect is None:
            return None
        reply = await self.wait(expect, timeout)
        return reply

    async def wait(self, cmd, timeout):
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            for i, item in enumerate(self.replies):
                if item.get("cmd") == cmd:
                    self.replies.pop(i)
                    return item
            if asyncio.get_event_loop().time() >= deadline:
                raise SystemExit("等待 cmd=0x%02X 回复超时" % cmd)
            await asyncio.sleep(0.02)


def _check(reply):
    if reply is None:
        return
    if not reply.get("ok", False):
        raise SystemExit("设备拒绝: %s" % reply.get("err", "unknown"))


def check_installed(info, version):
    """判断设备是否真正切到目标版本并完成确认。"""
    if info.get("pending"):
        return False, "设备已接收，等待安全点切换"
    if info.get("version") != version:
        return False, "当前版本 %s，未切到 %s（可能已回滚）" % (
            info.get("version"), version)
    app = info.get("app") or {}
    if app.get("error"):
        return False, "技能异常: %s" % app["error"]
    return True, "已确认版本 %s" % version


def format_info(info):
    lines = ["slot=%s version=%s pending=%s bootcnt=%s kernel=%s" % (
        info.get("slot"), info.get("version"), info.get("pending"),
        info.get("bootcnt"), info.get("kernel"))]
    app = info.get("app") or {}
    if app:
        lines.append("app: slot=%s version=%s failures=%s healthy_ms=%s error=%s" % (
            app.get("slot"), app.get("version"), app.get("failures"),
            app.get("healthy_ms"), app.get("error")))
    return "\n".join(lines)


@asynccontextmanager
async def ble_channel(name, address, timeout):
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError:
        raise SystemExit("BLE 传输需要 bleak：pip install bleak")

    if address is None:
        devices = await BleakScanner.discover(timeout=5)
        hit = next((d for d in devices if d.name == name), None)
        if hit is None:
            raise SystemExit("未发现设备: %s" % name)
        address = hit.address

    async with BleakClient(address, timeout=timeout) as client:
        channel = BleChannel(client, UUID_RX, UUID_TX)
        await client.start_notify(UUID_TX, channel.on_notify)
        yield client, channel


async def read_info(channel, timeout):
    info = await channel.send(encode_frame(CMD_INFO), expect=CMD_INFO, timeout=timeout)
    _check(info)
    return info


async def push_ble(manifest, src, name, address, chunk, timeout, confirm_timeout=0):
    total = sum(item["size"] for item in manifest["files"])
    started = time.monotonic()

    async with ble_channel(name, address, timeout) as (client, channel):
        info = await read_info(channel, timeout)
        print("device: %s" % format_info(info))

        reply = await channel.send(
            encode_frame(CMD_BEGIN, json.dumps(manifest).encode()),
            expect=CMD_BEGIN, timeout=timeout)
        _check(reply)
        print("begin: %d files, %d bytes" % (reply.get("files", 0), total))

        mtu = int(getattr(client, "mtu_size", 23) or 23)
        size = max(8, min(chunk, mtu - 9))  # 扣除 ATT 与 6 字节帧头
        sent = 0
        for item in manifest["files"]:
            path = item["path"]
            reply = await channel.send(
                encode_frame(CMD_FILE, json.dumps({"path": path}).encode()),
                expect=CMD_FILE, timeout=timeout)
            _check(reply)
            with open(os.path.join(src, path), "rb") as f:
                while True:
                    buf = f.read(size)
                    if not buf:
                        break
                    await channel.send(encode_frame(CMD_DATA, buf), expect=None)
                    sent += len(buf)
            reply = await channel.send(
                encode_frame(CMD_END_FILE), expect=CMD_END_FILE, timeout=timeout)
            _check(reply)
            print("  %-40s %6d ok" % (path, item["size"]))

        reply = await channel.send(
            encode_frame(CMD_COMMIT), expect=CMD_COMMIT, timeout=timeout)
        _check(reply)
        print("commit: slot=%s %d/%d bytes, %.1fs" % (
            reply.get("slot"), sent, total, time.monotonic() - started))

        if not confirm_timeout:
            print("设备会在安全点切换；保持上电，健康运行 5 s 后自动确认。")
            return 0

        print("等待设备确认（安全点切换 + 5 s 健康运行）...")
        deadline = asyncio.get_running_loop().time() + confirm_timeout
        while True:
            info = await read_info(channel, timeout)
            ok, msg = check_installed(info, manifest["version"])
            if ok:
                print(msg)
                return 0
            if info.get("version") != manifest["version"] and not info.get("pending"):
                raise SystemExit("安装失败: " + msg)
            if asyncio.get_running_loop().time() >= deadline:
                raise SystemExit("等待确认超时: " + msg)
            await asyncio.sleep(1)


async def status_ble(name, address, timeout, as_json):
    async with ble_channel(name, address, timeout) as (_client, channel):
        info = await read_info(channel, timeout)
        if as_json:
            print(json.dumps(info, ensure_ascii=False, indent=2))
        else:
            print(format_info(info))
    return 0


def cmd_push(args):
    old = load_manifest(args.src) or {}
    manifest = build(
        args.src,
        args.version or old.get("version") or "0.0.0",
        args.entry or old.get("entry") or "main",
        args.note if args.note is not None else old.get("note", ""),
        args.kernel_min or old.get("kernel_min") or "0.1.0",
        args.id or old.get("id"),
    )
    if args.transport == "replay":
        return push_replay(manifest, args.src, args.out, args.chunk)
    return asyncio.run(push_ble(
        manifest, args.src, args.name, args.address, args.chunk, args.timeout))


def cmd_install(args):
    old = load_manifest(args.src) or {}
    version = args.version or old.get("version")
    if not version:
        raise SystemExit("安装需要 --version，例如 --version 1.0.1")
    manifest = build(
        args.src,
        version,
        args.entry or old.get("entry") or "main",
        args.note if args.note is not None else old.get("note", ""),
        args.kernel_min or old.get("kernel_min") or "0.1.0",
        args.id or old.get("id"),
    )
    if args.transport == "replay":
        return push_replay(manifest, args.src, args.out, args.chunk)
    wait = 0 if args.no_wait else args.confirm_timeout
    return asyncio.run(push_ble(
        manifest, args.src, args.name, args.address, args.chunk,
        args.timeout, confirm_timeout=wait))


def cmd_status(args):
    return asyncio.run(status_ble(args.name, args.address, args.timeout, args.json))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    def pkg_args(p):
        p.add_argument("src")
        p.add_argument("--version")
        p.add_argument("--entry")
        p.add_argument("--note")
        p.add_argument("--kernel-min")
        p.add_argument("--id")

    def ble_args(p):
        p.add_argument("--name", default="bot-c3-01")
        p.add_argument("--address")
        p.add_argument("--chunk", type=int, default=180)
        p.add_argument("--timeout", type=int, default=20)

    p = sub.add_parser("build")
    pkg_args(p)
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("show")
    p.add_argument("src")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("push")
    pkg_args(p)
    p.add_argument("--transport", choices=("ble", "replay"), default="ble")
    p.add_argument("--out", default="update.stream")
    ble_args(p)
    p.set_defaults(func=cmd_push)

    p = sub.add_parser("install")
    pkg_args(p)
    p.add_argument("--transport", choices=("ble", "replay"), default="ble")
    p.add_argument("--out", default="update.stream")
    p.add_argument("--no-wait", action="store_true", help="下发后不等待确认")
    p.add_argument("--confirm-timeout", type=int, default=60)
    ble_args(p)
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("status")
    p.add_argument("--name", default="bot-c3-01")
    p.add_argument("--address")
    p.add_argument("--timeout", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
