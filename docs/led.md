# LED 模块

目录：[LED/](../LED)｜覆盖 **I2C OLED ASCII 显示**、**TM1637**、**TM1650** 三种显示类驱动。

---

## 1. I2C OLED ASCII 显示 (`OLED_I2C_ASC`)

- **驱动文件**：[oled.py](../LED/OLED_I2C_ASC/oled.py)｜示例：[demo.py](../LED/OLED_I2C_ASC/demo.py)｜文档：[README.md](../LED/OLED_I2C_ASC/README.md)
- **器件**：SSD1306 控制器 128×64 I2C OLED。
- **默认 I2C 地址**：`0x3C`（常量 `OLED_ADDR`）。
- **字库数据模块**：[Font_6x8.py](../LED/OLED_I2C_ASC/Font_6x8.py)、[Font_8x16.py](../LED/OLED_I2C_ASC/Font_8x16.py)、[Font_12x24.py](../LED/OLED_I2C_ASC/Font_12x24.py)、[Font_16x32.py](../LED/OLED_I2C_ASC/Font_16x32.py)——以 `bytes` 导出 ASCII 点阵（覆盖 `' '`～`'~'`，即 0x20–0x7E）。
- **核心类**：`OLED12864_I2C(i2c, ADDR=OLED_ADDR)`

### 关键方法与属性

| 方法 | 说明 |
| --- | --- |
| `command(c)` | 发送 SSD1306 命令字节（前缀 `0x00`） |
| `set_pos(col=0, page=0)` | 设置显存列/页指针 |
| `pixel(x, y, color=1)` | 画单像素（越界自动忽略） |
| `invert(v=1)` / `on(v=1)` | 反色显示 / 显示开关 |
| `clear(c=0)` | 清屏（清空 1025 字节缓冲并刷屏） |
| `draw()` | 将 `screen` 缓冲写入 OLED |
| `hline(x, y, len, c)` / `vline(x, y, len, c)` / `rect(x1,y1,x2,y2,c)` | 水平线/垂直线/矩形框 |
| `line(...)` | **空实现（占位，未实现）** |
| `scroll()` | 按 8 像素字节滚动，超出后整体上移 |
| `char_6x8 / char_8x16 / char_12x24 / char_16x32 (x, y, ch, c)` | 指定字号绘制单字符 |
| `text_6x8 / text_8x16 / text_12x24 / text_16x32 (x, y, s, c, wrap)` | 指定字号绘制字符串（`wrap=1` 时自动换行） |
| `Font(Font)` | **绑定字号**：传入 `Font_8_16`/`'Font_8x16'` 等，把 `self.char`/`self.text` 指向对应实现（默认 `6x8`） |
| `font(FONT)` | 仅设置 `self.FONT` 属性（不改变绘制行为） |
| `print(s, c=1, cr=1)` | 流式打印，行尾自动 `scroll()` |

**字号常量**：`Font_6_8=1`、`Font_8_16=2`、`Font_12_24=3`、`Font_16_32=4`。
**属性**：`width=128`、`height=64`、`MAX_X=127`、`MAX_Y=63`；`self.char`/`self.text` 为动态绑定的绘制/de 函数。

### 示例

```python
from machine import I2C, Pin
from oled import OLED12864_I2C

i2c = I2C(-1, scl=Pin(27, pull=Pin.PULL_UP), sda=Pin(13, pull=Pin.PULL_UP))
oled = OLED12864_I2C(i2c)
oled.text(0, 0, '0123456789')        # 默认 6x8
oled.Font('Font_8x16')
oled.text(0, 1, '0123456789')
oled.Font('Font_12x24')
oled.text(0, 3, '0123456789')
```

---

## 2. TM1637 四位数码管 (`TM1637`)

- **驱动文件**：[TM1637.py](../LED/TM1637/TM1637.py)｜示例：[test.py](../LED/TM1637/test.py)｜文档：[README.md](../LED/TM1637/README.md)
- **器件**：TM1637 四位 7 段数码管，两线接口（CLK/DIO），**软件模拟时序**。
- **来源**：基于 mcauser 的 micropython-tm1637 移植。
- **核心类**：`TM1637(clk, dio, intensity=7, number=4)`

### 关键方法与属性

| 方法 | 说明 |
| --- | --- |
| `on()` / `off()` | 显示开/关 |
| `intensity(val=None)` | 设/取亮度；`val` 0–8，`0` 即关闭；不传参返回当前值 |
| `clear()` | 清空显示与缓冲 |
| `showbit(num, bit=0)` | 在指定位显示 0–15 的段码 |
| `showDP(bit=1, show=True)` | 显示/隐藏小数点 |
| `shownum(num)` | 显示十进制整数（负数显示 `-`） |
| `showhex(num)` | 显示十六进制 |
| `_start()/_stop()/_write_byte(b)/_write_data_cmd()/_write_dsp_ctrl()/_dat(bit, dat)` | 内部时序与命令原语 |

**常量**：`TM1637_CMD1=0x40`(数据命令)、`TM1637_CMD2=0xC0`(地址命令)、`TM1637_CMD3=0x80`(显示控制)、`TM1637_DELAY=10us`；段码表 `_SEGMENTS`。

### 示例

```python
from machine import Pin
import TM1637

tm = TM1637.TM1637(clk=Pin(4, Pin.OUT), dio=Pin(5, Pin.OUT))
tm.shownum(1234)
tm.showDP(3, True)
```

> 示例中 `dio`/`clk` 顺序：`TM1637(dio=dio, clk=clk)`，与文档一致。

---

## 3. TM1650/HBS650 四位数码管 (`FourDigitDisplay`)

- **驱动文件**：[FourDigitDisplay.py](../LED/TM1650/FourDigitDisplay.py)｜示例：[test.py](../LED/TM1650/test.py)｜文档：[README.md](../LED/TM1650/README.md)
- **器件**：TM1650/HBS650 四位 7 段数码管，**I2C** 接口。
- **I2C 地址**：命令 `0x24`，显示数据 `0x34`–`0x37`（常量 `COMMAND_I2C_ADDRESS=0x24`、`DISPLAY_I2C_ADDRESS=0x34`）。
- **核心类**：`FourDigitDisplay(i2c)`

### 关键方法

| 方法 | 说明 |
| --- | --- |
| `intensity(dat=-1)` | 设/取亮度；`dat` 0–8，传参越界则返回当前值；`dat=0` 关闭 |
| `cmd(c)` / `dat(bit, d)` | 写命令寄存器 / 写某位显示寄存器（内部） |
| `on()` / `off()` | 显示开/关 |
| `clear()` | 清空显示与缓冲 |
| `showbit(num, bit=0)` | 指定位显示 0–15 段码 |
| `shownum(num)` | 显示十进制整数（负数显示 `-`） |
| `showhex(num)` | 显示十六进制 |
| `showDP(bit=1, show=True)` | 显示/隐藏小数点 |

> 注意：`FourDigitDisplay.showDP()` 使用 `self.dbuf[bit]` 直接索引，未对 `bit` 取模（`bit` 需在 0–3 内）。

### 示例

```python
import machine, time
import FourDigitDisplay

fdd = FourDigitDisplay.FourDigitDisplay(machine.I2C(1))
fdd.shownum(1234)
```
