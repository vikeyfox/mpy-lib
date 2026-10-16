# 整体架构与设计

本页说明 `micropython-libs` 的整体架构、驱动通用设计约定、**依赖关系**与命名规范，是二次开发与维护的入口。

---

## 1. 架构分层模型

整个仓库采用极简的四层模型，所有驱动都遵循同一模式：

```text
┌───────────────────────────────────────────────┐
│  应用/示例层  test.py · *_demo.py · *_irq_demo.py │  直接运行，演示 API 用法
├───────────────────────────────────────────────┤
│  驱动层       <驱动名>.py 中的 Python 类          │  面向用户的 API，封装器件语义
│               （BMP280 / TM1637 / DS1307 ...）   │
├───────────────────────────────────────────────┤
│  平台抽象层   machine.I2C / Pin / Timer / UART   │  MicroPython 内置，屏蔽 MCU 差异
├───────────────────────────────────────────────┤
│  硬件层       传感器 / 显示 / RTC / EEPROM ...    │  通过 I2C、SPI-like、单总线、GPIO 交互
└───────────────────────────────────────────────┘
```

- **驱动层不依赖平台抽象层之外的任何第三方库**，只 import `machine`（`I2C`/`Pin`/`Timer`/`UART`），个别 import `neopixel`、`sys`、`time`、`micropython.const`。
- 因此驱动可移植性强：更换 MCU 平台时，通常只需修改 `I2C(...)`/`Pin(...)` 的构造参数。

---

## 2. 通信接口分类

| 接口类型 | 涉及驱动 | 说明 |
| --- | --- | --- |
| **I2C** | LCD1602、OLED12864、FourDigitDisplay(TM1650)、全部 `sensor/*`、AT24XX、DS1307、DS3231 | 主流方式，直接使用 `machine.I2C` 的 `readfrom`/`writeto`（或 `readfrom_mem`/`writeto_mem`） |
| **两线软件时序** | TM1637 | 自行用 `Pin` 位翻转模拟 CLK/DIO 时序（`_start`/`_stop`/`_write_byte`） |
| **三线同步串行 + CS** | HT1621B（GDC03849）、DS1302 | 用 `Pin` 位操作逐位收发 |
| **GPIO 中断 + UART** | irqUART | 用 RXD 引脚下降沿中断 + 定时器，替代不被原生支持 UART RXD 中断的平台 |
| **GPIO 中断 + 定时器** | KEYBOARD | 定时器周期扫描按键电平，识别单击/连击/长按 |
| **单总线（NeoPixel）** | neo16x16、neo16x16_img | 基于 MicroPython 内置 `neopixel` 模块 |

---

## 3. 驱动的通用设计约定

多数 I2C 传感器驱动共享同一套内部惯例，理解它们即可快速读懂任意一个驱动：

### 3.1 寄存器读写原语

```python
def setreg(self, reg, dat):        # 写单个寄存器
    self.tb[0] = dat
    self.i2c.writeto_mem(self.addr, reg, self.tb)

def getreg(self, reg):             # 读单个寄存器（返回 int）
    self.i2c.readfrom_mem_into(self.addr, reg, self.rb)
    return self.rb[0]

def get2reg(self, reg):            # 读连续两寄存器组成小端 16 位
    return self.getreg(reg) + self.getreg(reg + 1) * 256
```

- Bosch 系列（BMP180/280、BME280）因历史原因使用 `writeto`+`readfrom`（先写寄存器地址再读）而非 `*_mem` 系列，语义等价。
- `int16(d)` 工具方法用于把无符号 16 位转成有符号（`d if d < 0x8000 else d - 0x10000`）。
- `short(d)` 是 Bosch 驱动里对 `int16` 的同义命名。
- `r_w_reg(reg, dat, mask)` 为"读-改-写"辅助方法（ST 驱动中常见），用于按位掩码更新寄存器字段。

### 3.2 单次测量（One-shot）模式

许多 ST 驱动支持 `oneshot_mode(on)` + `ONE_SHOT(b)`：开启后每次读取前触发一次转换并轮询状态位，兼顾低功耗与读取一致性。`oneshot=False`（默认）时走连续转换模式。

### 3.3 中断中安全读取（MemoryError 回退）

ST 驱动常把主读取逻辑放在 `try/except MemoryError` 中，异常时回退到 `*_irq()` 方法。这是因为在**定时器中断上下文**中无法分配内存，程序必须改用无分配（复用 `bytearray`/乘法除法而非浮点包装）的路径。示例见 [hts221.py](../sensor/HTS221/hts221.py) 与 [LPS22.py](../sensor/LPS22/LPS22.py)。

### 3.4 BCD 转换与 RTC

RTC 驱动（DS1302/DS1307/DS3231）内部统一提供：

```python
def DecToHex(self, dat):  return (dat // 10) * 16 + (dat % 10)   # 十进制 -> BCD
def HexToDec(self, dat):  return (dat // 16) * 10 + (dat % 16)   # BCD -> 十进制
```

有需要则统一用 `DateTime([Year, Month, Day, Weekday, Hour, Minute, Second])` 读写整组时间。

### 3.5 显存 / 缓冲

- **OLED12864**：维护 1025 字节 `screen` 缓冲（首字节为 I2C 控制字节 `0x40`），支持 `pixel`/画线/滚动/多字号字符渲染，`_DRAW` 控制是否立即刷屏。
- **TM1637 / TM1650**：维护 4 字节 `dbuf` 段码缓冲与 `_SEGMENTS` 段码表，实现 `shownum`/`showhex`/`showDP`。

