# 寄存器映射

本页汇总各驱动实际使用的芯片寄存器地址、初始化值与数据含义，便于对照 Datasheet 调试。数据均从源码提取。

> 说明：`+1` 表示驱动读取时在基址上加 1（多为 RTC 的"读地址 = 写地址 +1"约定）；"读"列给出驱动使用的地址。

---

## 1. ST 传感器

### HTS221（温湿度，地址 `0x5F`）
源码：[hts221.py](../sensor/HTS221/hts221.py)

| 寄存器 | 地址 | 读/写 | 说明 |
| --- | --- | --- | --- |
| AV_CONF | `0x10` | 写 | 初始化 `0x26`（T 采样 4、H 采样 8） |
| CTRL_REG1 | `0x20` | 读写 | 初始化 `0x85`（PD=1, BDU=1, ODR=1）；bit0 单次模式；bit7 PD |
| CTRL_REG2 | `0x21` | 读写 | bit0=1 触发单次测量 |
| STATUS | `0x27` | 读 | bit1 温度就绪（`ONE_SHOT(1)`）；bit2 湿度就绪（`ONE_SHOT(2)`） |
| HUMIDITY_OUT_L/H | `0x28`/`0x29` | 读 | 16 位湿度原始值 |
| TEMP_OUT_L/H | `0x2A`/`0x2B` | 读 | 16 位温度原始值 |
| H0_rH / H1_rH | `0x30` / `0x31` | 读 | 读出值 ×5 得 %RH 标定 |
| T0_degC_x8 / T1_degC_x8 | `0x32` / `0x33` | 读 | 温度标定低 8 位 |
| T1/T0 MSB | `0x35` | 读 | 低 4 位拆分标定高位 |
| H0_OUT / H1_OUT | `0x36` / `0x3A` | 读 | 湿度标定原始值（int16） |
| T0_OUT / T1_OUT | `0x3C` / `0x3E` | 读 | 温度标定原始值（int16） |

### LPS22（气压，地址 `0x5D`）
源码：[LPS22.py](../sensor/LPS22/LPS22.py)

| 寄存器 | 地址 | 说明 |
| --- | --- | --- |
| CTRL_REG1 | `0x10` | 初始化 `0x1A`（ODR=1, EN_LPFP=1, BDU=1）；bit4 单次电压控制 |
| CTRL_REG2 | `0x11` | bit0=1 单次测量触发 |
| STATUS | `0x27` | bit1 气压就绪（`ONE_SHOT(1)`）；bit2 温度就绪（`ONE_SHOT(2)`） |
| PRESS_OUT_XL/L/H | `0x28`/`0x29`/`0x2A` | 气压 24 位；`(XL + L<<8 + H<<16)/4096` hPa |
| TEMP_OUT_L/H | `0x2B`/`0x2C` | 温度 16 位 int16 `/100` ℃ |

### STTS751（温度，地址 `0x4A`）
源码：[STTS751.py](../sensor/STTS751/STTS751.py)

| 寄存器 | 地址 | 说明 |
| --- | --- | --- |
| STATUS | `0x01` | `<0x80` 表示转换完成（`ONE_SHOT` 轮询条件） |
| CONFIG | `0x03` | bit6 单次模式；bit3:2 分辨率 |
| Conversion Rate | `0x04` | 转换速率 |
| TEMP_VALUE_HIGH | `0x00` | 温度高字节（主读数） |
| TEMP_VALUE_LOW | `0x02` | 温度低字节 |
| TEMP_HIGH_H/L | `0x05`/`0x06` | 高温阈值 |
| TEMP_LOW_H/L | `0x07`/`0x08` | 低温阈值 |
| ONESHOT | `0x0F` | 写 1 触发单次测量 |
| THERM / HYS | `0x20`/`0x21` | 温度比较器 |

分辨率表 `STTS751_RESOLUTION = (8,0,4,12,10,11,9,12)`，`resolution(9..12)` 选择。

### LIS2DW12（加速度，地址 `0x19`）
源码：[LIS2DW12.py](../sensor/LIS2DW12/LIS2DW12.py)

