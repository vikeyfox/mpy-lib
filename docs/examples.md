# 示例与样例索引

本页列出仓库内所有可运行的示例文件，说明其演示内容与依赖的硬件/平台。示例文件命名规则：

- `test.py` / `demo.py`：功能演示（多为循环读取/显示）。
- `*_irq_demo.py`：在**定时器中断**中读取的演示（使用 `from pyb import Timer`，面向 PyBoard/STM32）。
- `*_demo.py`：普通功能演示。

> 运行方式见 [运行与部署](runtime.md)。示例中的 I2C/Pin 参数需按你自己的开发板调整。

---

## LED

| 文件 | 驱动 / 类 | 演示内容 | 平台/硬件假设 |
| --- | --- | --- | --- |
| [demo.py](../LED/OLED_I2C_ASC/demo.py) | `oled.py` / `OLED12864_I2C` | 依次用默认 6x8、`Font_8x16`、`Font_12x24` 显示 `'0123456789'` | 软件 I2C：`scl=Pin(27)`, `sda=Pin(13)` |
| [test.py](../LED/TM1637/test.py) | `TM1637.py` / `TM1637` | 每秒 `shownum(n)` 递增计数 | `dio=Pin(5)`, `clk=Pin(4)` |
| [test.py](../LED/TM1650/test.py) | `FourDigitDisplay.py` / `FourDigitDisplay` | 每秒 `shownum(n)` 递增计数 | `machine.I2C(1)` |

## LCD

| 文件 | 驱动 / 类 | 演示内容 | 平台/硬件假设 |
| --- | --- | --- | --- |
| [test.py](../lcd/I2C_LCD1602/test.py) | `mp_i2c_lcd1602.py` / `LCD1602` | `puts("I2C LCD1602")` 并在第二行递增显示计数 | 硬件 `I2C(1, sda=Pin(9), scl=Pin(10))` |
| [README 综合示例](../lcd/3Wire-HT1621B-GDC03849/README_CN.md) | `HT1621B` + `GDC03849` | 温度区 33.05、湿度区 98.34% | PyBoard：`CS/RD/WR/DA = A0/A1/B0/B1` |

> `3Wire-HT1621B-GDC03849` 目录**未提供独立 test.py**，可运行示例内嵌在其 README 中。

## Sensor

| 文件 | 驱动 / 类 | 演示内容 | 说明 |
| --- | --- | --- | --- |
| [test.py](../sensor/bmp180/test.py) | `BMP180` | 每 500ms `get()` | Bosch 气压 |
| [test.py](../sensor/bmp280/test.py) | `BMP280` | 每 500ms `get()` | Bosch 气压 |
| [test.py](../sensor/bme280/test.py) | `BME280` | 每 500ms `print(get())` | Bosch 温湿度气压 |
| [ALS_demo.py](../sensor/APDS9930/ALS_demo.py) | `APDS9930` | 每 500ms `getALS()` | 环境光 |
| [Proximity_demo.py](../sensor/APDS9930/Proximity_demo.py) | `APDS9930` | `Proximity_Enable()` 后循环 `getProximity()` | 接近（需 VL 接 3.3V） |
| [hts221_demo.py](../sensor/HTS221/hts221_demo.py) | `HTS221` | `get()` | — |
| [hts221_irq_demo.py](../sensor/HTS221/hts221_irq_demo.py) | `HTS221` | 定时器 1Hz 中 `get_irq()` | `pyb.Timer` |
| [LPS22_demo.py](../sensor/LPS22/LPS22_demo.py) | `LPS22` | `get()` | — |
| [LPS22_irq_demo.py](../sensor/LPS22/LPS22_irq_demo.py) | `LPS22` | 定时器 1Hz 中 `get_irq()` | `pyb.Timer` |
| [STTS751_demo.py](../sensor/STTS751/STTS751_demo.py) | `STTS751` | `temperature()` | — |
| [STTS751_irq_demo.py](../sensor/STTS751/STTS751_irq_demo.py) | `STTS751` | 定时器 1Hz 中 `temperature_irq()` | `pyb.Timer` |
| [LIS2DW12_demo.py](../sensor/LIS2DW12/LIS2DW12_demo.py) | `LIS2DW12` | `x()`、`get()` | — |
| [LIS2DW12_irq_demo.py](../sensor/LIS2DW12/LIS2DW12_irq_demo.py) | `LIS2DW12` | 定时器 1Hz 中 `get()` | `pyb.Timer` |
| [LIS2MDL_demo.py](../sensor/LIS2MDL/LIS2MDL_demo.py) | `LIS2MDL` | `x()`、`get()` | 见源码注释缺陷 |
| [LIS2MDL_irq_demo.py](../sensor/LIS2MDL/LIS2MDL_irq_demo.py) | `LIS2MDL` | 定时器 1Hz 中 `get()` | `pyb.Timer` |
| [LSM6DSO_demo.py](../sensor/LSM6DSO/LSM6DSO_demo.py) | `LSM6DSO` | `ax()`、`get_a()`、`get()`（注意 `get()` 缺陷） | — |
| [LSM6DSO_irq_demo.py](../sensor/LSM6DSO/LSM6DSO_irq_demo.py) | `LSM6DSO` | 定时器 1Hz 中 `get()`、`temperature()` | `pyb.Timer` |

