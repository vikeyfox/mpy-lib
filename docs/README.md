# micropython-libs Code Wiki

> MicroPython 硬件驱动、示例与库集合（All kinds of micropython drives, examples, libraries）
> 来源：microbit / micropython 中国社区 · [www.micropython.org.cn](http://www.micropython.org.cn)

本 Wiki 面向前两类读者：

- **使用者**：想快速了解某个驱动模块怎么接线、怎么调用，请直接看对应模块章节与 `README.md` / `test.py`。
- **维护者 / 二次开发者**：想理解整体架构、驱动编写约定、寄存器抽象层与依赖关系，请阅读 [架构与设计](architecture.md)。

---

## 1. 项目概览

`micropython-libs` 是一个面向 MicroPython 平台的**外设驱动库集合**，按外设类型分类组织。每个驱动通常由三个部分构成：

| 文件 | 作用 |
| --- | --- |
| `<驱动名>.py` | 驱动实现，核心类定义 |
| `README.md` | 中文/英文使用文档，含 API 表与接线说明 |
| `test.py` / `*_demo.py` / `*_irq_demo.py` | 可直接烧录运行的示例程序 |

项目本身**不是一个可构建的软件工程**：它是"复制到开发板文件系统即可 `import` 使用"的脚本集合（详见 [运行与部署](runtime.md)）。没有 `setup.py`、`requirements.txt` 或自动化构建流程。

- **许可证**：MIT（见仓库根 [LICENSE](../LICENSE)；`ht1621x.py`、`gdc03849.py`、`keyboard.py` 内含由 Robin Chen 提供的 MIT 声明）。
- **主要作者**：shaoziyang（肖子扬）；Robin Chen（HT1621x、GDC03849、KEYBOARD）。
- **支持平台**：任何支持 MicroPython `machine` 模块的 MCU（PyBoard/STM32、ESP8266、ESP32、部分 micro:bit 场景），部分示例明确区分 `pyboard` 与 `esp32`。

---

## 2. 仓库目录结构

```text
micropython-libs/
├── README.md                     # 顶层索引
├── LICENSE                       # MIT
├── .gitattributes                # 文本 LF 归一化
├── lcd/                          # 字符/段码液晶驱动
│   ├── I2C_LCD1602/              # PCF8574 + LCD1602（I2C 字符屏）
│   └── 3Wire-HT1621B-GDC03849/   # HT1621B + GDC03849（三线段码屏）
├── LED/                          # 显示/数码管类 LED 驱动
│   ├── OLED_I2C_ASC/             # SSD1306 I2C OLED ASCII 显示
│   ├── TM1637/                   # 4 位 7 段数码管（两线）
│   └── TM1650/                   # 4 位 7 段数码管（I2C）
├── sensor/                       # 传感器驱动
│   ├── bmp180/  bmp280/  bme280/ # Bosch 气压/温湿度
│   ├── APDS9930/                 # 环境光 + 接近
│   ├── HTS221/ LPS22/ STTS751/   # ST 温湿度/气压/温度
│   └── LIS2DW12/ LIS2MDL/ LSM6DSO/  # ST 加速度/磁力/6 轴 IMU
├── misc/                         # 其它外设
│   ├── AT24XX/                   # EEPROM
│   ├── DS1302/ DS1307/ DS3231/   # RTC 实时时钟
│   └── irqUART/                  # 引脚中断模拟 UART 接收中断
├── neopixel/                     # WS281x 全彩灯板
│   ├── neo_16x16/                # 16x16 单色位图显示
│   └── neo_16x16_img/            # 16x16 彩色位图显示
└── keyboard/
    └── mechanical-button/single-button/  # 单机械按键（单击/连击/长按）
```

> 顶层 [README.md](../README.md) 还列出了 `radio`、`bluetooth` 两个分类，但当前仓库中**并不存在对应目录**（未实现/未收录）。

---

## 3. 驱动模块总览

| 分类 | 驱动 / 类名 | 器件 / 芯片 | 通信接口 | 驱动文件 |
| --- | --- | --- | --- | --- |
| LCD | `LCD1602` | PCF8574 + HD44780 兼容 LCD1602 | I2C | [mp_i2c_lcd1602.py](../lcd/I2C_LCD1602/mp_i2c_lcd1602.py) |
| LCD | `HT1621B` + `GDC03849` | HT1621B + GDC03849 段码屏 | 3-Wire + CS | [ht1621x.py](../lcd/3Wire-HT1621B-GDC03849/ht1621x.py) / [gdc03849.py](../lcd/3Wire-HT1621B-GDC03849/gdc03849.py) |
| LED | `OLED12864_I2C` | SSD1306 128×64 OLED | I2C | [oled.py](../LED/OLED_I2C_ASC/oled.py) |
| LED | `TM1637` | TM1637 四位数码管 | 两线（CLK/DIO） | [TM1637.py](../LED/TM1637/TM1637.py) |
| LED | `FourDigitDisplay` | TM1650 / HBS650 四位数码管 | I2C | [FourDigitDisplay.py](../LED/TM1650/FourDigitDisplay.py) |
| Sensor | `BMP180` | BMP180 气压 | I2C | [BMP180.py](../sensor/bmp180/BMP180.py) |
| Sensor | `BMP280` | BMP280 气压 | I2C | [bmp280.py](../sensor/bmp280/bmp280.py) |
| Sensor | `BME280` | BME280 气压 + 湿度 | I2C | [bme280.py](../sensor/bme280/bme280.py) |
| Sensor | `APDS9930` | APDS-9930 环境光/接近 | I2C | [APDS9930.py](../sensor/APDS9930/APDS9930.py) |
| Sensor | `HTS221` | HTS221 温湿度 | I2C | [hts221.py](../sensor/HTS221/hts221.py) |
| Sensor | `LPS22` | LPS22HB/HD/HH 气压 | I2C | [LPS22.py](../sensor/LPS22/LPS22.py) |
| Sensor | `STTS751` | STTS751 温度 | I2C | [STTS751.py](../sensor/STTS751/STTS751.py) |
| Sensor | `LIS2DW12` | LIS2DW12 三轴加速度 | I2C | [LIS2DW12.py](../sensor/LIS2DW12/LIS2DW12.py) |
| Sensor | `LIS2MDL` | LIS2MDL 三轴磁力 | I2C | [LIS2MDL.py](../sensor/LIS2MDL/LIS2MDL.py) |
| Sensor | `LSM6DSO` | LSM6DSO 6 轴 IMU | I2C | [LSM6DSO.py](../sensor/LSM6DSO/LSM6DSO.py) |
| Misc | `AT24XX` | AT24/AT25 系列 EEPROM | I2C | [AT24XX.py](../misc/AT24XX/AT24XX.py) |
| Misc | `DS1302` | DS1302 RTC | 三线同步串口 | [DS1302.py](../misc/DS1302/DS1302.py) |
| Misc | `DS1307` | DS1307 RTC | I2C | [DS1307.py](../misc/DS1307/DS1307.py) |
| Misc | `DS3231` | DS3231 RTC | I2C | [DS3231.py](../misc/DS3231/DS3231.py) |
| Misc | `irqUART` | 任意 UART + 引脚中断 | GPIO 中断 + UART | [irqUART.py](../misc/irqUART/irqUART.py) |
| Neopixel | `neo16x16` | WS2812 16×16 灯板 | 单总线 | [neo16x16.py](../neopixel/neo_16x16/neo16x16.py) |
| Neopixel | `neo16x16_img` | WS2812 16×16 彩色灯板 | 单总线 | [neo16x16_img.py](../neopixel/neo_16x16_img/neo16x16_img.py) |
| Keyboard | `KEYBOARD` | 单个机械按键 | GPIO + 定时器 | [keyboard.py](../keyboard/mechanical-button/single-button/keyboard.py) |

---

## 4. 快速开始

以 I2C 传感器为例（其余驱动同理）：

```python
from machine import I2C, Pin
import bmp280                       # 将 bmp280.py 复制到板子文件系统

i2c = I2C(1)                        # 或 I2C(sda=Pin(5), scl=Pin(4))
b = bmp280.BMP280(i2c)
print(b.get())                      # [温度℃, 气压Pa]
```

1. 将目标驱动 `.py` 文件拷贝到开发板文件系统（根目录或被 `sys.path` 包含的目录）。
2. 将 `test.py` / `demo.py` 一并拷贝并用 REPL（Thonny、rshell、mpremote、ampy 等）执行。
3. 具体接线、I2C 地址与 `machine` 构造参数见各模块章节与仓库内 `README.md`。

---

## 5. 文档导航

| 文档 | 内容 |
| --- | --- |
| [architecture.md](architecture.md) | 整体架构、分层模型、驱动设计约定、**依赖关系**、命名规范 |
| [lcd.md](lcd.md) | LCD 模块（LCD1602、HT1621B + GDC03849）关键类与函数 |
| [led.md](led.md) | LED 模块（OLED12864、TM1637、TM1650）关键类与函数 |
| [sensor.md](sensor.md) | 传感器模块（Bosch / ST 系列）关键类与函数 |
| [misc.md](misc.md) | 外设模块（AT24XX、DS1302/07/3231、irqUART） |
| [neopixel.md](neopixel.md) | Neopixel 16×16 模块 |
| [keyboard.md](keyboard.md) | 机械按键（KEYBOARD）模块 |
| [runtime.md](runtime.md) | 运行/部署方式、平台差异与注意事项 |