| 寄存器 | 地址 | 说明 |
| --- | --- | --- |
| CTRL1 | `0x20` | 初始化 `0x51`（ODR=5, MODE=0, LP=1）；bit3:0 电源/ODR；单次模式置 `0x08` |
| CTRL2 | `0x21` | 初始化 `0x0C`（BDU=1） |
| CTRL3 | `0x22` | 初始化 `0x02`（SLP_MODE_SEL=1）；bit0=1 触发单次（轮询至 0） |
| CTRL6 | `0x25` | bit5:4 满量程 `FS`（scale 左移 4） |
| STATUS | `0x27` | 数据就绪 |
| OUT_T_L | `0x0D` | 温度输出 |
| OUT_X_L / Y_L / Z_L | `0x28` / `0x2A` / `0x2C` | 三轴 16 位 int16 |

量程表 `LIS2DW12_SCALE = ('2g','4g','8g','16g')`；mg 换算系数 `0.061 << scale`。

### LIS2MDL（磁力计，地址 `0x1E`）
源码：[LIS2MDL.py](../sensor/LIS2MDL/LIS2MDL.py)

| 寄存器 | 地址 | 说明 |
| --- | --- | --- |
| CFG_REG_A | `0x60` | 初始化 `0x80`（TEMP_EN=1）；bit1:0 MD 模式，单次置 `0x01` |
| CFG_REG_C | `0x62` | 初始化 `0x10`（BDU=1） |
| STATUS_REG | `0x67` | bit3=1 表示数据就绪（`ONE_SHOT` 轮询） |
| OUTX_L / Y_L / Z_L | `0x68` / `0x6A` / `0x6C` | 三轴 16 位 int16；uT = raw*3//20 |

### LSM6DSO（加速度+陀螺仪，地址 `0x6B`）
源码：[LSM6DSO.py](../sensor/LSM6DSO/LSM6DSO.py)

| 寄存器 | 地址 | 说明 |
| --- | --- | --- |
| CTRL1_XL | `0x10` | 初始化 `0x10`（ODR_XL=1）；bit3:0 电源；bit3:2 FS_XL（`scale_a<<2`） |
| CTRL2_G | `0x11` | 初始化 `0x12`（ODR_G=1, FS_125=1）；`scale_g<<1` |
| CTRL3_C | `0x12` | 初始化 `0x44`（BDU=1, IF_INC=1） |
| CTRL6_C | `0x15` | 陀螺仪滤波等 |
| CTRL8_XL | `0x17` | 初始化 `0` |
| STATUS | `0x1E` | 数据就绪 |
| OUT_TEMP_L | `0x20` | 温度 |
| OUTX_L_G / Y_L_G / Z_L_G | `0x22` / `0x24` / `0x26` | 陀螺仪三轴 |
| OUTX_L_A / Y_L_A / Z_L_A | `0x28` / `0x2A` / `0x2C` | 加速度三轴 |

量程表：`LSM6DSO_SCALEA=('2g','16g','4g','8g')`、`LSM6DSO_SCALEG=('250','125','500','','1000','','2000')`。
换算：加速度 `0.061 × scale_a_c` mg；角速度 `4.375 × scale_g_c` mdps。

---

## 2. Bosch 传感器

### BMP180（地址 `0x77`）
源码：[BMP180.py](../sensor/bmp180/BMP180.py)

| 寄存器 | 地址 | 说明 |
| --- | --- | --- |
| 标定系数 | `0xAA`–`0xBF` | AC1(0xAA)、AC2(0xAC)、AC3(0xAE)、AC4(0xB0)、AC5(0xB2)、AC6(0xB4)、B1(0xB6)、B2(0xB8)、MB(0xBA)、MC(0xBC)、MD(0xBE)，连续两字节大端 |
| CTRL | `0xF4` | 写 `0x2E` 测温度，写 `0x34` 测气压 |
| OUT | `0xF6`–`0xF8` | 测量结果（`measure()` 读 `0xF6` 两字节） |

> `get2Reg` 为**大端**（`t[0]*256 + t[1]`）。BMP180 已不推荐，建议用 BMP280。

### BMP280（地址 `0x76`）
源码：[bmp280.py](../sensor/bmp280/bmp280.py)