> 所有 ST 传感器 demo 均以 `I2C(1)` 构造；irq demo 统一模式为：构造传感器 → 定义 `tim_irq(t)` → `Timer(1, freq=1).callback(tim_irq)`。

## Misc

| 文件 | 驱动 / 类 | 演示内容 | 平台/硬件假设 |
| --- | --- | --- | --- |
| [test.py](../misc/AT24XX/test.py) | `AT24XX` | 写/读 byte、word、buf | `I2C(sda=Pin(5), scl=Pin(4))` |
| [test.py](../misc/DS1302/test.py) | `DS1302` | 读写 DateTime/Hour/Second | `clk=Pin(4), dio=Pin(5), cs=Pin(2)` |
| [test.py](../misc/DS1307/test.py) | `DS1307` | 读写 DateTime/Hour | `I2C(sda=Pin(5), scl=Pin(4))` |
| [test.py](../misc/DS3231/test.py) | `DS3231` | 读写 Time/DateTime、设置/清除闹钟 | `I2C(sda=Pin(5), scl=Pin(4))` |
| [irqUART_pyb_demo.py](../misc/irqUART/irqUART_pyb_demo.py) | `irqUART` | RXD 中断 + 帧中断接收 | PyBoard：`UART(1)`, `Pin('B7')` |
| [irqUART_esp32_demo.py](../misc/irqUART/irqUART_esp32_demo.py) | `irqUART` | RXD 中断 + 帧中断接收 | ESP32：`UART(2, 115200, tx=23, rx=22)`, `Pin(22)` |

## Neopixel

| 文件 | 驱动 / 类 | 演示内容 | 说明 |
| --- | --- | --- | --- |
| [test.py](../neopixel/neo_16x16/test.py) | `neo16x16` | 循环滚动显示单色位图（70 帧动画） | `Pin(2)`，**需外部供电** |
| [test.py](../neopixel/neo_16x16_img/test.py) | `neo16x16_img` | 循环滚动显示彩色位图 | `Pin(2)`，**需外部供电** |

## Keyboard

无独立示例文件，用法示例内嵌在 [README.md](../keyboard/mechanical-button/single-button/README.md)（见 [keyboard.md](keyboard.md#用法示例)）。

---

## 典型运行流程

```python
# 1. 把驱动 + 示例拷到板子
# 2. 在 REPL 中执行
import test              # 运行某目录的 test.py（同名时重命名或以目录区分）

# 或直接逐行执行示例中的语句，例如：
from machine import I2C
from bmp280 import BMP280
print(BMP280(I2C(1)).get())
```
