# 运行与部署

本页说明如何把驱动部署到 MicroPython 设备并运行示例，以及平台差异与注意事项。

---

## 1. 运行模型

`micropython-libs` 不是可安装的 Python 包，而是**面向 MicroPython 固件的脚本集合**：

- 没有 `setup.py` / `requirements.txt` / 构建脚本；
- 驱动文件直接放到开发板文件系统，用 `import <驱动模块名>` 使用；
- 示例文件（`test.py` / `*_demo.py` / `*_irq_demo.py`）通常就是可执行的入口，可在 REPL 中 `exec` 或复制后 `import`。

运行环境要求：目标 MCU 固件需包含 `machine` 模块（几乎所有官方 MicroPython 固件都具备）。Neopixel 驱动额外依赖固件自带的 `neopixel` 模块。

---

## 2. 部署步骤

1. **准备设备**：烧录对应 MCU 的 MicroPython 固件，连接串口。
2. **拷贝文件**：将目标驱动的 `<驱动名>.py` 复制到设备（可放根目录或 `sys.path` 覆盖的目录）。
   - OLED 驱动还需一并拷贝 4 个 `Font_*.py`。
   - GDC03849 需同时拷贝 `ht1621x.py` 与 `gdc03849.py`。
3. **拷贝示例**：复制对应 `test.py` / `demo.py` 到设备。
4. **执行**：在 REPL 中运行，例如：

```python
import test              # 运行某驱动目录下的 test.py
```

常用上传/交互工具：

| 工具 | 典型用法 |
| --- | --- |
| **mpremote**（官方） | `mpremote connect <port> cp bmp280.py :` 然后 `mpremote repl` |
| **rshell** | `rshell -p <port> cp <驱动>.py /pyboard/` |
| **ampy** | `ampy -p <port> put <驱动>.py` |
| **Thonny IDE** | 图形化打开设备文件系统，拖拽拷贝并运行 |
| **PyBoard 虚拟磁盘** | 直接拖拽文件到 `PYBFLASH` 盘 |

> Windows 下部分 PyBoard 存在文件系统写入延迟问题，拷贝完成后请执行 `os.sync()` 或安全弹出。

---

## 3. 平台差异

| 平台 | 说明 |
| --- | --- |
| **PyBoard / STM32**（`sys.platform == 'pyboard'`） | 支持软件 I2C、`pyb.Timer`；irqUART 使用 `Timer.ONE_SHOT`；示例使用 `Pin('B7')` 等端口名 |
| **ESP8266 / ESP32** | 使用硬件 I2C；irqUART 使用 `Timer.PERIODIC`；示例使用数字引脚如 `Pin(22)` |
| **micro:bit** | 部分驱动标注"for microbit"（如 APDS9930），需按其引脚能力适配 |

- I2C 构造方式随平台不同，常见写法：
  - `I2C(1)`（硬件 I2C 端口 1）
  - `I2C(sda=Pin(5), scl=Pin(4))`（ESP 系列）
  - `I2C(-1, scl=Pin(27), sda=Pin(13))`（软件 I2C，OLED 示例）
- 定时器中断示例（`*_irq_demo.py`）使用 `pyb.Timer(1, freq=1)` + `tim.callback(tim_irq)`。

---

## 4. 各模块 I2C 地址速查

| 模块 | 地址 | 备注 |
| --- | --- | --- |
| LCD1602 (PCF8574 / PCF8574A) | `0x27` / `0x3F` | 驱动自动探测`0x20`/`0x3F` |
| OLED12864 (SSD1306) | `0x3C` | 可传 `ADDR` 覆盖 |
| TM1650 (FourDigitDisplay) | 命令 `0x24`，显示 `0x34–0x37` | — |
| BMP180 | `0x77` | — |
| BMP280 / BME280 | `0x76`（SDO 高 `0x77`） | — |
| APDS9930 | `0x39` | 接近功能需 `VL` 接 3.3V |
| HTS221 | `0x5F` | — |
| LPS22 | `0x5D` | LPS22HB/HD/HH |
| STTS751 | `0x4A` | — |
| LIS2DW12 | `0x19` | — |
| LIS2MDL | `0x1E` | — |
| LSM6DSO | `0x6B` | — |
| AT24XX EEPROM | `0x50–0x57` | 默认 `0x50` |
| DS1307 / DS3231 | `0x68` | — |
| DS1302 | 三线（clk/dio/cs） | 非 I2C |
| TM1637 | 两线（clk/dio） | 非 I2C |

---

## 5. 使用注意事项

- **中断上下文限制**：在定时器/引脚中断回调里不能分配内存；ST 传感器的 `*_irq()` 方法即为该场景准备（见 [architecture.md](architecture.md#33-中断中安全读取memoryerror-回退)）。示例 [LSM6DSO_irq_demo.py](../sensor/LSM6DSO/LSM6DSO_irq_demo.py)、[LIS2DW12_irq_demo.py](../sensor/LIS2DW12/LIS2DW12_irq_demo.py) 展示了用法。
- **Neopixel 必须外部供电**：仅靠 MCU 引脚供电会导致亮度/颜色异常或损坏。
- **两个已知源码缺陷**（使用前需处理）：
  - [LIS2MDL.py](../sensor/LIS2MDL/LIS2MDL.py) 含非法 `//` 注释，需删除后模块方可加载；
  - [LSM6DSO.py](../sensor/LSM6DSO/LSM6DSO.py) 的 `get()` 被错误覆盖调用了不存在的 `get_g_raw()`，建议改用 `get_a()`/`get_g()`。
- **文件命名大小写**：仓库中部分文件名为大写（`BMP180.py`、`HT1621B` 所在的 `ht1621x.py` 除外），而示例 `import` 用小写（如 `import bmp180`）。在区分大小写的文件系统上，请将文件名与 `import` 名称保持一致。
- **禁用平台差异**：`HT1621B` 依赖 `Pin` 的 `init(mode, pull, value)` 与 `.value()`/`.on()`/`.off()`；`DS1302`、`TM1637` 依赖 `pin.init(...)` 与位操作，移植到不支持这些方法的固件时需适配。
- **许可与署名**：整体 MIT。二次分发时请保留仓库根 [LICENSE](../LICENSE) 及各文件头部的作者/许可声明（shaoziyang、Robin Chen）。
