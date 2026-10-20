# MicroPython 机器人运行时 · 调试采集、解释层与更新系统

> 版本：v1.5  
> 适用范围：机器人 / 嵌入式设备的调试、行为解释与在线迭代；也适用于老化测试与现场问题复现  
> 大脑平台：ESP32-C3（基础版）/ ESP32-S3（进阶），运行 MicroPython  
> 目标平台：ESP32 / ESP32-S3 / ESP8266 / RP2040 / RP2350 / STM32 / SAMD / nRF 等具备 `machine` 模块的 MCU

---

## 1. 概述

### 1.1 要解决的问题

嵌入式设备出问题时，通常只能看到串口打印，缺少：

- 结构化、可回溯的历史数据；
- 掉电后仍然保留的现场；
- 能被人和智能体直接理解的数据格式；
- 不依赖调试线缆的取数方式；
- 机器人做决策时的依据，事后只能靠猜；
- 改一行逻辑就要重新编译、烧录的迭代效率。

本方案构建一套「采集 → 缓冲 → 落盘 → 交付」的调试日志系统：各类传感器与系统探针的数据统一编码为结构化日志，写入 Flash / SD 卡 / U 盘，或经 WiFi / BLE 送到主机；最终以一个**自包含的会话目录**交付给智能体分析。

在此基础上再往上走一层：系统同时承担机器人的**解释层**（记录意图、候选方案、选择理由与预期/实测差异，支持 `/why` 追问），并提供**免编译热更新**（上位机直接下发 `.py` 应用，设备在安全点切换，失败自动回滚）。

### 1.2 设计目标

| 目标 | 说明 |
| --- | --- |
| 结构化 | 每条记录自描述，带来源、时间、级别、单位语义 |
| 掉电安全 | 追加写 + 截断恢复，断电最多丢最后一个 flush 周期 |
| 介质无关 | 存储后端可插拔，SD 卡拔出不影响系统继续运行 |
| 低侵入 | 采样端只入内存队列，不阻塞中断与业务逻辑 |
| 智能体友好 | 会话目录内含机器可读元数据与自然语言说明书 |
| 可双向 | 支持主机下发命令，实现「看日志 → 改参数 → 复采」闭环 |
| 自解释 | 不只记录「发生了什么」，还记录「为什么这么做」，可回答上位机的追问 |
| 免编译更新 | 上位机直接下发 `.py` 源码，设备导入即生效，无需 mpy-cross 或固件编译 |

### 1.3 非目标

- 不做逻辑分析仪级别的高速采样（> 1 kHz 连续流）；
- 不做固件级 OTA：MicroPython 内核与 C 模块的更新仍需烧录，本方案的热更新只覆盖 Python 应用层；
- 不替代 `printf` 式即时调试，二者互补；
- 不在设备端做复杂数据分析，聚合与推理放在主机侧。

---

## 2. 总体架构

```mermaid
flowchart TB
    subgraph L1["采集层"]
        A1["传感器驱动<br/>I2C / SPI / ADC / UART"]
        A2["采样调度<br/>周期 / 事件 / 中断"]
        A3["系统探针<br/>内存 / RSSI / 复位原因"]
    end

    subgraph L2["记录层"]
        B1["记录编码<br/>JSONL & 二进制帧"]
        B2["RAM 环形缓冲<br/>丢老留新"]
        B3["落盘策略<br/>批量 flush / 轮转"]
    end

    subgraph L3["存储层"]
        C1["FlashSink<br/>LittleFS"]
        C2["SDSink / MSCSink<br/>SD 卡 / U 盘"]
        C3["NetSink<br/>WiFi / BLE"]
    end

    subgraph L4["交付层"]
        D1["会话目录<br/>manifest.json"]
        D2["索引与摘要<br/>index.jsonl / LOG.md"]
        D3["智能体<br/>读取 / 分析 / 下发命令"]
    end

    A1 --> A2 --> B1 --> B2 --> B3
    A3 --> A2
    B3 --> C1
    B3 --> C2
    B3 --> C3
    C1 --> D1
    C2 --> D1
    C3 --> D1
    D1 --> D2 --> D3
```

### 2.1 分层职责

| 层 | 职责 | 不做什么 |
| --- | --- | --- |
| 采集层 | 读取传感器、统一单位、标注质量位 | 不写文件、不做格式化 |
| 记录层 | 编码、缓冲、批量刷盘、文件轮转 | 不关心介质类型 |
| 存储层 | 打开/写入/同步/关闭具体介质 | 不解析日志内容 |
| 交付层 | 组织会话目录、生成索引与摘要、暴露接口 | 不做实时采样 |

### 2.2 数据流

1. 采样任务按配置周期触发，读取传感器并调用 `emit()`；
2. `emit()` 生成一条记录，写入 RAM 环形缓冲，立即返回；
3. Writer 任务批量取出记录，编码后写入所有已启用的 Sink；
4. Sink 按自身策略 flush（时间或字节阈值）；
5. 会话结束时补写 `manifest.json` 的 `close` 字段并生成 `LOG.md`。

生产与消费彻底解耦：任何一个 Sink 变慢或失败，都不会反压到采样中断。

### 2.3 两条横切能力

解释层与更新层不单独占一层，而是横跨整条链路：

- **解释层**：消费记录流与行为契约，产出 `EXPLAIN.md`，并通过 `/why` 回答上位机追问。它不改变采集与存储，只增加 L1 决策信息。
- **更新层**：分两条互不干扰的路径。技能包走 `app_a` / `app_b` 热更新，只替换 `app/`；固件与内核走独立的 OTA 子系统，拥有自己的状态机、存储分区和传输通道，不参与控制循环。前者见 8.1 ~ 8.10，后者见 8.11 ~ 8.15。

换一种说法：采集层负责“感知”，解释层负责“说出理由”，更新层负责“换一套行为”。三者共用同一套记录格式，因此智能体看到的永远是同一种文档。

在整机层面，这三条能力对应**底盘契约、运行时契约、技能契约**的划分，以及“设备快环 + 上位机慢环”的双环结构，详见第 9 章。

---

## 3. 日志数据模型

### 3.1 主通道格式：JSONL

主日志流 `events.jsonl` 每行一条独立 JSON，UTF-8 编码，以 `\n` 结尾。

```json
{"v":1,"seq":10231,"t":84213,"ts":1760000000,"src":"bmp280","lvl":"INFO","ev":"sample","m":{"p":1003.2,"tc":24.6},"q":"ok"}
```

**为什么选 JSONL 而不是 CSV / 纯二进制：**

- 追加写天然安全，单行损坏不影响其它行；
- 人和 LLM 可直接阅读，新增字段不会破坏旧解析器；
- 支持流式处理，主机可以边下边解析；
- 压缩后可读性依旧保留（gzip 后智能体仍能解压读取）。

代价是体积约为二进制的 2~4 倍，因此高频数据分流到二进制通道。

### 3.2 字段定义

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `v` | int | 是 | schema 版本，当前为 `1` |
| `seq` | int | 是 | 会话内自增序号，从 1 开始，用于定位与缺口检测 |
| `t` | int | 是 | 开机后毫秒数，来自 `time.ticks_ms()`，比较时使用 `ticks_diff` |
| `ts` | int/null | 是 | 绝对时间（epoch 秒）；无 RTC 且未校时时为 `null` |
| `src` | string | 是 | 数据源标识，如 `bmp280`、`sys`、`wifi`、`app` |
| `lvl` | string | 是 | `DEBUG` / `INFO` / `WARN` / `ERROR` / `CRIT` |
| `ev` | string | 是 | 事件类型，见下表 |
| `m` | object | 否 | 测量值字典，键为短名，单位在 `README.md` 中声明 |
| `q` | string | 否 | 质量位：`ok` / `timeout` / `range` / `crc` / `stale` |
| `ctx` | object | 否 | 上下文：`task`、`func`、`line`、`boot` |
| `cid` | string | 否 | 因果链 ID，同一次决策的 intent / plan / action / outcome 共用一个值 |
| `ref` | int | 否 | 指向上一条相关记录的 `seq`，用于回溯 |
| `why` | string | 否 | 人类可读的简短理由，进入解释层的原始素材 |
| `crc` | string | 否 | 可选，记录级 CRC32（默认关闭，见 3.5） |

### 3.3 事件类型

| `ev` | 触发时机 | 典型字段 |
| --- | --- | --- |
| `boot` | 每次启动 | `reset_cause`、`fw`、`free_mem` |
| `sample` | 周期采样 | `m` 测量值 |
| `error` | 驱动或总线异常 | `code`、`detail` |
| `degrade` | 存储/网络降级 | `from`、`to`、`reason` |
| `drop` | 环形缓冲溢出 | `count`、`first_seq` |
| `cmd` | 收到主机命令 | `cmd`、`result` |
| `mark` | 用户埋点 | `label` |
| `intent` | 产生一个目标 | `goal`、`args`、`why` |
| `plan` | 选定方案 | `chosen`、`rejected` |
| `action` | 开始执行动作 | `act`、`expect` |
| `outcome` | 动作结束 | `ok`、`observed`、`ref` |
| `state` | 状态机迁移 | `from`、`to`、`trigger` |
| `assert` | 断言/安全检查 | `cond`、`ok`、`detail` |
| `close` | 会话结束 | `reason` |

### 3.4 记录示例

```json
{"v":1,"seq":1,"t":312,"ts":1760000000,"src":"sys","lvl":"INFO","ev":"boot","m":{"reset":"power_on","fw":"1.29.0","free":182304}}
{"v":1,"seq":2,"t":420,"ts":null,"src":"bmp280","lvl":"INFO","ev":"sample","m":{"p":1003.2,"tc":24.6},"q":"ok"}
{"v":1,"seq":3,"t":1520,"ts":null,"src":"bmp280","lvl":"ERROR","ev":"error","m":{"code":"ETIMEDOUT","addr":"0x76"},"q":"timeout"}
{"v":1,"seq":4,"t":1600,"ts":null,"src":"sd","lvl":"WARN","ev":"degrade","m":{"from":"sd","to":"flash","reason":"EIO"}}
```

### 3.5 完整性与校验

**主通道（JSONL）默认不逐行写 CRC**，理由：JSON 语法本身即可发现截断与损坏，且逐行 CRC 会破坏「智能体直读」。用以下三重机制保证完整性：

1. **行完整性**：最后一行若无换行符或 JSON 解析失败，直接丢弃；
2. **序号连续性**：`seq` 出现跳变即说明丢记录，在恢复报告中标注缺口；
3. **会话闭合**：`manifest.close` 存在表示正常关闭，缺失则为异常掉电。

**二进制通道（`raw/`）必须逐帧带 CRC**：帧头 `0xAA55` + `len`(2B) + `seq`(4B) + `crc32`(4B) + payload。解码时 `crc32` 失败即整帧丢弃。

若某场景必须对 JSONL 做强校验，可在配置中开启 `log.record_crc=true`：设备在序列化完成后追加 `"crc":"xxxxxxxx"` 字段，CRC 覆盖追加该字段之前的整行字节。

---

## 4. 会话目录规范

一次上电运行对应一个会话，目录名格式 `S<YYYYMMDD>-<HHMMSS>`；无 RTC 时退化为 `S<boot_id>-<ticks>`。

会话内允许发生应用热更新：不重建目录，只写一条 `ev=reload` 记录新旧版本，`manifest.app.version` 保留起始版本。智能体按 `reload` 记录把会话切成若干“行为段”，用于对比版本差异。

```text
/LOG/
├── LATEST                          # 单行文本，指向最近会话目录名
├── S20261016-142530/
│   ├── manifest.json               # 机器可读元数据
│   ├── robot.json                  # 本会话生效的自描述快照（能力/策略/版本）
│   ├── README.md                   # 给智能体的字段说明书
│   ├── LOG.md                      # 自动生成的人类/智能体摘要
│   ├── EXPLAIN.md                  # 行为解释：决策链、失败归因、信息缺口
│   ├── approvals.jsonl             # 人工确认审计：谁批准/拒绝了什么
│   ├── index.jsonl                 # 每 N 条一行的跳表索引
│   ├── events.jsonl                # 主日志流（append-only）
│   └── raw/
│       ├── imu-0001.bin            # 高频二进制块
│       └── imu-0001.idx            # 块索引：起始 seq / 时间 / 条数
└── _trash/                         # 轮转淘汰的旧会话
```

### 4.1 manifest.json