| 寄存器 | 地址 | 说明 |
| --- | --- | --- |
| 标定系数 | `0x88`–`0x9E` | dig_T1..dig_P9，小端 |
| CTRL_MEAS | `0xF4` | 初始化 `0x2F`（正常模式）；`poweroff` 写 0 |
| CONFIG | `0xF5` | 初始化 `0x0C`（IIR 滤波） |
| PRESS | `0xF7`/`0xF8`/`0xF9` | 气压 20 位（`>>4` 取有效位） |
| TEMP | `0xFA`/`0xFB`/`0xFC` | 温度 20 位 |

### BME280（地址 `0x76`）
源码：[bme280.py](../sensor/bme280/bme280.py)

在 BMP280 基础上增加湿度标定与数据：

| 寄存器 | 地址 | 说明 |
| --- | --- | --- |
| dig_H1 | `0xA1` | 湿度标定 |
| dig_H2..H6 | `0xE1`–`0xE7` | 湿度标定（H4/H5 由 0xE4/0xE5/0xE6 组合） |
| CTRL_HUM | `0xF2` | 初始化 `0x04` |
| HUMIDITY | `0xFD`/`0xFE` | 湿度 16 位 |

---

## 3. APDS9930（接近/环境光，地址 `0x39`）
源码：[APDS9930.py](../sensor/APDS9930/APDS9930.py)（注意其**非标准 I2C 访问协议**，见 [protocols.md](protocols.md#5-apds9930-的特殊-i2c-访问)）

| 寄存器 | 地址 | 初始化值 | 说明 |
| --- | --- | --- | --- |
| ENABLE | `0x00` | `0` | bit0 电源、bit1 ALS、bit2 接近、bit3 等待 |
| ATIME | `0x01` | `0xFF` | ALS 积分时间 |
| PTIME | `0x02` | `0xFF` | 接近积分时间 |
| WTIME | `0x03` | `0xFF` | 等待时间 |
| AILTL/AILTH/AIHTL/AIHTH | `0x04`–`0x07` | — | ALS 中断阈值 |
| PILTL/PILTH/PIHTL/PIHTH | `0x08`–`0x0B` | — | 接近中断阈值 |
| PERS | `0x0C` | `0x22` | 中断持久性 |
| CONFIG | `0x0D` | `0` | 配置 |
| PPULSE | `0x0E` | `8` | 接近脉冲数 |
| CONTROL | `0x0F` | `0x2C` | bit1:0 AGAIN、bit3:2 PGAIN |
| ID | `0x12` | — | 器件 ID |
| STATUS | `0x13` | — | 中断状态 |
| Ch0DATA L/H | `0x14`/`0x15` | — | ALS 通道 0 |
| Ch1DATA L/H | `0x16`/`0x17` | — | ALS 通道 1 |
| PDATA L/H | `0x18`/`0x19` | — | 接近数据 |
| POFFSET | `0x1E` | — | 接近偏移 |

增益表：`APDS9930_AGAIN=(1,8,16,120)`、`APDS9930_PGAIN=(1,2,4,8)`；ALS 系数 `DF=52, GA=0.49, B=1.862, C=0.746, D=1.291`。

---

## 4. RTC 与存储器

### DS1302（三线串行，非 I2C）
源码：[DS1302.py](../misc/DS1302/DS1302.py)

| 寄存器 | 写地址 | 读地址 | 说明 |
| --- | --- | --- | --- |
| SEC / MIN / HOUR | `0x80`/`0x82`/`0x84` | +1 | BCD；秒 bit7=CH 停振位 |
| DAY / MONTH / WEEKDAY | `0x86`/`0x88`/`0x8A` | +1 | BCD |
| YEAR | `0x8C` | +1 | 两位年，读时 +2000 |
| WP | `0x8E` | +1 | 写保护：0 允许、`0x80` 禁止 |
| CTRL | `0x90` | +1 | 涓流充电 |
| RAM | `0xC0` | +1 | 31 字节，步长 2 |

### DS1307（I2C `0x68` = 104）
源码：[DS1307.py](../misc/DS1307/DS1307.py)

| 寄存器 | 地址 | 说明 |
| --- | --- | --- |
| SEC/MIN/HOUR/WEEKDAY/DAY/MONTH/YEAR | `0x00`–`0x06` | BCD；秒 bit7=CH 停振 |
| CTRL | `0x07` | 控制 |
| RAM | `0x08`–`0x3F` | 56 字节 |

### DS3231（I2C `0x68`）
源码：[DS3231.py](../misc/DS3231/DS3231.py)

| 寄存器 | 地址 | 说明 |
| --- | --- | --- |
| SEC/MIN/HOUR/WEEKDAY/DAY/MONTH/YEAR | `0x00`–`0x06` | BCD |
| A1SEC/A1MIN/A1HOUR/A1DAY | `0x07`–`0x0A` | 闹钟 1 |
| A2MIN/A2HOUR/A2DAY | `0x0B`–`0x0D` | 闹钟 2 |
| CTRL | `0x0E` | 初始化 `0x4C`；bit5:4 中断使能，bit2 `0x46` |
| STATUS | `0x0F` | `ClearALARM()` 写 0 |
| AGING | `0x10` | 老化偏移 |
| TEMP | `0x11`/`0x12` | 温度（高字节 + 低字节/256） |

周期常量：`PER_DISABLE(0)/PER_MINUTE(1)/PER_HOUR(2)/PER_DAY(3)/PER_WEEKDAY(4)/PER_MONTH(5)`。

### AT24C32 EEPROM（I2C `0x50` = 80）
源码：[AT24XX.py](../misc/AT24XX/AT24XX.py)

无寄存器概念，采用 **2 字节内存地址**（高字节 + 低字节）。`byte/word/dword/buf` 读写均先写地址再读数据。

---

## 5. 显示类

### LCD1602（PCF8574 I2C）
源码：[mp_i2c_lcd1602.py](../lcd/I2C_LCD1602/mp_i2c_lcd1602.py)

- 默认地址 `LCD_I2C_ADDR = 63 (0x3F)`；`autoaddr()` 仅探测 `0x20` 与 `0x3F`。
- PCF8574 位定义：`BK=0x08`（背光）、`RS=0x00`、`E=0x04`。
- HD44780 初始化命令：`0x33, 0x30, 0x20, 0x28, 0x0C, 0x06, 0x01`。

### OLED SSD1306（I2C `0x3C`）
源码：[oled.py](../LED/OLED_I2C_ASC/oled.py)

- 控制字节：命令 `0x00`，数据 `0x40`。
- 初始化命令序列见源码 `cmd` 列表（`0xAE` 关屏、`0xA8 0x3F` 复用率、`0x20 0x00` 水平寻址、`0x81 0xCF` 对比度、`0xAF` 开屏等）。
- FB 缓冲区为 `bytearray(1025)`，`screen[0]=0x40` 为数据前缀。

### TM1637（两线）
源码：[TM1637.py](../LED/TM1637/TM1637.py)

| 常量 | 值 | 说明 |
| --- | --- | --- |
| TM1637_CMD1 | `0x40` | 数据命令（自动地址递增） |
| TM1637_CMD2 | `0xC0` | 地址命令（+位号） |
| TM1637_CMD3 | `0x80` | 显示控制（显示开 + 亮度） |
| TM1637_DELAY | `10` µs | 位间延时 |
| `_SEGMENTS` | 16 项 | 0–F 段码表 |

### TM1650（I2C）
源码：[FourDigitDisplay.py](../LED/TM1650/FourDigitDisplay.py)

- 命令地址 `0x24`，显示地址 `0x34`（+位号 0–3）。
- 亮度/开屏：`cmd((intensity<<4)|0x01)`；关屏 `cmd(0)`。
- 段码表与 TM1637 相同。

### HT1621B（三线）
源码：[ht1621x.py](../lcd/3Wire-HT1621B-GDC03849/ht1621x.py)

寄存器即**显存地址空间**（0–31，每地址 4 bit）。命令码常量见 [lcd.md](lcd.md#2-ht1621b--gdc03849-三线段码屏)。命令帧结构见 [protocols.md](protocols.md#2-ht1621b-三线位操作)。
