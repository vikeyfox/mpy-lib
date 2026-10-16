# LCD 模块

目录：[lcd/](../lcd)｜覆盖 **I2C 字符屏 LCD1602** 与 **三线段码屏 HT1621B + GDC03849**。

---

## 1. I2C LCD1602 (`I2C_LCD1602`)

- **驱动文件**：[mp_i2c_lcd1602.py](../lcd/I2C_LCD1602/mp_i2c_lcd1602.py)｜示例：[test.py](../lcd/I2C_LCD1602/test.py)｜文档：[README.md](../lcd/I2C_LCD1602/README.md)
- **器件**：HD44780 兼容 16×2 字符 LCD，经 PCF8574/PCF8574A 的 I2C 转并口扩展板驱动。
- **I2C 地址**：PCF8574 = `0x27`，PCF8574A = `0x3F`。驱动内常量 `LCD_I2C_ADDR = 63`（0x3F），并在 `autoaddr()` 中探测 `0x20` 与 `0x3F`。
- **接口信号映射**：`RS→P0`、`RW→P1`、`E→P2`、`BackLight→P3`、`Dat→P4-P7`。
- **核心类**：`LCD1602(i2c, addr=0)`

### 关键方法与属性

| 方法 | 说明 |
| --- | --- |
| `LCD1602(i2c, addr=0)` | 构造。`addr=0` 时自动探测地址；执行初始化命令序列 `0x33/0x30/0x20/0x28/0x0C/0x06/0x01` |
| `setReg(dat)` | 向 I2C 写 1 字节 |
| `send(dat)` / `setcmd(cmd)` / `setdat(dat)` | 4 位半字节方式发送命令/数据（含 E 脉冲） |
| `autoaddr()` | 在 `0x20`/`0x3F` 中探测在线地址，失败抛 `Exception` |
| `clear()` | 清屏 |
| `backlight(on)` | 背光开（`on=1`）/关（`on=0`） |
| `on()` / `off()` | 显示开/关（光标关闭） |
| `shl()` / `shr()` | 显示整体左移/右移 |
| `char(ch, x=-1, y=0)` | 在 `(x,y)` 写一个字符；`x>=0` 时先定位 |
| `puts(s, x=0, y=0)` | 在 `(x,y)` 输出字符串/对象（自动 `str()`） |
| `newline()` | 手动换行（第 0 行→第 1 行；第 1 行→滚动） |
| `print(s)` | 流式打印，`\n` 换行，行尾自动换行滚动 |

- 坐标范围：`x` 0–15，`y` 0–1。
- 内部维护 `px, py`（光标位置）与 `pb`（用于滚动的上一行缓冲）。

### 示例

```python
from machine import I2C, Pin
from mp_i2c_lcd1602 import LCD1602

i2c = I2C(1, sda=Pin(9), scl=Pin(10))
LCD = LCD1602(i2c)
LCD.puts("I2C LCD1602")
LCD.print("hello\nworld")     # 流式打印，支持换行与滚动
```

---

## 2. 3-Wire HT1621B + GDC03849 (`3Wire-HT1621B-GDC03849`)

- **驱动文件**：[ht1621x.py](../lcd/3Wire-HT1621B-GDC03849/ht1621x.py)、[gdc03849.py](../lcd/3Wire-HT1621B-GDC03849/gdc03849.py)
- **文档**：[README_CN.md](../lcd/3Wire-HT1621B-GDC03849/README_CN.md) / [README.md](../lcd/3Wire-HT1621B-GDC03849/README.md)
- **数据手册**：[DataSheet/](../lcd/3Wire-HT1621B-GDC03849/DataSheet)
- **器件**：HT1621B（合泰，128 点内存映像 LCD 驱动控制器，3+CS 线通信）；GDC03849（大连佳显，仅显示 3 位整数 + 2 位小数的温度/湿度段码屏）。
- **作者/许可**：Robin Chen，MIT（内嵌于文件头）。

### 2.1 类 `HT1621B` — 底层控制器

