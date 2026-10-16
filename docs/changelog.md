# 版本与变更记录

本仓库**没有仓库级 CHANGELOG**，也没有统一版本号。版本信息散落在各文件的头部注释与 `self.version` 属性中。本页将其汇总，便于判断驱动的新旧与兼容性。

## 1. 版本一览

| 模块 | 文件 | 版本 | 日期 | 作者 | 备注 |
| --- | --- | --- | --- | --- | --- |
| LCD1602 | [mp_i2c_lcd1602.py](../lcd/I2C_LCD1602/mp_i2c_lcd1602.py) | `2.0`（`self.version`） | 2018.2 | shaoziyang | 含 I2C 地址自动探测 |
| HT1621B | [ht1621x.py](../lcd/3Wire-HT1621B-GDC03849/ht1621x.py) | `V0.13`（头）/ 函数 `V1.00` | 2018.5 | Robin Chen | 三线段码控制器 |
| GDC03849 | [gdc03849.py](../lcd/3Wire-HT1621B-GDC03849/gdc03849.py) | `V1.00` | 2018.5 | Robin Chen | 依赖 HT1621B |
| OLED12864 | [oled.py](../LED/OLED_I2C_ASC/oled.py) | — | 2020.1 | shaoziyang | 4 套字库 |
| TM1637 | [TM1637.py](../LED/TM1637/TM1637.py) | — | 2018.3 | shaoziyang | |
| TM1650 | [FourDigitDisplay.py](../LED/TM1650/FourDigitDisplay.py) | — | 2018.3 | shaoziyang | |
| BMP180 | [BMP180.py](../sensor/bmp180/BMP180.py) | `2.0`（`self.version`） | 2018.2 | shaoziyang | 已不推荐，建议 BMP280 |
| BMP280 | [bmp280.py](../sensor/bmp280/bmp280.py) | `1.0`（`self.version`） | 2018.2 | shaoziyang | |
| BME280 | [bme280.py](../sensor/bme280/bme280.py) | `1.0`（`self.version`） | 2018.2 | shaoziyang | 温+压+湿 |
| APDS9930 | [APDS9930.py](../sensor/APDS9930/APDS9930.py) | — | 2018.4 | shaoziyang | 特殊 I2C 协议 |
| HTS221 | [hts221.py](../sensor/HTS221/hts221.py) | `2.0`（v1.0 → v2.0） | 2019.7（v1.0 2016.4） | shaoziyang | 含 oneshot / irq |
| LPS22 | [LPS22.py](../sensor/LPS22/LPS22.py) | `2.0`（v1.0 → v2.0） | 2019.7（v1.0 2016.4） | shaoziyang | 含 oneshot / irq |
| STTS751 | [STTS751.py](../sensor/STTS751/STTS751.py) | `1.0` | 2019.7 | shaoziyang | |
| LIS2DW12 | [LIS2DW12.py](../sensor/LIS2DW12/LIS2DW12.py) | `1.0` | 2019.7 | shaoziyang | |
| LIS2MDL | [LIS2MDL.py](../sensor/LIS2MDL/LIS2MDL.py) | `1.0` | 2019.7 | shaoziyang | 见已知缺陷 |
| LSM6DSO | [LSM6DSO.py](../sensor/LSM6DSO/LSM6DSO.py) | `1.0` | 2019.7 | shaoziyang | 见已知缺陷 |
| AT24XX | [AT24XX.py](../misc/AT24XX/AT24XX.py) | — | 2018.3 | shaoziyang | |
| DS1302 | [DS1302.py](../misc/DS1302/DS1302.py) | — | 2018.3 | shaoziyang | 三线 RTC |
| DS1307 | [DS1307.py](../misc/DS1307/DS1307.py) | — | 2018.3 | shaoziyang | |
| DS3231 | [DS3231.py](../misc/DS3231/DS3231.py) | — | 2018.3 | shaoziyang | 含闹钟 |
| irqUART | [irqUART.py](../misc/irqUART/irqUART.py) | — | 2020.6 | shaoziyang | 中断接收 |
| neo16x16 | [neo16x16.py](../neopixel/neo_16x16/neo16x16.py) | — | 2018.2 | shaoziyang | |
| neo16x16_img | [neo16x16_img.py](../neopixel/neo_16x16_img/neo16x16_img.py) | — | 2018.2 | shaoziyang | 彩色位图 |
| KEYBOARD | [keyboard.py](../keyboard/mechanical-button/single-button/keyboard.py) | — | 2018 | Robin Chen | MIT |

## 2. 时间线

```
2016.4  HTS221 / LPS22  v1.0（首版）
2018.2  LCD1602、BMP180/280、BME280、neo16x16、neo16x16_img
2018.3  TM1637、TM1650、DS1302、DS1307、DS3231、AT24XX
2018.4  APDS9930
2018.5  HT1621B、GDC03849（Robin Chen）
2019.7  HTS221 / LPS22 → v2.0；新增 STTS751、LIS2DW12、LIS2MDL、LSM6DSO
2020.1  OLED12864_I2C（4 套字库）
2020.6  irqUART
```

## 3. 版本语义观察

- **`v2.0`（2019.7）的两款**（HTS221、LPS22）是唯一发生大版本跃迁的驱动，其变化方向为：新增 `oneshot_mode` 单次测量、`*_irq()` 中断安全接口与 `MemoryError` 回退。
- 同期新增的 ST 传感器（STTS751/LIS2DW12/LIS2MDL/LSM6DSO）直接以 `v1.0` 起步，已经内置上述 oneshot/irq 规范，说明 2019.7 是驱动风格的**统一节点**（见 [architecture.md 设计约定](architecture.md#3-驱动通用设计约定)）。
- 2018 年的多数驱动**没有** `oneshot`/`irq` 接口，仅支持连续转换读取。
- 只有 BMP180/BMP280/BME280 与 LCD1602 在 `__init__` 设置 `self.version` 属性；其余版本仅存在于注释。

## 4. 已知缺陷（截至当前源码，未修复）

| 文件 | 问题 | 影响 | 规避 |
| --- | --- | --- | --- |
| [LIS2MDL.py](../sensor/LIS2MDL/LIS2MDL.py#L81-L93) | 含 C 风格 `// unit uT` 注释，非合法 Python | **模块无法加载**（SyntaxError） | 删除 4 行 `//` 注释 |
| [LSM6DSO.py](../sensor/LSM6DSO/LSM6DSO.py#L128-L143) | `get_a_raw()` 定义了未使用的 `get_g_raw()`；第二个 `get()` 覆盖首个并调用未定义的 `get_g_raw()` | 调用 `get()` 抛 `NameError` | 改用 `get_a()` / `get_g()`，或修复为 `get_g()` 的原始值版本 |

## 5. 文档与示例

仓库各驱动目录下的 `README.md`（多为中英双语）随驱动一起更新，但仓库根 [README.md](../README.md) 自 2018 年后基本未变，其列出的 `radio`、`bluetooth` 分类目录**当前不存在**。