```json
{
  "v": 1,
  "session": "S20261016-142530",
  "device": {
    "port": "esp32",
    "board": "ESP32-S3-DevKitC",
    "fw": "1.29.0",
    "id": "A1B2C3D4"
  },
  "app": {"version": "1.4.2", "slot": "a"},
  "clock": {
    "mode": "rtc",
    "t0_epoch": 1760000000,
    "t0_ticks": 0,
    "rtc": "ds3231",
    "drift_ppm": null
  },
  "buses": {
    "i2c0": {"scl": 22, "sda": 21, "freq": 400000}
  },
  "sensors": [
    {"id": "bmp280", "bus": "i2c0", "addr": "0x76", "hz": 1, "fields": {"p": "hPa", "tc": "degC"}},
    {"id": "lsm6dso", "bus": "i2c0", "addr": "0x6A", "hz": 50, "channels": "raw"}
  ],
  "files": {
    "events": "events.jsonl",
    "index": "index.jsonl",
    "summary": "LOG.md",
    "explain": "EXPLAIN.md",
    "robot": "robot.json"
  },
  "limits": {
    "max_bytes": 2097152,
    "rotate_bytes": 524288,
    "flush_ms": 1000,
    "ring_bytes": 16384
  },
  "close": null
}
```

`manifest.json` 必须采用「写临时文件 → rename 覆盖」的方式更新，避免掉电产生半截 JSON。

### 4.2 index.jsonl

每 100 条记录写一行索引，用于快速定位：

```json
{"seq":100,"off":18342,"t":84100,"lvl":"INFO"}
{"seq":200,"off":36811,"t":168300,"lvl":"INFO"}
```

`off` 为该 `seq` 记录在 `events.jsonl` 中的字节偏移，可由 `f.tell()` 获取。

### 4.3 LOG.md

会话结束时（或每 N 分钟增量更新）在设备端生成，也可由主机侧生成。内容控制在几百行内：

```markdown
# 会话 S20261016-142530

- 设备：ESP32-S3 / MicroPython 1.29.0
- 时长：00:12:41
- 记录：761 条，其中 WARN 12 条、ERROR 3 条
- 结束：异常掉电（无 close 记录）
- 结论：bmp280 自 14:31:02 起出现 37 次 I2C 超时，疑似接线松动

## 时间线

| 时间 | 事件 | 说明 |
| --- | --- | --- |
| 14:25:30 | boot | power_on，free=182304 |
| 14:31:02 | error | bmp280 ETIMEDOUT ×1 |
| 14:31:04 | degrade | sd → flash，EIO |

## 缺口

- seq 320-328 缺失（环形缓冲溢出 9 条）
```

### 4.4 README.md（智能体说明书）

这是整个方案里最容易被忽略、但对智能体最关键的文件。模板：

```markdown
# 如何读取本会话

## 快速开始
1. 读 `manifest.json`，获取时钟基准、传感器清单、采样率与文件映射；
2. 问题与行为有关时，先读 `EXPLAIN.md` 的关键决策与失败归因，再读 `robot.json` 的能力与安全策略；
3. 读 `events.jsonl`，每行一条 JSON，按 `seq` 递增；
4. 需要定位时先查 `index.jsonl` 的字节偏移，再 seek；
5. 追问“为什么”时，沿同一条 `cid` 或 `ref` 链回溯 `intent → plan → action → outcome`。

## 字段
- `t` 是开机毫秒，用 `ts = t0_epoch + t/1000` 换算绝对时间（`t0_epoch` 为 null 时不可换算）；
- `lvl` 顺序：DEBUG < INFO < WARN < ERROR < CRIT；
- `q != "ok"` 表示该测量值不可信，不要参与趋势分析；
- `cid` 标识一次决策，`ref` 指向上一条相关记录，`why` 是简短理由；
- 找不到 `ref` 或对应 `ev` 时，说明该环节未埋点，请直接标注“未知”，不要推测。

## 常用查询
- 所有错误：`jq 'select(.lvl=="ERROR" or .lvl=="CRIT")' events.jsonl`
- 某传感器：`jq 'select(.src=="bmp280")' events.jsonl`
- 时间窗：`jq 'select(.t>=60000 and .t<120000)' events.jsonl`
- 一次决策的完整链：`jq 'select(.cid=="c7")' events.jsonl`

## 注意
- 末尾无换行的一行可能被截断，请忽略；
- `seq` 跳变代表丢数据，不要假设等间隔。
```

---

## 5. 模块设计

### 5.1 目录结构（设备端）

内核（`kernel/`）与应用（`app_a/` / `app_b/`）分离，更新只替换应用槽位：

```text
/
├── boot.py                # 挂载文件系统、读 current.json、选择应用槽位
├── current.json           # 当前槽位与版本
├── bootcnt                # 启动失败计数
├── kernel/                # 稳定层，随固件发布
│   ├── main.py            # 装配：总线、传感器、Sink、writer、调度
│   ├── config.json        # 设备与采样配置
│   ├── logcore/
│   │   ├── record.py      # 记录编码与字段校验
│   │   ├── ring.py        # RAM 环形缓冲
│   │   ├── writer.py      # 批量取数、刷盘、轮转
│   │   ├── session.py     # 会话目录、manifest、恢复扫描
│   │   └── summary.py     # LOG.md / EXPLAIN.md 生成
│   ├── sinks/
│   │   ├── base.py        # Sink 抽象
│   │   ├── flash.py       # LittleFS
│   │   ├── sd.py          # SD 卡
│   │   ├── msc.py         # U 盘 / USB MSC
│   │   └── net.py         # HTTP / MQTT / BLE
│   ├── probes/
│   │   ├── base.py        # Probe 抽象
│   │   ├── bmp280.py      # 适配现有驱动
│   │   ├── lsm6dso.py
│   │   └── sysinfo.py     # 内存、RSSI、复位原因
│   ├── agentsrv/
│   │   ├── http.py        # 只读 API + /why + /update
│   │   └── ctl.py         # 命令轮询
│   └── updater.py         # 槽位校验、切换、回滚
├── app_a/                 # 应用槽位 A
│   ├── main.py            # setup / step / teardown / snapshot
│   ├── behaviors/         # 行为契约与实现
│   ├── policies/          # 安全策略
│   └── params.json
└── app_b/                 # 应用槽位 B
```

### 5.2 配置示例

```json
{
  "device": {"name": "bench-01"},
  "log": {
    "root": "/LOG",
    "flush_ms": 1000,
    "rotate_bytes": 524288,
    "keep_sessions": 8,
    "ring_bytes": 16384,
    "min_level": "DEBUG"
  },
  "sinks": [
    {"type": "flash", "path": "/LOG", "enabled": true},
    {"type": "sd", "sck": 18, "mosi": 23, "miso": 19, "cs": 5, "enabled": true},
    {"type": "net", "proto": "http", "enabled": false}
  ],
  "sensors": [
    {"id": "bmp280", "driver": "bmp280", "bus": "i2c0", "addr": 118, "hz": 1},
    {"id": "lsm6dso", "driver": "LSM6DSO", "bus": "i2c0", "addr": 106, "hz": 50, "channel": "raw"}
  ]
}
```

### 5.3 Probe 抽象（对接现有驱动）

仓库中已有 `sensor/` 与 `misc/` 下的驱动可直接复用，只需包一层统一接口：

```python
class Probe:
    src = "probe"
    def init(self): ...
    def read(self) -> dict: ...   # 返回 {"字段": 值}，单位与 manifest 一致
    def hz(self) -> float: ...
```

适配示例（属性名以各驱动 README 为准）：

```python
# probes/bmp280.py
from bmp280 import BMP280

class Bmp280Probe:
    src = "bmp280"
    def __init__(self, i2c, addr=0x76, hz=1):
        self.dev = BMP280(i2c, addr)
        self._hz = hz

    def read(self):
        try:
            return {"p": self.dev.pressure, "tc": self.dev.temperature}
        except OSError:
            return None          # 由调度器写入 error 记录

    def hz(self):
        return self._hz
```

可复用的驱动清单：

| 类型 | 驱动路径 |
| --- | --- |
| 气压/温湿度 | `sensor/bmp180/BMP180.py`、`sensor/bmp280/bmp280.py`、`sensor/bme280/bme280.py` |
| 温湿度/气压 | `sensor/HTS221/hts221.py`、`sensor/LPS22/LPS22.py`、`sensor/STTS751/STTS751.py` |
| IMU | `sensor/LSM6DSO/LSM6DSO.py`、`sensor/LIS2DW12/LIS2DW12.py`、`sensor/LIS2MDL/LIS2MDL.py` |
| 光/接近 | `sensor/APDS9930/APDS9930.py` |
| RTC | `misc/DS3231/DS3231.py`、`misc/DS1307/DS1307.py`、`misc/DS1302/DS1302.py` |
| EEPROM | `misc/AT24XX/AT24XX.py`（可存配置或掉电计数） |

### 5.4 记录层

```python
# logcore/record.py
import time, json

_seq = 0

def emit(src, lvl="INFO", ev="sample", m=None, q="ok", ctx=None):
    global _seq
    _seq += 1
    rec = {
        "v": 1,
        "seq": _seq,
        "t": time.ticks_ms(),
        "ts": _epoch_or_none(),
        "src": src,
        "lvl": lvl,
        "ev": ev,
    }
    if m:
        rec["m"] = m
    if q != "ok":
        rec["q"] = q
    if ctx:
        rec["ctx"] = ctx
    ring.push(json.dumps(rec).encode() + b"\n")
```

高频通道绕过 `json.dumps`，直接 `struct.pack`：

```python
# 每条 IMU 样本 16 字节：t(4) + ax/ay/az/gx/gy/gz (6×2, int16)
def emit_raw(seq, t, samples):
    payload = b"".join(struct.pack("<Ihhhhhh", t, *s) for s in samples)
    raw_writer.append(seq, t, payload)
```

### 5.5 存储抽象

```python
class Sink:
    name = "sink"

    def open(self, session_dir): ...
    def write(self, buf): ...
    def sync(self): ...
    def rotate(self, reason="size"): ...
    def close(self, reason="normal"): ...
    def info(self): return {"name": self.name, "healthy": True}
```

`SinkRouter` 负责：

- 按 `config.sinks` 顺序打开，失败的跳过并记录 `degrade`；
- `write` 时逐个投递，单个 Sink 抛 `OSError` 只标记不可用，不影响其它 Sink；
- 周期性健康检查（如 SD 卡是否仍可写），恢复后重新接入并补写 `degrade` 恢复记录；
- 所有 Sink 都不可用时降级为 `NullSink`，仅保留 RAM 环形缓冲与串口输出。

### 5.6 Writer 任务

```python
class Writer:
    def __init__(self, router, flush_ms=1000, rotate_bytes=524288):
        self.router = router
        self.flush_ms = flush_ms
        self.rotate_bytes = rotate_bytes
        self.last_flush = time.ticks_ms()
        self.written = 0

    def run(self):
        while True:
            batch = ring.pop_batch(4096)
            if batch:
                self.router.write(batch)
                self.written += len(batch)
            now = time.ticks_ms()
            if time.ticks_diff(now, self.last_flush) >= self.flush_ms:
                self.router.sync()
                self.last_flush = now
            if self.written >= self.rotate_bytes:
                self.router.rotate("size")
                self.written = 0
            time.sleep_ms(20)
```

`Writer.run()` 放在主循环或 `asyncio` 任务中执行，**绝不在定时器/中断回调中调用**。

### 5.7 采样调度

- 低频（≤ 10 Hz）：主循环轮询，读取 `ticks_diff` 判断是否到期；
- 中频（10~100 Hz）：`machine.Timer` 回调中只置标志或写环形缓冲，不做 I2C 读；
- 高频（> 100 Hz）：使用传感器内置 FIFO + 中断（如 LSM6DSO 的 FIFO/INT），中断中只读 FIFO 到本地数组，主循环批量打包。

所有 I2C/SPI 读操作都在主上下文完成，避免在中断里发生总线阻塞。

---

## 6. 传输与智能体交互

### 6.1 三种取数模式

| 模式 | 链路 | 适用场景 | 优点 | 缺点 |
| --- | --- | --- | --- | --- |
| 介质摆渡 | SD 卡 / U 盘 | 长时间无人值守 | 容量大、零功耗、最稳 | 需人工拔插 |
| 主动拉取 | WiFi HTTP | 台架调试、现场排障 | 断点续传、可脚本化 | 需要网络与 IP |
| 实时推送 | WiFi MQTT / BLE | 告警、在线观察 | 低延迟 | 易丢数据、功耗高 |

推荐默认组合：**SD 卡常开记录 + WiFi 按需开启拉取 + BLE/MQTT 只推 `ERROR/CRIT`**。