**构造**：`HT1621B(_cs, _rd, _wr, _htdata)`（CS/RD/WR/DATA 四个 `Pin`，构造后自动 `init()`）

| 方法 | 说明 |
| --- | --- |
| `init(_timer=CMD_TIMER_DIS, _wdt=CMD_WDT_DIS, _scs=CMD_RC256K, _bias=CMD_B3C4, _tone=CMD_TONE4K, _irq=CMD_IRQ_DIS, _twc=CMD_F128, _mod=CMD_NORMAL)` | 芯片功能/参数初始化；内部发送 `CMD_SYSDIS → _wdt → CMD_SYSEN → 各命令 → ALLCLEAR(0,32)` |
| `_wrData(_da)` | 逐位写一串 0/1（内部） |
| `HT1621xWrCmd(_cmd)` | 发送单条命令（9 位） |
| `HT1621xWrOneData(_addr, _htdata)` | 向指定地址写单字节数据 |
| `HT1621xWrAllData(_addr, _htdata)` | 从起始地址连续写多个数据（列表） |
| `ALLSHOW(_addr, _nbit)` | 从 `_addr` 起写 `_nbit` 个 `0x0F`（全 1） |
| `ALLCLEAR(_addr, _nbit)` | 从 `_addr` 起写 `_nbit` 个 `0x00`（全 0） |
| `LCDON()` / `LCDOFF()` | 打开/关闭 LCD 偏压发生器（显示电源） |
| `HTBEEP(_t)` | 蜂鸣器响 `_t` 毫秒 |

**常用常量**（节选）：标志字 `FLAG_CMD/FLAG_READ/FLAG_WRITE/FLAG_MODIFY`；LCD 控制 `CMD_LCDON(0x006)/CMD_LCDOFF(0x004)`；系统 `CMD_SYSEN/CMD_SYSDIS`；偏压/COM `CMD_B2C2..B3C4`（如 4COM 1/3 bias = `CMD_B3C4`）；时钟 `CMD_RC256K/CMD_EXT256K/CMD_XTAL32K`；时基 `CMD_TIMER_EN/DIS/CLR_TIMER`；WDT `CMD_WDT_DIS/EN/CLR_WDT`；声音 `CMD_TONE2K/4K/TONEON/TONEOFF`；分频 `CMD_F1..CMD_F128`；IRQ `CMD_IRQ_DIS/EN`；模式 `CMD_TEST/CMD_NORMAL`。完整表见 [README_CN.md](../lcd/3Wire-HT1621B-GDC03849/README_CN.md)。

### 2.2 类 `GDC03849` — 段码屏应用层

**构造**：`GDC03849(_ht1621x)`（传入 `HT1621B` 对象；构造时 `init()` → `LCDON()` → `LCDALLSHOW()` → `HTBEEP(1)` → `LCDALLCLEAR()`）

| 方法 | 说明 |
| --- | --- |
| `viewTemp(_gdcdata)` | 温度区显示浮点温度（乘 100 取 5 位，写地址 `0x0A`） |
| `viewRH(_gdcdata)` | 湿度区显示浮点湿度（写地址 `0x00`） |
| `LCDALLSHOW()` | 点亮整屏所有字段 |
| `LCDALLCLEAR()` | 清除整屏所有字段 |
| `TEMPCLEAR()` | 清除温度区（地址 `0x0A`，10 段） |
| `RHCLEAR()` | 清除湿度区（地址 `0x00`，10 段） |

**常量**：`NUMCODE_RH_HEX`、`NUMCODE_TEMP_HEX`（`0–9` 及小数点的段码编码元组）。

### 2.3 示例

```python
from ht1621x import HT1621B
from gdc03849 import GDC03849
from machine import Pin

CS, RD, WR, DA = Pin("A0"), Pin("A1"), Pin("B0"), Pin("B1")
ht  = HT1621B(CS, RD, WR, DA)
gdc = GDC03849(ht)

gdc.viewTemp(33.05)   # 显示温度 33.05
gdc.viewRH(98.34)     # 显示湿度 98.34%
```
