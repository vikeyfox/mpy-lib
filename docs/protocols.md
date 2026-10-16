# 通信协议与时序

本仓库的驱动本质上都是对若干硬件协议的最小封装。本页说明各协议在本项目中的**具体实现方式**（位序、帧结构、延时），便于移植与排错。所有描述均来自源码。

---

## 1. 通用约定

- **寄存器读写原语**：所有 I2C 驱动都提供 `setreg(reg,dat)` / `getreg(reg)` / `get2reg(reg)` 三件套；`get2reg` 多为小端（`低字节 + 高字节*256`），仅 BMP180 为大端。
- **`get2reg` 会触发两次独立读**，因此要求器件地址自增（多数 ST/Bosch 传感器默认开启）。
- **预分配缓冲**：驱动在 `__init__` 中创建 `self.tb`/`self.rb`（`bytearray(1)`），避免在运行时分配内存（影响中断安全）。

---

## 2. HT1621B 三线位操作

源码：[ht1621x.py](../lcd/3Wire-HT1621B-GDC03849/ht1621x.py)

引脚：`CS`、`WR`（写时钟）、`RD`、`DA`（数据）。全部由 `Pin` 软件模拟。

**位发送**（`_wrData`）：

```
WR 拉低 → DA 输出该位 → 延时 4µs → WR 拉高（上升沿锁存）→ 延时 4µs
```

逐位发送，**MSB first**（对 `bin()` 字符串按下标正序迭代）。

**命令帧**（`HT1621xWrCmd`）：

```
CS 拉低 → 3bit 标志 "100"(FLAG_CMD) → 9bit 命令(MSB first) → CS 拉高
```

命令值通过 `_cmd ^ (1<<9)` 转成 9 位二进制。

**写数据帧**（`HT1621xWrOneData` / `HT1621xWrAllData`）：

```
CS 拉低 → 3bit 标志 "101"(FLAG_WRITE) → 6bit 地址(MSB first) → N×4bit 数据 → CS 拉高
```

- `HT1621xWrOneData`：1 个地址 1 个 nibble。
- `HT1621xWrAllData`：起始地址 + 连续 nibble 列表（`ALLSHOW`/`ALLCLEAR` 用 0x0F/0x00 填充）。

**初始化时序**（`init`）：`SYSDIS → WDT → SYSEN → 依序写 8 条命令 → ALLCLEAR(0,32)`，每条命令间有 `sleep(1)` / `sleep_us(4)`。

---

## 3. DS1302 三线串行

源码：[DS1302.py](../misc/DS1302/DS1302.py)

引脚：`clk`、`dio`（双向）、`cs`。

- **位序 LSB first**：`write_byte` 从 bit0 到 bit7 依次输出，每位产生一次 `clk(1)→clk(0)` 时钟。
- **读操作**：`read_byte` 先把 `dio` 切换为输入，再逐位读入（同样 LSB first）。
- **命令字节编码**：bit0 = R/W（读=1），bit1–6 = 寄存器地址，bit7 = 1。
  - 因此驱动的常量给的是**写地址**（bit0=0，如秒 `0x80`），读时统一取 **`写地址 + 1`**（如 `getReg(DS1302_REG_SECOND + 1)`）。
- **写保护时序**（`wr`）：`写 WP=0 → 写目标寄存器 → 写 WP=0x80`。

---

## 4. TM1637 两线（类 I2C）

源码：[TM1637.py](../LED/TM1637/TM1637.py)

引脚：`clk`、`dio`，逐位软件模拟，位间固定 `TM1637_DELAY=10µs`。

**起始/停止条件**：

```
_start: dio=0 → clk=0
_stop : dio=0 → clk=1 → dio=1
```

**写字节**（`_write_byte`）：8 位 **LSB first**，每位 `dio` 置值 → `clk↑` → `clk↓`；第 9 个时钟周期为 ACK 占位（不做校验）。

**三命令流程**：
1. `_write_data_cmd`：发 `0x40`（自动地址递增）。
2. 写显存：`start → 0xC0|地址 → 数据 → stop`。
3. `_write_dsp_ctrl`：发 `0x80 | 显示开 | 亮度`。

---

## 5. APDS9930 的特殊 I2C 访问

源码：[APDS9930.py](../sensor/APDS9930/APDS9930.py)

APDS-9930 **不支持** `writeto_mem`/`readfrom_mem` 的常规子地址协议，而是把寄存器地址编码进**首字节的命令寄存器**：

```
首字节 = reg | 0xA0     # 高 3 位固定 101（寄存器访问），低 5 位为寄存器地址

写：i2c.writeto(0x39, [reg|0xA0, dat])
读：i2c.writeto(0x39, [reg|0xA0])  →  i2c.readfrom(0x39, n)
```