### 6.2 HTTP 接口

设备端运行一个极小 HTTP 服务（`asyncio.start_server` 或 `socket`），只读为主：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/sessions` | 会话列表及大小 |
| GET | `/manifest?session=` | 返回 manifest.json |
| GET | `/tail?session=&n=100` | 返回最后 N 条记录 |
| GET | `/range?session=&from=&limit=500` | 按 seq 区间取记录 |
| GET | `/file?session=&path=events.jsonl` | 下载文件，支持 `Range` |
| GET | `/health` | 内存、介质状态、最后 seq |
| POST | `/ctl` | 下发命令（需 token） |

`/file` 支持 `Range: bytes=18342-`，配合 `index.jsonl` 即可实现断点续传。

### 6.3 BLE 接口

BLE 仅承载小数据量：

| 特征 | 属性 | 用途 |
| --- | --- | --- |
| `manifest` | Read | 读取设备与会话元数据 |
| `tail` | Read / Notify | 最近 N 条摘要或告警 |
| `cmd` | Write | 下发短命令（改采样率、立即 flush、打标） |
| `chunk` | Read | 分块读取文件（每块 ≤ MTU-3） |

BLE 实测吞吐通常只有 5~20 KB/s，不适合传完整 `events.jsonl`；建议只传 `LOG.md` 与错误记录。

### 6.4 双向命令通道

文件摆渡与 HTTP 共用同一套命令格式：

```json
// /CTL/cmd.json
{"seq": 12, "cmd": "set_rate", "src": "bmp280", "hz": 4, "ttl_s": 60}
```

```json
// /CTL/ack.json
{"seq": 12, "ok": true, "applied": {"src": "bmp280", "hz": 4}, "t": 84213}
```

支持的命令：

| `cmd` | 参数 | 作用 |
| --- | --- | --- |
| `set_rate` | `src`, `hz` | 修改采样率 |
| `flush` | — | 立即刷盘 |
| `mark` | `label` | 写入一条埋点记录 |
| `set_level` | `level` | 调整日志级别 |
| `rotate` | — | 强制轮转 |
| `dump` | `src`, `n` | 回传最近 N 条该源记录 |
| `set_time` | `epoch` | 校准绝对时间基准 |
| `reboot` | `delay_s` | 延时重启（谨慎启用） |

命令必须带 `seq` 去重、带 `ttl_s` 过期，且只允许白名单命令。

### 6.5 智能体接入方式

1. **离线直读**：主机挂载 SD/U 盘或拷贝会话目录，智能体直接读 `README.md` → `manifest.json` → `LOG.md` → `events.jsonl`；
2. **MCP / 工具封装**：把 `/range`、`/tail`、`/ctl` 封装成主机侧工具，智能体按需查询，不必下载整份日志；
3. **混合**：先读 `LOG.md` 定位时间窗，再用 `/range` 精确拉取。

Prompt 约定（建议写进 `README.md`）：

> 你是硬件调试助手。先读 `manifest.json` 确认时钟与传感器，再读 `LOG.md` 获取结论，最后用 `events.jsonl` 验证。分析结论必须引用具体 `seq`，区分「测量值异常」与「采集链路异常」。

---

## 7. 机器人解释层

### 7.1 从「记录数据」到「解释行为」

普通日志回答“传感器读到了什么”；解释层要回答另外三个问题：

- 机器人现在在做什么？（状态与意图）
- 为什么这么做？（决策依据与被否决的方案）
- 做完之后实际发生了什么？（预期与实测的差异）

对应三层信息：

| 层级 | 内容 | 来源 | 输出 |
| --- | --- | --- | --- |
| L0 事实层 | 传感器值、执行器输出、系统资源 | Probe | `events.jsonl` |
| L1 决策层 | 目标、候选方案、选择理由、预期结果 | 应用代码主动埋点 | `events.jsonl` 中的 `intent/plan/action/outcome` |
| L2 叙事层 | 会话摘要、因果链、失败归因 | 设备或主机聚合 | `LOG.md` / `EXPLAIN.md` |

关键约束：**L1 必须由运行中的应用主动上报**。事后从 L0 反推出来的“理由”只是猜测，不能当作解释。行为代码里少写一行 `emit`，解释层就少一个环节，因此埋点覆盖率要作为一项指标。

### 7.2 自描述：robot.json

设备启动时生成或读取一份自描述文件，与 `manifest.json` 并列存放。它既是智能体的入口，也是运行时校验行为合法性的依据：

```json
{
  "id": "r1",
  "model": "diff-drive-01",
  "firmware": {"kernel": "1.0.0", "app": "1.4.2"},
  "states": ["IDLE", "NAV", "GRASP", "FAULT"],
  "capabilities": [
    {"id": "go_to", "args": {"x": "m", "y": "m"}, "limits": {"max_speed": 0.3}},
    {"id": "grab", "args": {"target": "str"}, "limits": {"max_force": 20}}
  ],
  "sensors": ["bmp280", "lsm6dso", "tof_left", "tof_right"],
  "actuators": ["wheel_l", "wheel_r", "gripper"],
  "safety": {"estop_pin": 4, "max_tilt": 25, "min_battery": 20},
  "policies": [
    {"id": "avoid", "priority": 10, "when": "tof < 0.25", "then": "stop"},
    {"id": "failsafe", "priority": 20, "when": "battery < 20", "then": "return_home"}
  ],
  "entry": "app.main"
}
```

`capabilities` 与 `policies` 是给智能体看的“能做什么、受什么限制”，也是应用更新时的兼容性约束：新版本不能声明旧内核不支持的能力。

### 7.3 行为契约

每个行为模块导出一份契约，运行时在执行前后自动校验并记录：

```python
# app/behaviors/go_to.py
BEHAVIOR = {
    "id": "go_to",
    "pre": ["battery > 20", "localized"],
    "abort": ["tof < 0.2"],
    "effects": ["pose_changed"],
    "explain": "前往 ({x:.2f}, {y:.2f})，原因：{why}",
}

def run(ctx, x, y, why):
    ...
```

执行器统一入口：

```python
def invoke(behavior, args, why):
    cid = ctx.next_cid()
    emit("app", "INFO", "intent", {"goal": behavior["id"], "args": args},
         cid=cid, why=why)

    failed = [p for p in behavior["pre"] if not ctx.check(p)]
    if failed:
        emit("app", "WARN", "assert",
             {"cond": failed, "ok": False, "detail": "precondition"},
             cid=cid, ref=ctx.last_seq())
        return False

    emit("app", "INFO", "action",
         {"act": behavior["id"], "args": args, "expect": behavior["effects"]},
         cid=cid)

    ok, observed = behavior["run"](ctx, **args)
    emit("app", "INFO", "outcome",
         {"ok": ok, "observed": observed}, cid=cid, ref=ctx.last_seq())
    return ok
```

约定：`behavior["run"]` 只做动作，不写日志；日志由 `invoke` 统一产生，保证格式一致。

### 7.4 因果记录

同一次决策的四类记录共用一个 `cid`，并用 `ref` 指向前一条：

```json
{"v":1,"seq":41,"t":12000,"ts":null,"src":"app","lvl":"INFO","ev":"intent","cid":"c7","why":"task=patrol#3","m":{"goal":"go_to","x":1.2,"y":0.8}}
{"v":1,"seq":42,"t":12010,"ts":null,"src":"app","lvl":"INFO","ev":"plan","cid":"c7","ref":41,"m":{"chosen":"go_to","rejected":[{"alt":"arc","reason":"tof=0.18"}]}}
{"v":1,"seq":43,"t":12020,"ts":null,"src":"app","lvl":"INFO","ev":"action","cid":"c7","ref":42,"m":{"act":"go_to","expect":"arrive<3s"}}
{"v":1,"seq":44,"t":15020,"ts":null,"src":"app","lvl":"WARN","ev":"outcome","cid":"c7","ref":43,"m":{"ok":false,"observed":"stuck","dist":0.12}}
```

这段链路就是一次可解释的最小单元：**想做什么 → 为什么选它 → 怎么做的 → 结果如何**。

### 7.5 解释接口

| 方法 | 路径 | 返回 |
| --- | --- | --- |
| GET | `/state` | 当前状态、最后意图、活动故障、最近 5 条决策 |
| GET | `/why?seq=44` | 沿 `ref` 链回溯最多 5 跳，渲染成因果说明 |
| GET | `/timeline?from=&to=` | 按时间窗返回决策与状态迁移 |
| GET | `/capabilities` | 能力、限制、安全策略 |
| GET | `/explain?session=` | 生成整份 `EXPLAIN.md` |

`/why` 的返回同时给两种格式，方便人和模型使用：

```json
{
  "seq": 44,
  "chain": [44, 43, 42, 41],
  "text": "机器人在 t=12.0s 决定前往 (1.2, 0.8)，因为巡逻任务第 3 段；\n由于左侧测距 0.18m 低于安全阈值，放弃了弧线路径；\n执行 3 秒后仍未到达，距离 0.12m，判定为卡住。",
  "observed": {"ok": false, "dist": 0.12},
  "expect": "arrive<3s"
}
```

实现要点：只读 `events.jsonl` 即可，不需要额外存储；找不到 `ref` 时明确返回“该环节未埋点”，不要补写推测。

### 7.6 EXPLAIN.md

与会话目录放在一起，会话结束时生成，也可按需增量刷新：

```markdown
# 会话解释 S20261016-142530

## 任务
巡逻任务，共 3 段路径，目标为 (1.2, 0.8)。

## 关键决策
| 时间 | 决策 | 理由 | 结果 |
| --- | --- | --- | --- |
| 12.0s | 前往 (1.2,0.8) | 巡逻第 3 段 | 卡住 |
| 15.0s | 放弃弧线路径 | tof 0.18 < 0.25 | — |
| 15.2s | 进入 FAULT | 连续 2 次未到达 | 停机 |

## 失败归因
- 直接原因：路径被障碍物阻挡，tof 左 0.18m；
- 触发策略：`avoid`（优先级 10）；
- 未触发项：`failsafe` 电量正常；
- 缺口：`go_to` 内部的电机电流未埋点，无法判断是否打滑。
```

最后一行“缺口”很重要：明确告诉智能体哪些信息缺失，避免它用常识补全。

### 7.7 智能体问答闭环

| 用户问题 | 智能体动作 |
| --- | --- |
| “为什么刚才停下来了？” | `GET /why?seq=<最后一条 outcome>` → 读因果链 |
| “这次任务为什么失败？” | 读 `EXPLAIN.md` 的失败归因段落 |
| “能不能开快一点？” | 读 `/capabilities` 的 `max_speed`，再查 `policies` 是否冲突 |
| “改一下避障距离，再跑一次” | `POST /ctl` 改参数，或推送新版本 → 观察新会话 |
| “这个版本比上个版本差在哪？” | 按 `ev=reload` 切分会话，对比成功率与异常分布 |

### 7.8 解释的边界

- 解释的是**系统内部的理由**，不等于物理世界的真实因果。电机堵转可能被记录成“超时”，而不是“轮子被卡”。
- 必须同时记录 `expect` 与 `observed`，否则容易自圆其说。
- 未埋点的环节要显式标注为缺口，禁止让模型自行补全。
- 解释层不参与控制决策，只读不写，避免“为了让日志好看而改变行为”。

---

## 8. 更新系统：免编译热更新与 OTA

### 8.1 设计原则

1. **上位机只传 `.py` 源码**，设备导入时编译；不需要 mpy-cross，也不需要重新编译固件。
2. **内核与应用分离**：`kernel/` 稳定（调度、日志、驱动、更新器），`app/` 高频迭代（行为、策略、参数）。
3. **双槽位 + 指针切换**：新版本写入非活动槽，校验通过后才切换指针。
4. **安全点应用**：机器人运动、抓取、标定过程中不重载。
5. **失败自动回滚**：连续启动失败达到阈值，自动退回上一版本。

### 8.2 目录与槽位

```text
/
├── boot.py                 # 只负责挂载文件系统、读取 current.json、跳转到内核
├── kernel/
│   ├── main.py             # 调度器、日志系统、更新器
│   ├── logcore/
│   ├── drivers/
│   └── updater.py
├── app_a/                  # 应用槽位 A
│   ├── main.py
│   ├── behaviors/
│   └── params.json
├── app_b/                  # 应用槽位 B
├── STATE/
│   └── state.json          # 重载前的运行状态快照
├── current.json            # 当前槽位与版本
├── bootcnt                 # 启动失败计数
└── LOG/                    # 会话目录，与代码完全分离
```

```json
// current.json
{"slot": "a", "version": "1.4.2", "prev": "b", "confirmed": true, "kernel_min": "1.0.0"}
```

切换槽位只改 `current.json`，采用「写临时文件 → `os.rename` 覆盖」。日志目录与代码目录分离，更新不会触碰正在写入的会话。

### 8.3 更新包格式

```text
pkg-1.4.2/
├── update.json
└── app/
    ├── main.py
    ├── behaviors/
    │   ├── go_to.py
    │   └── grab.py
    └── params.json
