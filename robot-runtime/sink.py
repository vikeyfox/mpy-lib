"""P0 输出通道：文件 sink 与空 sink。

P1 再增加 SDSink / NetSink，接口保持不变。
"""


class FileSink:
    def __init__(self, path, mode="ab"):
        self.path = path
        self.fh = open(path, mode)

    def write(self, buf):
        return self.fh.write(buf)

    def sync(self):
        try:
            self.fh.flush()
        except Exception:
            pass

    def close(self):
        try:
            self.fh.flush()
            self.fh.close()
        except Exception:
            pass


class NullSink:
    """用于压测或关闭落盘，接口与 FileSink 一致。"""

    def write(self, buf):
        return len(buf)

    def sync(self):
        pass

    def close(self):
        pass
