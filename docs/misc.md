# 外设 / 杂项模块（MISC）

目录：[misc/](../misc)｜包含 **EEPROM**、**RTC 实时时钟** 与 **irqUART**。

---

## 1. AT24XX EEPROM (`AT24XX`)

- 驱动：[AT24XX.py](../misc/AT24XX/AT24XX.py)｜示例：[test.py](../misc/AT24XX/test.py)｜文档：[README.md](../misc/AT24XX/README.md)
- **器件**：AT24/AT25 系列 EEPROM。**I2C 地址**：`0x50–0x57`（驱动内常量 `AT24CXX_I2C_ADDRESS = 80`，即 0x50）。
- **构造**：`AT24XX(i2c)`

| 方法 | 说明 |
| --- | --- |
| `write_byte(addr, dat)` / `read_byte(addr)` | 读写 1 字节 |
| `write_word(addr, dat)` / `read_word(addr)` | 读写 1 字（2 字节，大端） |
| `write_dword(addr, dat)` / `read_dword(addr)` | 读写 1 双字（4 字节，大端） |
| `write_buf(addr, buf)` | 从 `addr` 写缓冲区（最大 32 字节） |
| `read_buf(addr, num)` | 从 `addr` 读 `num` 字节 |

> 所有读写的前两字节为 16 位内部地址（`addr//256, addr`）。

### 示例

```python
from machine import I2C, Pin
import AT24XX

ee = AT24XX.AT24XX(I2C(sda=Pin(5), scl=Pin(4)))
ee.write_byte(0, 12)
ee.write_word(4, 0x1234)
ee.write_buf(800, b'Hello!')
```

---

## 2. RTC 实时时钟

三个 RTC 驱动共享统一 API：`DateTime([年,月,日,星期,时,分,秒])` 读写整组时间；各提供单项 `Year()/Month()/Day()/Weekday()/Hour()/Minute()/Second()` 的 get/set（不传参=读，传参=写）；`start()/stop()` 启停；BCD 转换 `DecToHex()/HexToDec()`。

### 2.1 DS1302 (`DS1302`) — 三线同步串口

- 驱动：[DS1302.py](../misc/DS1302/DS1302.py)｜示例：[test.py](../misc/DS1302/test.py)｜文档：[README.md](../misc/DS1302/README.md)
- **构造**：`DS1302(clk, dio, cs)`（3 个 `Pin`）；带 31×8 位 RAM。
- 特有：`wr(reg,dat)`（先解写保护再写回）、`ram(reg, dat=None)`（读写 31 字节 RAM）。

### 2.2 DS1307 (`DS1307`) — I2C

- 驱动：[DS1307.py](../misc/DS1307/DS1307.py)｜示例：[test.py](../misc/DS1307/test.py)｜文档：[README.md](../misc/DS1307/README.md)
- **I2C 地址**：`0x68`（常量 `DS1307_I2C_ADDRESS = 104`）。带 56 字节 NV SRAM。
- **构造**：`DS1307(i2c)`；`ram(reg, dat=None)` 读写 56 字节 RAM。

### 2.3 DS3231 (`DS3231`) — I2C + 闹钟

- 驱动：[DS3231.py](../misc/DS3231/DS3231.py)｜示例：[test.py](../misc/DS3231/test.py)｜文档：[README.md](../misc/DS3231/README.md)
- **I2C 地址**：`0x68`。功能最全。

| 方法 | 说明 |
| --- | --- |
| `DateTime(dat=None)` | 读写 `[年,月,日,星期,时,分,秒]` |
| `Date(dat=None)` / `Time(dat=None)` | 读写 `[年,月,日]` / `[时,分,秒]` |
| `Year()..Second()` | 各字段 get/set |
| `Temperature()` | 读取环境温度（含小数） |
| `ALARM(day, hour, minute, repeat)` | 设置闹钟与重复模式 |
| `ClearALARM()` | 清闹钟标志（需手动调用以复位 SQW 输出） |

**重复模式常量**：`PER_DISABLE`、`PER_MINUTE`、`PER_HOUR`、`PER_DAY`、`PER_WEEKDAY`、`PER_MONTH`。

### RTC 示例

```python
from machine import I2C, Pin
import DS3231

ds = DS3231.DS3231(I2C(sda=Pin(5), scl=Pin(4)))
print(ds.DateTime())
ds.DateTime([2018, 3, 12, 1, 22, 10, 0])
ds.ALARM(12, 20, 10, ds.PER_DAY)
ds.ClearALARM()
```

---

## 3. irqUART — 引脚中断模拟 UART 接收中断 (`irqUART`)

- 驱动：[irqUART.py](../misc/irqUART/irqUART.py)
- 示例：[irqUART_pyb_demo.py](../misc/irqUART/irqUART_pyb_demo.py)（PyBoard）、[irqUART_esp32_demo.py](../misc/irqUART/irqUART_esp32_demo.py)（ESP32）
- 文档：[README.md](../misc/irqUART/README.md)
- **用途**：`machine.UART` 不支持 RXD 中断的平台，改用 **RXD 引脚下降沿中断 + 定时器** 来模拟接收中断；可唤醒睡眠中的 MCU。

**构造**：
```python
irqUART(uart, rx_pin, rx_irq=None, frame_irq=None, CHR_TMO=3, FRAME_TMO=100)
```

| 参数 | 说明 |
| --- | --- |
| `uart` | `machine.UART` 对象（构造后需 `ui.uart.init(baudrate)` 初始化） |
| `rx_pin` | UART 的 RXD 引脚 |
| `rx_irq` | 用户"收到字符"中断回调 |
| `frame_irq` | 用户"一帧结束"中断回调（超时后触发） |
| `CHR_TMO` | 引脚中断后延迟多少 ms 触发字符中断（依波特率/缓冲而定） |
| `FRAME_TMO` | 最后一个字符后多少 ms 触发帧中断 |

**内部机制**：`_RXPIN_IRQ(t)` 在 RXD 下降沿启动一次性/周期定时器（`_RXPIN_IRQ → _TMRX → _TMRX_IRQ`）；`_TMRX_IRQ` 中调用 `rx_irq` 或 `frame_irq`。`self._mode` 依 `sys.platform` 在 `Timer.ONE_SHOT`(pyboard) / `Timer.PERIODIC` 间切换。

### 示例

```python
from machine import Pin, UART
from irqUART import irqUART

def U1_RX_IRQ(t):      print('char')
def U1_RX_FRAME_IRQ(t):print('FRAME end')

u1 = UART(1)
ui = irqUART(u1, Pin('B7'), U1_RX_IRQ, U1_RX_FRAME_IRQ)
ui.uart.init(115200)
```

> 大量收数据时，建议增大 uart `rxbuf` 避免丢数据。