```

```json
{
  "version": "1.4.2",
  "kernel_min": "1.0.0",
  "entry": "app.main",
  "note": "降低避障阈值，修复抓取超时",
  "files": [
    {"path": "app/main.py", "size": 4213, "sha256": "9f2c..."},
    {"path": "app/behaviors/go_to.py", "size": 2871, "sha256": "3ab1..."}
  ]
}
```

上位机在打包时计算哈希；设备逐文件校验。上传前先对比 `/update/info` 返回的哈希表，只传变化的文件，实现差分更新。

### 8.4 更新流程

```mermaid
sequenceDiagram
    participant H as 上位机
    participant D as 设备
    H->>D: GET /update/info
    D-->>H: 当前槽位/版本/文件哈希/是否处于安全点
    H->>D: PUT /update/file?slot=b&path=app/main.py
    H->>D: PUT /update/file?slot=b&path=app/behaviors/go_to.py
    H->>D: POST /update/commit {version, files}
    D->>D: 校验哈希 + compile() 语法检查
    D-->>H: 202 pending（等待安全点）
    D->>D: 到达安全点 → snapshot → teardown → 切换 → setup
    D-->>H: /update/status = running 1.4.2
```

| 步骤 | 接口 | 说明 |
| --- | --- | --- |
| 查询 | `GET /update/info` | 返回当前槽位、版本、各文件哈希、`safe` 标志 |
| 上传 | `PUT /update/file?slot=b&path=...` | 原始字节写入非活动槽，路径必须落在 `app_*` 内 |
| 提交 | `POST /update/commit` | 校验全部哈希与语法，写 `pending.json` |
| 应用 | `POST /update/apply` | 立即尝试应用；失败则保持 pending，等下一个安全点 |
| 状态 | `GET /update/status` | `idle / uploading / pending / applying / running / rolled_back` |
| 回滚 | `POST /update/rollback` | 手动切回 `prev` |

### 8.5 安全点与状态迁移

应用必须实现以下约定函数（`restore` 可选）：

```python
# app/main.py
def setup(ctx): ...          # 初始化行为、订阅配置
def step(dt_ms): ...         # 主循环调用，内部应快速返回
def teardown(): ...          # 释放资源、停止电机
def snapshot() -> dict: ...  # 导出需要跨版本保留的状态
def restore(state): ...      # 可选：从快照恢复任务队列与位姿
```

更新器只在满足以下条件时应用新版本：

- 状态机处于 `IDLE` 或显式声明的安全状态；
- 无运动指令、无抓取动作；
- 当前 `step()` 已返回，不在回调中；
- 电量高于阈值（避免切换过程中掉电）。

应用流程：

1. `state = snapshot()` 写入 `STATE/state.json`；
2. 调用旧版本 `teardown()`，确保执行器进入安全状态；
3. 切换 `current.json` 指针，重新导入 `app.*`；
4. 调用新版本 `setup(ctx)` 与 `restore(state)`；
5. 连续心跳 5 s 正常后写 `confirmed=true` 并清零 `bootcnt`；
6. 任一步抛异常 → 立即回滚并写 `CRIT`。

### 8.6 校验与约束

| 检查项 | 位置 | 规则 |
| --- | --- | --- |
| 语法 | 设备 | 逐文件 `compile(src, path, "exec")`，失败拒绝提交 |
| 语法（预检） | 上位机 | `ast.parse` 或 MicroPython unix 版导入测试，减少无效上传 |
| 哈希 | 设备 | `sha256` 流式计算；端口不支持时退化为 CRC32 并在 `update.json` 标注 |
| 大小 | 设备 | 单文件 ≤ 32 KB，整包 ≤ 256 KB（可按板型配置） |
| 路径 | 设备 | 只允许 `app_*` 前缀，拒绝 `..`、绝对路径、符号链接 |
| 内核兼容 | 设备 | `kernel_min` 必须 ≤ 当前内核版本 |
| 导入白名单 | 设备 | 应用只能导入 `machine`、`time`、`math`、`json`、`os`、`struct` 与 `app.*` |
| 命名 | 设备 | 入口模块必须存在且导出 `setup/step/teardown` |

设备端 `compile()` 会占用堆，大文件应在主机侧拆分为多个小模块；不建议在 ESP8266 等内存紧张的平台上一次性校验整包。

### 8.7 热重载骨架

```python
# kernel/updater.py
import sys, os, json

def _purge_app_modules():
    for name in [m for m in sys.modules
                 if m == "app" or m.startswith("app.")]:
        del sys.modules[name]

def load_app(slot, entry="app.main"):
    base = "/" + slot
    _purge_app_modules()
    if base in sys.path:
        sys.path.remove(base)
    sys.path.insert(0, base)          # 新槽位优先
    __import__(entry)
    return sys.modules[entry]

def apply(pending, ctx):
    if not ctx.safe_to_reload():
        return "pending"

    state = ctx.app.snapshot() if hasattr(ctx.app, "snapshot") else {}
    with open("/STATE/state.json", "w") as f:
        json.dump(state, f)

    try:
        ctx.app.teardown()
    except Exception as e:
        emit("sys", "ERROR", "reload", {"stage": "teardown", "err": str(e)})

    try:
        mod = load_app(pending["slot"], pending["entry"])
        mod.setup(ctx)
        if hasattr(mod, "restore"):
            mod.restore(state)
    except Exception as e:
        emit("sys", "CRIT", "reload", {"stage": "setup", "err": str(e)})
        rollback()
        return "rolled_back"

    switch_current(pending["slot"], pending["version"])
    emit("sys", "INFO", "reload",
         {"from": ctx.app_version, "to": pending["version"]})
    ctx.app, ctx.app_version = mod, pending["version"]
    return "running"