---

## 4. 依赖关系

### 4.1 外部依赖（运行环境）

所有驱动**仅依赖 MicroPython 固件内置模块**，无 pip 依赖、无第三方包：

| 内置模块 | 被哪些驱动使用 |
| --- | --- |
| `machine.I2C` | 全部 I2C 驱动 |
| `machine.Pin` | TM1637、HT1621B、DS1302、irqUART、KEYBOARD、neo* |
| `machine.Timer` | irqUART、KEYBOARD、`*_irq_demo.py` |
| `machine.UART` | irqUART |
| `time`（`sleep_ms`/`sleep_us`/`sleep`） | 几乎所有 I2C/时序驱动 |
| `micropython.const` | HT1621B、部分 ST 驱动 |
| `sys` | irqUART（区分 `pyboard` 与其它平台） |
| `neopixel`（固件自带） | neo16x16、neo16x16_img |

### 4.2 仓库内部依赖（模块间）

绝大多数驱动是**彼此独立**的，可单独取用。仅存在少量内部耦合：

```text
lcd/3Wire-HT1621B-GDC03849/
    gdc03849.py  ──依赖──▶  ht1621x.py          # GDC03849 通过 HT1621B 对象写段码

LED/OLED_I2C_ASC/
    oled.py  ──依赖──▶  Font_6x8.py / Font_8x16.py
                        Font_12x24.py / Font_16x32.py   # 字库数据模块

sensor/* 的 *_irq_demo.py
    ──依赖──▶  对应 sensor python 驱动 + machine.Timer
```

字库文件（`Font_*.py`）是**纯数据模块**，以 `bytes` 常量导出字形点阵（`Font_6x8` 覆盖 `' '`–`'~'`，即 0x20–0x7E），被 `oled.py` 直接 `from ... import`。

### 4.3 依赖关系总图

```text
应用示例 (test.py / *_demo.py)
        │  import
        ▼
驱动类 ──────────────┬───────────────┬───────────────┐
        │            │               │               │
        ▼            ▼               ▼               ▼
  machine.I2C   machine.Pin    machine.Timer    neopixel(内置)
        │            │               │               │
        ▼            ▼               ▼               ▼
       └─────────── 物理外设（传感器/显示/RTC/灯板/按键）───────────┘
```

---

## 5. 命名与代码规范

| 维度 | 约定 |
| --- | --- |
| 目录 | 直接以**器件型号**命名（`bme280`、`LIS2DW12`、`DS3231`、`neo_16x16`） |
| 驱动文件名 | 多数与型号同名；LCD1602 为 `mp_i2c_lcd1602.py`，OLED 为 `oled.py`，HT1621x 为 `ht1621x.py` |
| 类名 | 与器件/功能同名（`BMP280`、`TM1637`、`LCD1602`、`HT1621B`、`KEYBOARD`） |
| 寄存器常量 | 全大写 + 前缀（`BMP280_I2C_ADDR`、`LIS2DW12_CTRL1`、`DS3231_REG_SEC`、`CMD_LCDON`） |
| 全局配置 | 常量用 `const(...)`（MicroPython 编译期常量，省 RAM） |
| 单位后缀方法 | `x()/y()/z()` 返回换算后物理量，`x_raw()/y_raw()/z_raw()` 返回原始值 |
| 读写方法 | `get()` 返回整组测量值（列表/元组），`getTemp()/getPress()/getHumi()` 返回单项 |
| 电源控制 | `power(on)` / `poweron()` / `poweroff()` |
| 版本号 | 部分驱动保留 `self.version = 'x.y'` 属性 |

---

## 6. 几个值得注意的实现细节

- **OLED `Font` 与 `font` 两个方法**：小写 [`font()`](../LED/OLED_I2C_ASC/oled.py#L138-L139) 仅设置 `self.FONT` 属性；大写 [`Font()`](../LED/OLED_I2C_ASC/oled.py#L249-L261) 才会把 `self.char`/`self.text` 绑定到对应字号的实现。日常使用调用大写 `Font()`。
- **OLED `print`** 是自定义方法（非 Python 内建），自动换行并滚动。
- **LSM6DSO 存在方法覆盖问题**：类中 `get_g` 与 `get` 被定义了两次，且第二次的 `get()` 引用了未定义的 `get_g_raw()`（见 [LSM6DSO.py](../sensor/LSM6DSO/LSM6DSO.py#L128-L143)）。实际生效的是后定义的版本，`get()` 会在运行时报 `NameError`。使用应以 `get_a()`/`get_g()`（第一次定义）或单项 `ax()/gx()` 为准。
- **LIS2MDL 源码包含 C 风格注释 `// unit uT`**（见 [LIS2MDL.py](../sensor/LIS2MDL/LIS2MDL.py#L81-L93)），这些是非法 Python 语法，若整文件运行会报错——使用时应删除这些注释行或仅使用其余合法部分。
- **irqUART 平台分支**：`self._mode = Timer.ONE_SHOT if sys.platform == 'pyboard' else Timer.PERIODIC`，用于适配不同固件的定时器语义。
- **HT1621B 通过二进制字符串逐位移位**发送命令/地址/数据（`bin(...)[3:]`），并用 `_wrData` 逐位翻转 WR/DA 引脚。