连续两字节读（`get2Reg`）先写命令字节再 `readfrom(2)`，得到 `t[0] + t[1]*256`。因此该驱动**不遵循**其他驱动的 `setreg/getreg` 命名，而用 `setReg/getReg/get2Reg`（大写 R），且读写都走 `writeto`/`readfrom` 而非 `writeto_mem`。

---

## 6. OLED（SSD1306）控制字节

源码：[oled.py](../LED/OLED_I2C_ASC/oled.py)

I2C 传输以控制字节区分命令/数据：

```
命令：writeto(ADDR, 0x00 + [命令字节...])
数据：writeto(ADDR, 0x40 + 数据字节...)
```

显存缓冲区 `screen = bytearray(1025)`，`screen[0]=0x40` 即数据前缀。`pixel()` 在 `_DRAW=1` 时即时写入（`set_pos` 设置页地址 `0xB0|page` 与列地址高低位）。`draw()` 一次性发送整块 1024 字节。

### LCD1602（PCF8574）
源码：[mp_i2c_lcd1602.py](../lcd/I2C_LCD1602/mp_i2c_lcd1602.py)

PCF8574 的 8 位并行口拆成控制线：`BK=0x08`（背光）、`RS=0x00`（0 命令/1 数据）、`E=0x04`（使能脉冲）。时序为经典的 HD44780 4 位模式：置 `RS` 与数据 → `E` 高 → `E` 低锁存。

---

## 7. Neopixel 单线

源码：[neo16x16.py](../neopixel/neo_16x16/neo16x16.py) / [neo16x16_img.py](../neopixel/neo_16x16_img/neo16x16_img.py)

不自行实现位时序，直接使用固件内置 `neopixel` 模块（ESP8266/ESP32）。驱动负责**颜色编排**：`set(n,color)` 定位、`show(dat,offset)` 批量刷新，`clear()` 清屏。

---

## 8. irqUART 中断接收时序

源码：[irqUART.py](../misc/irqUART/irqUART.py)

利用 **RXD 引脚下降沿中断 + 定时器** 模拟"字符中断/帧中断"：

```
RXD 下降沿(IRQ_FALLING) → _RXPIN_IRQ
   └ 首次触发：启动 Timer，周期 = CHR_TMO(默认3ms)，回调 _TMRX_IRQ

_TMRX_IRQ（字符级）:
   若设置了 frame_irq 且 FRAME_TMO>0：
        重装 Timer 为 ONE_SHOT，周期 = FRAME_TMO(默认100ms)
        调用 rx_irq(0)          # 字符到达
   否则/后续：
        调用 frame_irq(0)       # 帧结束
```

- 定时器模式按平台选择：`sys.platform == 'pyboard'` 用 `Timer.ONE_SHOT`，否则 `Timer.PERIODIC`。
- `CHR_TMO` 与波特率、`rxbuf` 大小相关；`FRAME_TMO` 与帧间空闲时间相关，需按实际协议调整。

---

## 9. 单次测量握手（one-shot）

ST 系列传感器普遍采用同一套"软件触发 + 轮询就绪位"协议：

```
init:        oneshot_mode(True)        # 关闭连续转换
每次测量:    [
             先读一次输出寄存器清标志（LIS2MDL）
             置触发位（CTRL2/CTRL3/ONESHOT...）
             while 未就绪: 轮询 STATUS 就绪位
             读输出寄存器并换算
           ]
```

`ONE_SHOT(b)` 中的 `b`（1=气压/加速度、2=温度/湿度）即状态位掩码。

---

## 10. 中断安全：整数算法与 MemoryError 回退

ST 系列驱动中 `*_irq()` 版本与普通版本算法相同，但有三点差异：

1. **全整数运算**：如 `K1` 用 `//` 与 `>>`，避免浮点在中断中的开销与临时对象。
2. **复用预分配缓冲**：`self.irq_v` 列表先建好，`get_irq()` 只赋值不新建。
3. **无异常**：不在中断路径里做会抛异常的内存分配。

普通方法（`temperature()` 等）用 `try/except MemoryError` 兜底，在内存紧张或位于中断上下文时自动切换到 `*_irq()`：

```python
def temperature(self):
    try:
        return <浮点计算>
    except MemoryError:
        return self.temperature_irq()
```

---

## 11. 计时与 BCD 转换

RTC 驱动（DS1302/07/3231）内部以 BCD 存储时间，读写时统一经过：

```
DecToHex(dat) = (dat//10)*16 + (dat%10)    # 十进制 → BCD
HexToDec(dat) = (dat//16)*10 + (dat%16)    # BCD → 十进制
```

年份两位存储，读出时 `+2000`，写入时 `%100`。