```

注意两点：

- 删除 `sys.modules` 中的旧模块只是让后续 `import` 拿到新代码，**已存在的对象引用不会自动更新**，所以必须走 `teardown → setup` 的完整重建；
- `sys.path` 中要移除旧槽位，避免同名模块被旧路径遮蔽。

### 8.8 上位机工具

```bash
logctl status --host 192.168.4.1
logctl push ./pkg-1.4.2 --host 192.168.4.1   # 计算哈希 + 差分上传 + 提交
logctl apply  --host 192.168.4.1             # 到安全点后应用
logctl rollback --host 192.168.4.1
logctl logs --tail 50 --host 192.168.4.1
```

`logctl push` 不做任何编译，只做三件事：计算哈希、上传差异文件、调用 commit。主机侧可选的 `ast.parse` 仅用于提前发现明显语法错误，不生成字节码。

### 8.9 回滚与失败模式

| 失败场景 | 检测方式 | 处理 |
| --- | --- | --- |
| 哈希不匹配 | commit 校验 | 拒绝提交，旧版本继续运行 |
| 语法错误 | `compile()` | 拒绝提交，返回具体文件与行号 |
| `setup()` 抛异常 | 应用钩子 | 切回 `prev`，写 `CRIT` |
| 启动后崩溃 | 心跳缺失 / 看门狗 | 重启，`bootcnt++`，达到 3 次回滚 |
| 新版本行为异常 | 主机看日志 | 手动 `logctl rollback`，保留现场会话 |
| 内核不兼容 | `kernel_min` | 提交阶段拒绝 |
| 更新中掉电 | 启动时检查 `pending.json` | 旧槽完整，`current.json` 未切换，直接走旧版本 |

`bootcnt` 的写入必须在 `boot.py` 早期完成，且用独立的单行文件，避免依赖完整 JSON 解析。

### 8.10 边界与注意事项

- 8.1 ~ 8.10 的热更新只覆盖 Python 应用层；新增 C 模块、修改 MicroPython 内核、更新底盘固件，走 8.11 ~ 8.15 的 OTA 子系统。
- 更新期间日志继续写入当前会话，切换时写一条 `ev=reload` 作为分界；智能体据此按版本切分行为，对比新旧表现。
- 应用代码不要缓存跨版本的全局句柄（I2C、定时器、电机对象），统一由 `ctx` 提供，`setup` 时重新获取。
- 参数（`params.json`）与代码同包更新，避免“代码回滚了、参数没回滚”。
- 生产设备建议默认关闭 `/update/*` 写接口，仅在维护模式或本地 AP 下开启。

---

### 8.11 OTA 与主逻辑的隔离边界

OTA 是**独立子系统**，不是主操作逻辑的一部分。五条边界必须同时成立：

| 边界 | 约束 | 目的 |
| --- | --- | --- |
| 任务隔离 | OTA 运行在独立任务/协程，控制循环只读取一个 `ota.pending()` 标志 | 不拖慢 20~50 Hz 快环 |
| 状态隔离 | 只允许在 `IDLE` 且 `DISARM` 时应用；`RUN` / `FAULT` 下禁止 | 不在运动中换固件 |
| 存储隔离 | 镜像写入独立 `/ota/` 分区，绝不与 `/LOG/` 混用 | 刷写失败不损坏会话 |
| 故障隔离 | OTA 失败只回滚或中止，不把整机置为 `FAULT` | 观测能力不被更新拖累 |
| 链路隔离 | OTA 只走 WiFi / UART1，**永不占用 UART0** | 底盘控制链路专用于实时协议 |

主逻辑与 OTA 的全部交互只有三个入口：

```python
ota.request(manifest)   # 上位机发起，进入下载
ota.status()             # 主逻辑/UI 查询，只读
ota.apply_at_safe_point()  # 仅在 IDLE 且 DISARM 时由监督器调用
```

### 8.12 三类更新对象

| 类型 | 内容 | 机制 | 生效方式 | 风险 |
| --- | --- | --- | --- | --- |
| 技能包 | `.py` + `skill.json` + 参数 | 8.1 ~ 8.10 热更新 | 安全点重载，不重启 | 低 |
| ESP32 固件 | MicroPython `.bin` / 文件系统镜像 | ESP32 引导器 A/B 槽 | 重启切换 | 中 |
| 底盘固件 | 底盘 MCU `.bin` | ESP32 经 UART0 转发给底盘 bootloader | 底盘重启 | 高 |
| 配置 | `config.json` / `params.json` | 临时文件 + rename | 立即或重载 | 低 |

三类对象统一实现同一个接口，主逻辑不关心差异：

```python
class OtaTarget:
    def begin(self, manifest): ...   # 校验型号、协议版本、空间
    def write(self, offset, chunk): ...
    def verify(self): ...            # 分块哈希 + 整镜像哈希 + 签名
    def commit(self): ...            # 切槽，标记 pending
    def rollback(self): ...
```

固件 OTA 的落地方式随 port 而异：ESP32 可用 OTA 分区与 `esp32.Partition`，RP2040/RP2350 走 UF2/bootloader，STM32 需要自定义 bootloader。**应用层接口保持一致，移植差异封装在 `OtaTarget` 实现里。**

ESP32 的具体做法：

- 默认 MicroPython 通用固件通常使用非 OTA 分区表，**固件级 OTA 需要自定义分区表**（`factory` + `ota_0` + `ota_1`，或双 OTA 槽）；
- **4 MB Flash 上双 app 槽与文件系统难以共存**（两个 1.5 MB 固件槽已占满），C3 基础版建议固件升级走 USB / UART1，固件 OTA 留给 8 MB 模块或 S3；
- 运行时用 `esp32.Partition` 找到下一更新槽，分块写入，校验后 `set_boot()` 并重启；
- 若暂时不改分区表，则“固件 OTA”退化为 UART1 / USB 维护模式烧录，**技能包热更新不受影响**；
- 无论哪种方式，都必须保留 esptool 可恢复的串口与 BOOT 引脚。

### 8.13 OTA 状态机

```mermaid
stateDiagram-v2
    [*] --> IDLE
    IDLE --> DOWNLOAD : 收到 OTA manifest
    DOWNLOAD --> VERIFY : 下载完成
    DOWNLOAD --> IDLE : 中断 / 超时
    VERIFY --> PENDING : 哈希与签名通过
    VERIFY --> IDLE : 拒绝并记录原因
    PENDING --> APPLY : 人工确认通过
    PENDING --> IDLE : 超时 / 用户拒绝
    APPLY --> REBOOT : 切换槽位
    REBOOT --> CONFIRM : 5 s 内心跳正常
    REBOOT --> ROLLBACK : 连续 3 次启动失败
    CONFIRM --> IDLE : 清零 bootcnt
    ROLLBACK --> IDLE : 恢复旧槽
```

关键规则：

- 下载可分块、可断点续传，每块带偏移与哈希；
- `PENDING` 状态可跨重启保留，但**不能跨人工确认**；
- 应用前必须再次检查 `IDLE`、`DISARM`、无未完成会话写盘；
- `CONFIRM` 失败自动回滚，并把 `bootcnt`、失败原因写入 `ev=ota`；
- 底盘固件更新时，ESP32 大脑进入 `UPDATE` 状态并暂停心跳业务，但保留 200 ms 超时保护。

### 8.14 校验、签名与防变砖

每个 OTA 包必须携带 `manifest.json`：

```json
{
  "id": "brain-fw",
  "type": "firmware",
  "target": "brain",
  "version": "1.4.2",
  "board": "esp32s3",
  "min_proto": "1.0",
  "size": 1048576,
  "sha256": "…",
  "signature": "ed25519:…",
  "rollback_to": "1.4.1",
  "approval_required": true
}
```

校验顺序：型号与 `min_proto` → 空间 → 分块哈希 → 整镜像哈希 → 签名 → 人工确认。任一失败立即中止，旧槽保持不变。

防变砖三重保障：

1. **双槽 + 指针**：`current.json` 只在 `CONFIRM` 成功后切换；
2. **独立引导器**：`boot.py` 只做槽位选择与 `bootcnt` 判断，不导入业务代码；
3. **物理恢复**：保留 UART1 / USB MSC 的维护模式，可在无网络时手动推镜像。

### 8.15 传输选择与日志记录

| 通道 | 用途 | 分块大小 | 说明 |
| --- | --- | --- | --- |
| WiFi | 主通道：固件镜像、技能包、会话回传 | 1~4 KB | 带宽高，支持断点续传 |
| UART1 | 备用：小镜像、配置、无 WiFi 恢复 | 128~256 B | 稳定，但大镜像耗时明显 |
| BLE | 仅状态查询与确认，不传镜像 | — | 带宽不足 |
| USB MSC | 现场维护：直接拷贝镜像 | — | 需要人工插拔 |

OTA 全程写结构化记录，便于事后归因：

```json
{"v":1,"seq":20481,"t":512300,"src":"ota","lvl":"INFO","ev":"ota",
 "m":{"target":"brain","from":"1.4.1","to":"1.4.2","phase":"confirm","approval_id":"ap-7f3c"}}
```

应用镜像前必须同步 flush 一次，确保 `ev=ota` 落盘；重启后由新版本继续写同一会话，智能体据此按版本切分前后表现。

---

## 9. 整机工程：固定底盘 + 可更新技能层

### 9.1 三个契约

整机只允许通过三个稳定契约交互，任何一层都不越界：

| 契约 | 归属 | 变更频率 | 内容 |
| --- | --- | --- | --- |
| **底盘契约** | 底盘固件 | 极低（版本化） | 帧协议、命令、遥测、能力描述、硬安全 |
| **运行时契约** | `kernel/` | 低 | `ctx` API、生命周期、调度、日志、更新 |
| **技能契约** | `app_a/` / `app_b/` | 高（AI 生成） | `skill.json` + 行为代码 + 参数 |

核心原则：

- 上位机与 AI **只写技能层**，永远不生成或修改底盘固件；
- 底盘只暴露“能力”，不暴露寄存器、PID 参数或电机对象；
- 运行时是唯一同时看见两侧的组件，负责翻译、限幅、记录与回滚。

### 9.2 拓扑与术语：只有一个大脑

先澄清一个容易混淆的说法：**系统里只有一颗“大脑”，就是跑 MicroPython 的那颗 ESP32，不存在“双大脑”，也不会有第二个 Python 解释层。**

| 角色 | 芯片 | 跑什么 | 是否可更新 |
| --- | --- | --- | --- |
| 大脑 | **ESP32-C3（基础版）/ ESP32-S3（进阶）** | MicroPython 运行时、技能、日志、解释、OTA | 是 |
| 底盘控制器 | 另一颗固定功能 MCU（可选） | 电机闭环、编码器、限幅、急停 | 仅固件 OTA |

“双 MCU”指的是“一颗可编程大脑 + 一颗固定功能底盘控制器”，后者不跑 Python、不参与决策，只执行协议命令。如果你用的是自带控制器的成品底盘，这个结构已经成立，你只需要写 ESP32 侧。

| 拓扑 | 结构 | 优点 | 缺点 | 适用 |
| --- | --- | --- | --- | --- |
| A 单 ESP32 直驱 | ESP32 同时跑 MicroPython 与电机 PWM | 成本最低、结构最简单 | 实时性和安全隔离弱，GC/WiFi 可能引入抖动 | 低速小车、教学 |
| B ESP32 大脑 + 底盘控制器（推荐） | ESP32 跑 MicroPython；另一颗 MCU 做电机与安全 | 安全隔离、实时性好、可独立升级 | 多一颗 MCU 与一条线束 | 有编码器、动态性能要求高的机器人 |
| C 上位机直连 | PC 跑技能，ESP32 只做协议桥 | 算力最强、调试方便 | 不能脱机，线缆受限 | 台架与研究 |

选型结论：**基础版用 ESP32-C3，进阶版用 ESP32-S3**。

| 型号 | 核心 | 内存 | 适合 |
| --- | --- | --- | --- |
| **ESP32-C3** | 单核 RISC-V 160 MHz | ~400 KB SRAM，常见 4 MB Flash | BLE 更新技能、UART 控制、本地日志 |
| **ESP32-S3** | 双核 240 MHz | 512 KB SRAM，可选 PSRAM | WiFi + BLE 并发、大日志、USB OTG |

C3 做基础版是成立的，但要接受四条约束：

1. **BLE 与 WiFi 分时使用**，不同时开启——单核 + 400 KB 内存，两套协议栈并发会明显挤压 MicroPython 堆；
2. **日志以本地落盘为主**，WiFi 只在需要回传时打开；
3. **技能包保持小体积**（几十 KB 以内），不做图像、音频或大模型推理；
4. **4 MB Flash 必须轮转**，固件与文件系统约占一半，日志与技能包只能用剩下的部分。

#### 9.2.1 C3 的资源预算与升级路径

以下是量级估算，以实测为准：

| 项目 | 预算 |
| --- | --- |
| Flash | 固件 + 文件系统约 2 MB；日志 / 技能 / OTA 约 1.5~2 MB |
| RAM | WiFi 约 50 KB、BLE 约 40 KB，**分时使用**，峰值控制在 250 KB 以内 |
| 日志环形缓冲 | 8~16 KB（50~100 条记录） |
| 采样 / 控制 | 20~50 Hz 稳定；不要尝试 kHz 级闭环 |
| BLE 更新 | 技能包 10~50 KB，实测约 10~40 KB/s，几十秒内完成 |

关于“用蓝牙更新解释代码够不够”：

- **技能包够用**。BLE 传 `.py` + `skill.json` 完全可行，链路层分块 + 设备端 `compile()` 校验即可；
- **MicroPython 固件不够用**。固件镜像通常 1.5 MB 以上，BLE 传完要几分钟且易断，应走 WiFi、UART1 或 esptool；
- **日志回传不够用**。会话日志走 SD 卡或 WiFi，BLE 只传摘要与告警。

升级到 S3 时，业务代码不变，只改三处：`board.py` 引脚映射、分区表、链路模式（允许 WiFi + BLE 并发）。因此从第一版起就要把引脚、分区、链路开关放进配置，不要散落在业务代码里。

如果选拓扑 A（只有一颗 ESP32 直驱）：

- MicroPython 适合 50~100 Hz 的速度环，做不了 kHz 级电流环；
- 用硬件 PWM 驱动电机、硬件脉冲计数读编码器，控制任务固定周期，避免在中断里分配内存；
- 运动时尽量降低 WiFi 占空比，日志先入环形缓冲；
- 硬件急停与驱动使能必须独立于软件，不能只靠 Python 里的 `stop()`。

拓扑 B 下：

- 底盘控制器负责电机闭环、传感器采集、限幅、急停，固件固定；
- ESP32 大脑负责技能逻辑、日志、解释与更新；
- 两者之间只有一条 UART0 协议链路，协议版本写在 `HELLO` 帧里。

### 9.3 底盘协议（固定）

#### 帧格式

```text
0xAA 0x55 | ver(1) | type(1) | flags(1) | seq(2,LE) | len(2,LE) | payload | crc16(2,LE)
```

- `crc16` 使用 CCITT 多项式，覆盖 `ver` 到 `payload`；
- 单帧 payload ≤ 256 字节，长内容分片；
- 大脑侧接收使用状态机解析，禁止一次性 `read()` 后假设整帧到达；
- 命令最高 50 Hz，遥测默认 20 Hz，心跳 200 ms 一次。

#### 消息类型

| 类型 | 方向 | 用途 |
| --- | --- | --- |
| `HELLO` | 双向 | 协议版本、设备 ID、能力摘要 |
| `CAPS` | 底盘 → 大脑 | 完整能力描述（JSON 或 TLV） |
| `ARM` | 大脑 → 底盘 | 进入可运动状态 |
| `DISARM` | 双向 | 退出可运动状态 |
| `SET_VEL` | 大脑 → 底盘 | 线速度 `v`、角速度 `w` |
| `SET_ACT` | 大脑 → 底盘 | 执行器 ID 与目标值 |
| `STOP` | 双向 | 按限加速度减速停车 |
| `ESTOP` | 双向 / 硬件 | 立即断使能刹车，锁存故障 |
| `CLEAR_FAULT` | 大脑 → 底盘 | 静止且无危险时清故障 |
| `HEARTBEAT` | 大脑 → 底盘 | 超时 200 ms 自动停车 |
| `TELEM` | 底盘 → 大脑 | 位姿、电量、传感器快照、执行器反馈 |
| `FAULT` | 底盘 → 大脑 | 故障码与发生时刻 |

#### 能力描述

```json
{
  "proto": "1.0",
  "model": "diff-01",
  "capabilities": [
    {"id": "drive.diff", "cmd": "SET_VEL",
     "limits": {"v_max": 0.6, "w_max": 1.8, "a_max": 0.8}},
    {"id": "sensor.tof", "fields": {"left": "m", "right": "m"}, "rate_hz": 20},
    {"id": "sensor.imu", "fields": {"yaw": "rad", "pitch": "rad"}},
    {"id": "actuator.gripper", "range": [0, 1], "max_force_n": 20}
  ]
}
```

能力描述是**技能合法性的唯一依据**：技能声明的 `requires` 必须全部出现在这份清单里，否则拒绝部署。

#### 底盘强制安全

以下保护必须在底盘固件内实现，**不允许由技能层覆盖**：

- 速度、角速度、加速度硬限幅；
- 指令超时（200 ms 无心跳或新指令）自动停车；
- 硬件急停回路直接切断电机使能；
- 过流、过温、倾角超限保护；
- 故障锁存，必须显式 `CLEAR_FAULT` 才能恢复；
- `ARM` 之前拒绝任何运动指令。

技能层可以“请求更快”，但底盘只按自己的上限执行，并在遥测中回报实际值。这样 AI 生成的代码即使有错，也不会突破物理安全边界。

### 9.4 运行时契约

技能只允许通过 `ctx` 访问外部世界：

```python
def setup(ctx):
    ctx.chassis.require("drive.diff", "sensor.tof")
    ctx.state = {"phase": "idle"}

def step(ctx):
    tof = ctx.chassis.read("tof.left")
    if tof < ctx.params["stop_distance"]:
        ctx.log.outcome("avoid", ok=False, observed={"tof": tof})
        ctx.chassis.stop()
        return
    ctx.chassis.set_velocity(ctx.params["speed"], 0.0)

def on_event(ctx, e):
    if e["type"] == "fault":
        ctx.chassis.stop()

def teardown(ctx):
    ctx.chassis.stop()
```

| `ctx` 成员 | 作用 | 约束 |
| --- | --- | --- |
| `ctx.chassis` | 读能力、读遥测、发运动/执行器命令 | 只能调用 `requires` 中声明过的能力 |
| `ctx.log` | `intent / plan / action / outcome / mark` | 自动补 `cid`、`seq`、`t` |
| `ctx.params` | 校验后的技能参数 | 只读，范围由 `skill.json` 约束 |
| `ctx.now_ms()` | 单调时钟 | 禁止直接读硬件计时器 |
| `ctx.deadline_ms(n)` | 声明本步预算 | 超时由监督器记录并跳过下发 |

监督器在每次 `step` 前后执行：

1. 能力 ACL 检查；
2. 命令频率与幅度检查（超限则夹紧并写 `WARN`）；
3. 单步耗时预算（默认 20 ms，超时写 `assert`）；
4. 心跳续期；
5. 急停与故障状态检查，命中则跳过 `step`。

### 9.5 技能包

```text
pkg-patrol-0.3.1/
├── skill.json
└── app/
    ├── main.py
    ├── behaviors/
    │   └── follow_wall.py
    └── params.json
```

```json
{
  "id": "patrol",
  "version": "0.3.1",
  "entry": "app.main",
  "mode": "shadow",
  "requires": ["drive.diff", "sensor.tof", "sensor.imu"],
  "params": {
    "speed": {"type": "float", "min": 0.1, "max": 0.5, "default": 0.3},
    "stop_distance": {"type": "float", "min": 0.15, "max": 0.5, "default": 0.25}
  },
  "safety": {
    "max_speed": 0.5,
    "stop_on": ["tof.left < 0.2", "battery < 20"],
    "max_runtime_s": 600
  },
  "metrics": ["goal_reached", "abort_count", "collision_count", "time_s"]
}
```

技能包校验流水线（顺序执行，任一失败即拒绝）：

| 步骤 | 检查 | 失败后果 |
| --- | --- | --- |
| 1 | `skill.json` schema 与参数范围 | 拒绝 |
| 2 | `requires` ⊆ 底盘能力表 | 拒绝 |
| 3 | 导入白名单与 AST 静态检查（禁止 `machine` 直连、`eval`、动态导入） | 拒绝 |
| 4 | 设备端 `compile()` 语法检查 | 拒绝 |
| 5 | **shadow 模式**：只记录“本应下发的命令”，不真正驱动 | 转人工或延长观察 |
| 6 | **人工确认**：首次上线或大版本变更需审批令牌 | 保持 shadow，不生效 |
| 7 | live 上线，指标回流 | 异常自动回滚 |

第 5 步是 AI 生成代码能否直接上机的关键：影子模式让新技能在真实传感器输入下完整跑一遍决策，只把执行动作写进日志，再由上位机对比“意图 vs 实际”，确认无危险后才允许 `mode: live`。第 6 步可由上位机 UI 完成，但令牌校验必须在设备端执行，详见 9.12。

### 9.6 双环运行逻辑

整机由两个时间尺度的闭环组成：

```mermaid
flowchart LR
    subgraph FAST["快环 · 设备 20~50 Hz"]
        S1["读取遥测"] --> S2["技能决策"]
        S2 --> S3["监督器校验"]
        S3 --> S4["底盘执行"]
        S4 --> S5["记录 intent/action/outcome"]
    end

    subgraph SLOW["慢环 · 上位机 AI"]
        H1["读 EXPLAIN.md / 指标"] --> H2["归因与假设"]
        H2 --> H3["生成或修改技能"]
        H3 --> H4["校验 + 影子运行"]
        H4 --> H5["部署上线"]
        H5 --> H1
    end

    S5 -.会话文档.-> H1
    H5 -.技能包.-> S2
```

| 环 | 周期 | 负责 | 不允许做的事 |
| --- | --- | --- | --- |
| 快环 | 20~50 ms | 感知、决策、执行、记录 | 不做网络请求、不做文件压缩、不阻塞 |
| 慢环 | 分钟级 | 归因、生成代码、验证、部署 | 不直接控制电机 |

快环必须是确定性的：同样的遥测输入应产生同样的动作序列。因此技能里禁止网络调用、随机数（除显式种子）和长时间阻塞。

### 9.7 状态机与权限

```mermaid
stateDiagram-v2
    [*] --> BOOT
    BOOT --> SELF_TEST
    SELF_TEST --> IDLE
    IDLE --> ARMED : ARM
    ARMED --> IDLE : DISARM
    ARMED --> RUN : 首个运动指令
    RUN --> ARMED : 任务结束
    ARMED --> FAULT : 故障 / 急停
    RUN --> FAULT : 故障 / 急停
    FAULT --> IDLE : CLEAR_FAULT
    IDLE --> UPDATE : 收到技能包
    UPDATE --> IDLE : 校验完成
```

| 状态 | 允许动作 | 进入条件 | 记录 |
| --- | --- | --- | --- |
| `BOOT` | 挂载、校验、恢复 | 上电 | `ev=boot` |
| `SELF_TEST` | 传感器自检、能力核对 | 启动 | `ev=assert` |
| `IDLE` | 读遥测、接收更新 | 自检通过 | `ev=state` |
| `ARMED` | 接收运动指令 | 上位机 `ARM` + 物理使能 | `ev=state` |
| `RUN` | 执行技能 | 首个运动指令 | `ev=state` |
| `FAULT` | 只读、清故障 | 底盘故障 / 监督器触发 | `ev=state`、`CRIT` |
| `UPDATE` | 写非活动槽、校验 | 仅从 `IDLE` 进入 | `ev=reload` |

权限约定：

- `ARM` 需要“物理使能 + 软件确认”双重条件，避免纯 AI 误触发；
- 急停在任何状态都有效，且优先于所有软件逻辑；
- 更新只能在 `IDLE` 且 `DISARM` 时应用；
- `FAULT` 下禁止更新与运动，只能读取与清故障。

### 9.8 与调试采集系统的复用

这两套东西不是两个项目，而是同一个内核的两种用法：

| 组件 | 调试采集系统 | 机器人运行时 | 复用方式 |
| --- | --- | --- | --- |
| `logcore/`（record / ring / writer / session） | 采集传感器与系统日志 | 记录决策链与执行结果 | 完全复用 |
| 会话目录与文档规范 | `LOG.md` + `README.md` | 增加 `EXPLAIN.md` + `skill.json` | 同一套目录 |
| `sinks/`（Flash / SD / U 盘 / 网络） | 落盘与导出 | 同左 | 完全复用 |
| `updater.py`（A/B 槽位、回滚） | 更新应用 | 更新技能包，增加 `requires` 校验 | 同一实现 |
| HTTP 服务 | `/tail` `/range` `/file` | 增加 `/state` `/why` `/update` | 同一服务多路由 |
| `robot.json` | 设备与传感器自描述 | 由底盘 `CAPS` 动态生成能力表 | 同一份文件 |
| `/CTL` 命令通道 | 采样率、日志级别 | 增加 `ARM` / `DISARM` / 技能参数 | 同一通道，白名单不同 |
| 掉电恢复 | 截断最后一行 | 额外恢复 `bootcnt` 与状态快照 | 同一套扫描逻辑 |

一句话概括三者的关系：

- **调试采集系统** 提供 L0 事实；
- **解释层** 在 L0 之上补 L1 决策与 L2 归因；
- **技能层** 消费 L0/L1 的反馈，改写自己的行为。

因此工程上只维护一个 `kernel/`，不要为机器人另写一套日志系统。

### 9.9 统一工程目录

```text
robot/
├── chassis-fw/              # 固定协议固件（C/C++，独立构建，极少变更）
│   ├── protocol/
│   ├── motor/
│   └── safety/
├── kernel/                  # MicroPython 运行时（本方案主体）
│   ├── logcore/
│   ├── sinks/
│   ├── probes/
│   ├── updater.py           # 技能包 A/B 热更新
│   ├── ota/                 # 独立 OTA 子系统（与主逻辑隔离）
│   ├── approval.py          # 人工确认令牌校验
│   ├── supervisor.py
│   └── chassis_client.py
├── skills/                  # 技能包源码（AI 生成，按版本发布）
│   ├── patrol/
│   └── fetch/
├── host/                    # 上位机工具
│   ├── skillctl/            # 生成、校验、打包、部署、回滚
│   ├── logctl/              # 取日志、/why 查询
│   └── mcp/                 # 暴露给智能体的工具集
└── docs/                    # 会话文档与协议文档
```

技能包不是直接改设备上的 `app_a/`，而是由 `skillctl` 打包成带哈希与 `requires` 的更新包，走第 8 章的更新流程写入非活动槽。这样“AI 改逻辑”与“设备上运行”之间始终有一道校验与回滚。

### 9.10 技能粒度约定

- **同一时刻只运行一个技能**，避免多个策略争抢底盘；
- 通用动作（如 `drive_to`、`avoid`）放在 `kernel/behaviors/`，技能只做组合；
- 需要多技能切换时，由一个上层 `policy` 技能按优先级调度，而不是让多个技能并发下发指令；
- 每个技能必须声明 `max_runtime_s`，到期自动 `DISARM` 并写 `ev=close`。

### 9.11 多链路分工与仲裁

四条链路各有明确职责，不互相顶替：

| 链路 | 对端 | 职责 | 典型流量 | 实时性 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| **UART0** | 底盘 MCU | 固定帧协议：运动、遥测、心跳、底盘 OTA 转发 | 20~50 Hz，小帧 | 硬实时 | 最高 |
| **BLE** | 手机 / 平板 | 用户手动交互：ARM/DISARM、点动、急停、审批 | 低频小包 | 中 | 高（安全） |
| **WiFi** | 上位机 | 大数据：会话回传、技能包、固件镜像、日志流 | 高带宽 | 低 | 中 |
| **UART1** | 上位机 | 小数据：CLI、配置、心跳、无网恢复、OTA 备用通道 | 中低频 | 中 | 中高 |

表中的 `UART0` / `UART1` 是**逻辑编号，不是物理外设编号**。ESP32-C3 的 UART0 默认承担 REPL 与烧录，建议把底盘协议映射到 UART1，把 UART0 或原生 USB Serial/JTAG 留给调试；具体引脚在 `board.py` 显式声明，不依赖默认复用。

```mermaid
flowchart LR
    BLE["BLE<br/>用户手动"] --> R
    WIFI["WiFi<br/>大数据"] --> R
    U1["UART1<br/>上位机小数据"] --> R
    U0["UART0<br/>底盘"] <--> R
    R["命令仲裁<br/>鉴权 · 租约 · 去重"] --> APP["技能 / 日志 / OTA"]
```

仲裁规则：

1. **UART0 专用于底盘**，其他链路不得直接下发运动帧；
2. 所有外部命令进入同一个 `dispatcher`，携带 `src`、`auth`、`seq`，按 `seq` 去重；
3. **控制租约（lease）**：同一时刻只允许一个来源持有“运动控制权”，BLE 用户与上位机 AI 互斥；租约默认 2 s，靠心跳续期，`ESTOP` 或物理使能可立即抢占；
4. 优先级：`ESTOP` > `ARM/DISARM` > 运动指令 > 参数 > OTA > 日志上传；
5. 大数据传输必须限速，OTA 下载只在 `IDLE` 进行，会话回传可在 `RUN` 中低速进行。

C3 基础版必须增加一条硬约束：**BLE 与 WiFi 互斥**。用链路模式而不是“同时打开”：

| 模式 | 开启 | 用途 | 关闭 |
| --- | --- | --- | --- |
| `LOCAL`（默认） | BLE + UART0/UART1 | 手动交互、审批、技能包更新 | WiFi |
| `UPLINK` | WiFi + UART0 | 日志回传、固件 OTA、大数据 | BLE |
| `SERVICE` | UART1 + UART0 | 无网恢复、底盘烧录 | BLE / WiFi |

切换模式必须在 `IDLE` + `DISARM` 下进行，切换后重新广播或重连，并写一条 `ev=link` 记录。S3 可放宽为并发，但建议仍保留模式概念，便于排查。

断链行为必须预先定义：

| 断链 | 设备行为 |
| --- | --- |
| UART0 超时 200 ms | 底盘固件自动停车；ESP32 写 `ev=link`，进入 `FAULT` 等待恢复 |
| BLE 断开且持有租约 | 500 ms 后自动 `DISARM`，技能停止 |
| WiFi 断开 | 日志继续本地落盘，OTA 暂停并可续传，不影响控制 |
| UART1 断开 | 不影响运行，仅失去维护与备用通道 |

### 9.12 人工确认层

确认层解决的是“谁有权让一个新行为真正生效”，它属于运行时能力，而不是某个界面的按钮。

#### 默认策略

| 动作 | 默认确认级别 |
| --- | --- |
| `ESTOP` | 无需确认，任何来源立即执行 |
| `ARM` | 物理使能 + 软件确认，双条件 |
| 技能首次上线 / 大版本变更 | 上位机人工确认 |
| 技能小版本补丁（shadow 通过、差异在阈值内） | 可自动 |
| 参数在安全范围内微调 | 自动 |
| 参数越界、解除限幅 | 拒绝；仅维护模式可改 |
| ESP32 / 底盘固件 OTA | 默认人工确认 |
| `CLEAR_FAULT` | 人工确认，且必须静止 |

模式可配置为 `manual`（全部确认）、`assisted`（仅高风险确认，推荐）、`auto`（白名单内自动）。

#### 确认令牌

确认结果不是一句口头同意，而是一枚可验证、一次性、绑定工件的令牌：

```json
{
  "approval_id": "ap-7f3c",
  "action": "ota.apply",
  "target": "chassis-fw@1.4.2",
  "artifact_sha256": "…",
  "issued_by": "host-ui:user-01",
  "issued_at": 1760000000,
  "expires_at": 1760000300,
  "nonce": "9a1c…",
  "mode": "manual",
  "signature": "ed25519:…"
}
```

设备端校验五件事后才执行：签名有效、未过期、`nonce` 未使用、`artifact_sha256` 与实际工件一致、`action/target` 与待执行项一致。令牌一次性写入 `/AUTH/used.jsonl`，防止重放。

```mermaid
sequenceDiagram
    participant AI as 上位机 AI
    participant UI as 确认界面
    participant D as 设备运行时
    AI->>D: proposal（动作、目标、哈希、风险）
    D->>UI: 推送待确认项与差异摘要
    UI->>UI: 用户查看风险、版本、回滚点
    UI->>D: approval_token（nonce、过期、签名）
    D->>D: 校验签名、时效、哈希、一次性
    D->>AI: 执行结果 + 审计记录
```

落地位置：

- **上位机 UI 为主**：展示差异、风险、影响范围、回滚方案，用户可选择“执行一次 / 加入信任 / 拒绝”；
- **设备端为强制点**：即使绕过 UI 直接调接口，没有合法令牌也无法 apply；
- **BLE 作为现场二次确认**：适合手机靠近设备时确认 `ARM` 或急停复位；
- **物理按键**：作为 OTA 或恢复模式的最后一道人工确认。

所有确认与拒绝都写入 `approvals.jsonl` 和 `ev=approval`，让智能体知道“这一步是人批准的，还是策略放行的”。

### 9.13 双板分离的工程约定

ESP32 大脑与底盘控制器可能是两块独立板子，只靠线束连接，需要把电气与启动约定写死：

#### 连接器与电气

| 引脚 | 定义 | 说明 |
| --- | --- | --- |
| 1 | `5V_IN` | 供电或检测，按实际功率设计 |
| 2 | `GND` | 必须共地 |
| 3 | `BRAIN_TX → CHASSIS_RX` | 3.3 V 电平 |
| 4 | `BRAIN_RX ← CHASSIS_TX` | 3.3 V 电平 |
| 5 | `LINK_DET` | 可选：链路存在/心跳指示 |
| 6 | `GND` | 双地冗余 |

- 两侧均为 3.3 V；若必须跨电平，使用电平转换，不得 5 V 直连；
- TX 串 33~100 Ω，接口加 TVS，线束远离电机动力线，必要时用双绞线；
- 两板独立供电时，优先使用数字隔离器，避免地环流。

#### 启动与发现

- 不假设固定上电顺序：ESP32 每 500 ms 发一次 `HELLO`，指数退避，直到收到 `CAPS`；
- `CAPS` 到手后比对技能 `requires`，缺能力则拒绝进入 `ARMED`；
- 两板各自有独立看门狗，不依赖对方复位；
- 热插拔后重新 `HELLO` + 能力核对，运行中的技能立即 `DISARM`。

#### 底盘固件的 OTA 通道

底盘固件由 ESP32 经 UART0 转发：ESP32 下载完整镜像并校验，再进入 `UPDATE`，按帧分块写入底盘 bootloader，最后触发底盘重启。

若底盘变砖：

- ESP32 进入维护模式，把 UART0 透传给 UART1，上位机可直接对底盘烧录；
- 或使用底盘板上的 USB/调试口现场恢复；
- 该模式不加载技能，只保留串口桥与日志。

---

## 10. 可靠性设计

### 10.1 掉电恢复

启动时执行一次扫描：

```python
def recover(path):
    last_good = 0
    last_seq = 0
    with open(path, "rb+") as f:
        while True:
            line = f.readline()
            if not line:
                break
            if not line.endswith(b"\n"):
                break                      # 末尾截断，回退
            try:
                rec = json.loads(line)
            except ValueError:
                break                      # 损坏行，回退
            if rec["seq"] <= last_seq:
                break                      # 序号异常，回退
            last_seq = rec["seq"]
            last_good = f.tell()
        f.truncate(last_good)              # 截断到最后完整行
    return last_seq
```

恢复结果写入新会话的 `boot` 记录，包含：上一个会话名、恢复到的 `seq`、丢弃字节数。

### 10.2 时间同步

- 每条记录必须写 `t`（单调时钟），`ts` 可为空；
- 会话开始时由主机写入一次基准：`POST /ctl {"cmd":"set_time","epoch":...}`；
- 有 RTC 时每次写记录读取 RTC 成本过高，改为每 60 s 用 RTC 校正一次 `epoch = rtc + ticks_diff(now, base_ticks)/1000`；
- `ticks_ms()` 会回绕，所有差值必须用 `time.ticks_diff()`，禁止直接相减。

### 10.3 背压与丢弃

| 策略 | 行为 | 适用 |
| --- | --- | --- |
| `drop_oldest` | 覆盖最旧记录，累计 `dropped` | 默认，保证最新现场 |
| `drop_level` | 优先丢弃 `DEBUG`，再丢 `INFO` | 诊断期保留关键事件 |
| `block` | 生产者等待 | 仅用于非实时任务 |

丢弃后必须写一条 `ev=drop` 汇总记录（含 `count` 与 `first_seq`），否则分析时无法解释缺口。

### 10.4 介质降级

- SD 卡写入失败：标记 Sink 不可用，切到 Flash，写 `degrade` 记录；
- Flash 分区剩余 < 10%：删除 `_trash/` 中最旧会话；
- 所有介质满：只保留 RAM 环形缓冲，并通过 BLE/MQTT 发 `CRIT`；
- 网络断开：`NetSink` 进入重试队列，恢复后按 `seq` 续传，不重发已确认记录。

### 10.5 存储介质注意事项

| 介质 | 注意点 |
| --- | --- |
| 内置 Flash | 必须使用独立分区与 LittleFS；避免高频小写；轮转而非原地覆盖 |
| SD 卡 | 掉电可能损坏 FAT 目录项，建议每次会话结束显式 `sync` 并 `umount` |
| USB MSC | 主机挂载期间设备不能同时写同一分区，需明确「记录模式 / 导出模式」互斥 |
| U 盘 | 通过 USB OTG 主机模式挂载，需外部供电；插拔检测要做去抖 |

---

## 11. 资源与性能预算

以 ESP32-S3（约 300 KB 可用 heap）为例：

| 项目 | 预算 | 说明 |
| --- | --- | --- |
| RAM 环形缓冲 | 16 KB | 约 100 条 JSON 记录或 1000 条 IMU 样本 |
| 序列化缓冲 | 1 KB | 复用，避免 GC |
| Writer 批量缓冲 | 4 KB | 每次取数上限 |
| 协议栈 / Socket | 30~60 KB | 仅在 WiFi 开启时占用 |
| 单条 JSON 记录 | 120~200 B | 字段越多越大 |
| 写入吞吐 | 20~80 KB/s | Flash 与 SD 差异较大 |
| 典型日志量 | 2~10 MB/天 | 1 Hz × 4 通道 + 事件 |

Flash 寿命估算：若每分钟 flush 一次、每次 4 KB，则每天写入约 5.8 MB；对于 100k 擦写次数的 NOR/NAND，建议日志分区不小于 512 KB 并做文件轮转，避免单扇区热点。

---

## 12. 部署与运行

### 12.1 最小系统（P0）

```text
开发板
├── I2C: SCL=22, SDA=21 → BMP280 (0x76)
├── Flash: 内部 LittleFS 分区 /LOG
└── USB: REPL + 可选 MSC
```

启动流程：

1. `boot.py`：挂载 LittleFS，读取 `current.json` 与 `bootcnt`，选择 `app_a` / `app_b`；
2. 扫描 `/LOG` 最后会话，执行截断恢复；
3. 创建新会话目录，写 `manifest.json` 与 `robot.json`；
4. 打开 Sink，初始化总线与传感器；
5. 导入应用槽位，调用 `setup(ctx)`；
6. 启动采样调度与 Writer 任务，心跳正常 5 s 后确认本次启动成功（清零 `bootcnt`）；
7. 捕获 `KeyboardInterrupt` / 软复位，调用 `teardown()`、写 `close` 并生成 `LOG.md` 与 `EXPLAIN.md`。

### 12.2 主机侧取数

```bash
# 方式一：直接拷贝（SD / U 盘 / MSC）
cp -r /media/USER/LOG/S20261016-142530 ./session

# 方式二：HTTP 增量拉取
curl "http://192.168.4.1/range?session=S20261016-142530&from=10231&limit=500"

# 方式三：下载整份日志（支持断点续传）
curl -C - -o events.jsonl \
  "http://192.168.4.1/file?session=S20261016-142530&path=events.jsonl"
```

### 12.3 智能体分析入口

```bash
# 先看摘要
cat session/LOG.md

# 再看错误
jq 'select(.lvl=="ERROR" or .lvl=="CRIT")' session/events.jsonl

# 最后按时间窗定位原始数据
jq 'select(.src=="bmp280" and .t>=60000 and .t<120000)' session/events.jsonl
```

---

## 13. 实施计划

| 阶段 | 整机能力 | 日志 / 解释能力 | 验收标准 |
| --- | --- | --- | --- |
| P0 | 串口协议客户端，只读遥测（`HELLO` / `CAPS` / `TELEM`），不发运动指令；**C3 + 4 MB Flash 基础板** | JSONL + LittleFS + manifest + 断点恢复 | 能看到底盘遥测，拔电后恢复到最后一条完整记录 |
| P1 | `ARM` / `DISARM` + `SET_VEL` + 限幅与 200 ms 超时验证 | Sink 抽象 + SD 卡 + 轮转 + `LOG.md` | 手动遥控可跑，断链自动停车，日志连续 |
| P2 | 技能生命周期 `setup/step/on_event` + 参数 + 能力 ACL | `intent/plan/action/outcome` + `EXPLAIN.md` + `/why` | 单个巡逻技能可跑，能回答“为什么停下” |
| P3 | shadow 模式 + 技能包 A/B + **人工确认层**（首次上线） | `ev=reload` 版本分段 + `/state` + `approvals.jsonl` | 新技能先影子后上线，未经确认无法生效 |
| P4 | `skillctl` + MCP 工具 + 指标回流 + 版本对比 | HTTP 拉取 + `index.jsonl` + 多会话 | AI 能读日志 → 改技能 → 再部署，闭环成立 |
| P5 | **OTA 子系统**：ESP32 固件 WiFi 下载/校验/双槽/回滚，底盘固件经 UART0 转发 | `ev=ota` 记录与版本切分 | 断网可续传，坏镜像自动回滚，不丢会话 |
| P6 | 多链路仲裁 + BLE 手动接管 + policy 多技能调度 | 高频二进制 + 版本差异量化 | 链路互斥正确，连续运行稳定 |

底盘 bootloader 的升级帧类型与双槽约定，必须在 P0 / P1 就预留，但功能实现可以放到 P5——**协议要提前留位，实现可以延后**。

建议顺序：**先把 P0 / P1 的协议与安全边界打通**，这是不可回退的基础；再做 P2 / P3 的解释与确认；然后 P4 接 AI 慢环；最后 P5 / P6 补 OTA 与多链路。不要一上来就让 AI 生成动作逻辑——没有硬限幅、影子、人工确认和反馈数据，生成的代码既无法验证也无法归因。

### 13.1 P0 的第 0 步：先抓包，再写解析器

底盘协议是固定的，但**文档与固件经常不一致**。在写 `chassis.py` 之前，先用 USB-TTL 或逻辑分析仪录下真实帧：

- 上电后底盘主动发什么、周期多少；
- 上位机是否需要先发握手帧，底盘才回遥测；
- 帧头、长度、校验方式、字节序、有无转义；
- 遥测字段的缩放系数与单位（例如速度是 mm/s 还是 0.1 mm/s）；
- 断链后底盘是停车、保持，还是进入故障态。

把 20~30 帧存成 `captures/*.bin`，作为解析器的测试向量。**这一步不做，后面所有“协议已打通”的结论都不可信。**

### 13.2 C3 接线与引脚建议

以 ESP32-C3-WROOM-02-N4 / DevKitM-1 为例，避开 strapping 与 Flash 占用引脚：

| 信号 | 建议引脚 | 说明 |
| --- | --- | --- |
| 底盘 UART TX | GPIO6 | 接底盘 RX，3.3 V 电平 |
| 底盘 UART RX | GPIO7 | 接底盘 TX；若底盘为 5 V TTL，加分压或电平转换 |
| 调试 / 烧录 | USB D-/D+（GPIO18/19） | 原生 USB Serial/JTAG，保留 REPL 与 esptool |
| 急停输入 | GPIO4 | 上拉输入，低有效；同时接入硬件断电回路 |
| 状态指示 | GPIO5 | 心跳、故障、OTA 状态 |
| 电源 | 5V / GND | 与底盘共地，加 TVS 与去耦 |
| BOOT | GPIO9 | 仅烧录时使用，业务中禁止复用 |
| 禁用 | GPIO2 / 8 / 9 / 11~17 | strapping、VDD_SPI、片内 Flash |

接线原则：串阻 + TVS、远离电机线、两板共地；长线或强干扰环境改用隔离收发器。**急停必须同时切断驱动使能，不能只进 GPIO。**

### 13.3 4 MB Flash 的分区取舍

| 区域 | 典型大小 | 说明 |
| --- | --- | --- |
| bootloader + 分区表 | < 64 KB | 由构建生成，不手改 |
| app（MicroPython） | 1.4~1.6 MB | 固件本体 |
| nvs | 16~24 KB | WiFi/BLE 校准与配置 |
| LittleFS | 剩余约 1.4~2 MB | 日志、技能包、配置；留 10% 余量 |

具体偏移以所用 MicroPython 构建的 `partitions-4MiB.csv` 为准。**4 MB 上不要规划固件 A/B 双槽**：两个 app 槽已占满，没有空间放日志。基础版的策略是“技能 BLE 热更新 + 固件 USB/UART1 维护升级”；需要固件 OTA 时换 8 MB 模块或 S3。

容量还要算一笔账：1 Hz、单条约 150 B，一天约 13 MB。**4 MB 内置 Flash 只能保留几小时**，不是“够不够写”的问题，而是“能回溯多久”的问题。基础版有两条路：

- 降频或聚合：只在数值变化超过阈值时落 `sample`，其余写 1 分钟一条的摘要；
- 加 SD 卡（P1）：长时间无人值守必须上 SD，内置 Flash 只做最近窗口与掉电兜底。

### 13.4 P0 模块清单

| 文件 | 职责 | P0 范围 |
| --- | --- | --- |
| `boot.py` | 挂载文件系统、读配置、启动运行时、失败时保留 REPL | 必须 |
| `main.py` | 入口、看门狗、顶层异常兜底 | 必须 |
| `board.py` | 引脚映射、UART 初始化、LED、链路模式 | 必须 |
| `config.json` | 设备 ID、波特率、采样率、日志上限、链路模式 | 必须 |
| `logcore.py` | record / ring / writer / session / CRC / 恢复 | 必须 |
| `sink.py` | `FlashSink`（P0）、`NullSink` | 必须 |
| `chassis.py` | 帧编解码、握手状态机、`seq` 丢帧统计 | 必须 |
| `runtime.py` | 状态机、采样调度、链路切换 | 必须 |
| `diag.py` | 启动自检、heap / uptime 周期采样 | 建议 |
| `tools/logctl.py` | 上位机侧拉取、解析、校验 | 建议 |

协议解析保持可替换，不要把帧格式写进运行时：

```python
class FrameCodec:
    """固定协议适配层：P0 只实现 decode，encode 仅 HELLO/HEARTBEAT。"""
    def feed(self, buf):
        # 追加到内部缓冲，返回 [(msg_type, payload), ...]
        ...

    def encode(self, msg_type, payload):
        ...
```

注意区分两个序号：日志 `seq` 是本系统自增的，底盘帧里的 `seq` 要原样记到 `m.chassis_seq`。底盘 `seq` 跳变时写一条 `ev=drop, m={"n": 缺失数}`，这是判断 UART 丢帧的唯一可靠依据。

### 13.5 P0 验收用例

| # | 场景 | 通过标准 |
| --- | --- | --- |
| 1 | 上电握手 | 3 s 内发出 `HELLO`，收到 `CAPS` 并写入会话快照 |
| 2 | 遥测连续性 | 20 Hz 连续 10 min，底盘 `seq` 丢帧率 < 0.1% |
| 3 | 掉电恢复 | 连续拔电 10 次，每次都能恢复到最后一个完整记录 |
| 4 | 会话完整性 | 目录含 `manifest.json` / `events.jsonl` / `index.jsonl`，`close.reason` 正确 |
| 5 | 容量轮转 | 剩余空间 < 10% 时触发轮转，旧会话按策略淘汰 |
| 6 | 链路断开 | UART 静默 200 ms 后写 `ev=link`，进程不崩溃、不重启 |
| 7 | 长稳 | 连续 24 h，`gc.mem_free()` 无持续下降趋势 |
| 8 | 可解析性 | 上位机解析 `events.jsonl`，除最后截断外 100% 可读 |

### 13.6 P0 启动时序

```mermaid
sequenceDiagram
    participant B as boot.py
    participant R as runtime
    participant C as chassis
    participant L as logcore
    B->>R: 挂载 FS、读 config
    R->>L: 开 Session（写 manifest 草稿）
    R->>C: HELLO（500 ms 重试）
    C-->>R: CAPS
    R->>L: 写 boot / CAPS 快照
    R->>C: 订阅 TELEM
    loop 20~50 Hz
        C-->>R: TELEM
        R->>L: emit(sample)
    end
    Note over R,L: writer 独立 flush、轮转、恢复
```

### 13.7 可运行骨架

P0 的最小实现已落在 `robot-runtime/`，与上面的模块清单一一对应：

| 文件 | 作用 |
| --- | --- |
| `logcore.py` | 会话、JSONL 追加、索引、轮转、掉电截断恢复 |
| `sink.py` | `FileSink` / `NullSink`，P1 再扩 SD 与网络 |
| `chassis.py` | `FrameCodec` 接口、`MockCodec`、握手与 `seq` 丢帧统计 |
| `runtime.py` | 状态机、1 Hz 降采样、链路超时 |
| `board.py` | C3 引脚与 UART 初始化 |
| `boot.py` / `main.py` | 启动与异常兜底 |
| `config.json` | 设备、串口、日志、运行时参数 |
| `tools/logctl.py` | 上位机侧 `verify` / `summary` / `tail` |
| `tests/test_p0.py` | 主机侧回归测试 |

主机侧自测：

```sh
cd robot-runtime
python3 tests/test_p0.py
python3 tools/logctl.py verify /tmp/p0demo/SDEMO
```

当前测试覆盖：掉电截断恢复、轮转与索引、逐字节粘包/拆包、底盘 `seq` 丢帧、运行时写 `sample`、200 ms 链路超时。

上机时把 `.py` 与 `config.json` 复制到设备根目录即可，`main.py` 会自动执行。**`MockCodec` 只是占位**：拿到 13.1 的抓包后，实现对应的 `FrameCodec` 并替换 `main.py` 里的一行，`runtime` 不需要改动。

```python
# main.py
link = ChassisLink(uart, RealCodec(), timeout_ms=200)
```

---

## 14. 风险与取舍

| 风险 / 取舍 | 影响 | 应对 |
| --- | --- | --- |
| JSONL 体积大 | 占用更多 Flash、传输更慢 | 高频数据走二进制；JSONL 可 gzip 归档 |
| flush 间隔 | 掉电丢最后 1 s 数据 | 关键事件（ERROR/CRIT）立即 flush |
| Flash 磨损 | 分区寿命下降 | 独立分区、文件轮转、批量写 |
| SD 卡掉电损坏 | 会话不可读 | 会话结束显式 sync；保留内部 Flash 兜底 |
| BLE 带宽低 | 无法传大文件 | 只传摘要与告警，大文件走 WiFi/SD |
| 时钟不统一 | 多设备日志无法对齐 | 统一 `t0_epoch` 基准，`t` 单调、`ts` 可空 |
| MSC 与写入冲突 | 文件系统损坏 | 记录模式与导出模式互斥 |
| 明文 HTTP | 信息泄露 | 默认 AP 模式；可选 token；日志脱敏 WiFi 密码 |
| 智能体误读 | 结论错误 | `README.md` 声明单位、质量位、缺口语义 |
| 解释层“自圆其说” | 归因偏离物理事实 | 同时记录 `expect` 与 `observed`；缺失环节显式标注为缺口 |
| 热更新版本不兼容 | 新应用调用了旧内核不存在的接口 | `kernel_min` 校验 + 导入白名单 + 回滚 |
| 更新过程掉电 | 应用目录损坏 | A/B 双槽 + 指针切换 + `bootcnt` 自动回退 |
| 双槽位占用空间 | Flash 容量紧张 | 只保留两个应用槽；日志分区独立并做轮转 |
| 应用持有旧对象引用 | 热重载后行为异常 | 强制 `teardown → setup` 重建，句柄统一由 `ctx` 提供 |
| 底盘协议版本漂移 | 技能按错误语义执行 | `HELLO` 校验协议版本，`CAPS` 写入会话快照 |
| AI 生成危险动作 | 设备或人身损伤 | 底盘硬限幅 + 急停 + shadow 模式 + 首次上线人工放行 |
| 技能单步超时 | 控制周期抖动、指令堆积 | `deadline_ms` 预算 + 超时跳过下发 + `assert` 记录 |
| 多技能争抢底盘 | 指令互相覆盖 | 同一时刻只运行一个技能，切换由 policy 统一调度 |
| 影子模式误判 | 上线后行为与观察不一致 | 对比 intended 与 actual，差异超阈值禁止转 live |
| OTA 与主逻辑争用资源 | 控制周期抖动 | 独立任务 + 仅 `IDLE` 下载 + UART0 链路专用 |
| OTA 镜像不兼容 / 变砖 | 设备无法启动 | `min_proto` 校验 + A/B 双槽 + 3 次失败回滚 + UART1 恢复 |
| 确认令牌重放 | 未授权动作被执行 | `nonce` + 过期时间 + 工件哈希绑定 + 一次性记录 |
| 多链路指令冲突 | 运动抖动或误动作 | 单一控制租约 + `seq` 去重 + 固定优先级 |
| 双板地环 / 电平不匹配 | 通信误码、偶发丢帧 | 共地或隔离 + 3.3 V 电平转换 + TVS + CRC 校验 |
| 人工确认仅靠 UI | 可绕过界面直接调接口 | 设备端强制验签，UI 只是发起端 |

---

## 15. 附录

### 15.1 故障排查清单

| 现象 | 可能原因 | 检查点 |
| --- | --- | --- |
| `events.jsonl` 为空 | Sink 未打开 / writer 未启动 | `/health` 的 `last_seq`、Sink 状态 |
| `seq` 大量缺口 | 环形缓冲溢出 | 搜索 `ev=drop` 记录 |
| 时间戳全为 null | 未校时且无 RTC | `manifest.clock.mode` |
| 日志停在某一时刻 | 掉电 / 看门狗复位 | `manifest.close` 是否缺失 |
| 记录重复 | 恢复后 `seq` 未续接 | 恢复逻辑是否读取了 `last_seq` |
| 文件系统挂载失败 | 分区损坏 | 重新格式化分区，保留 `_trash` |

### 15.2 最小记录样例（可直接用于单元测试）

```json
{"v":1,"seq":1,"t":0,"ts":null,"src":"sys","lvl":"INFO","ev":"boot","m":{"reset":"power_on"}}
{"v":1,"seq":2,"t":1000,"ts":null,"src":"bmp280","lvl":"INFO","ev":"sample","m":{"p":1003.2,"tc":24.6},"q":"ok"}
{"v":1,"seq":3,"t":2000,"ts":null,"src":"sys","lvl":"INFO","ev":"close","m":{"reason":"user"}}
```

### 15.3 术语

| 术语 | 含义 |
| --- | --- |
| 会话（Session） | 一次上电运行产生的完整日志集合 |
| Sink | 一个可写入的存储后端 |
| Probe | 一个可采样的数据源 |
| 环形缓冲 | 固定容量、写满覆盖最旧数据的内存队列 |
| 降级 | 某个存储或传输通道失效后切换到备用通道 |
