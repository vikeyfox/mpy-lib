# 传感器模块

目录：[sensor/](../sensor)｜全部为 I2C 器件。分 **Bosch 气压/温湿度**、**ST 系列** 与 **APDS9930** 三组。

所有传感器驱动均遵循 [架构与设计](architecture.md) 中的通用约定：`getreg/setreg/get2reg` 读写寄存器、`int16/short` 符号转换、Unit 换算。

---

## 一、Bosch 系列

### 1. BMP180 气压传感器 (`BMP180`)

- 驱动：[BMP180.py](../sensor/bmp180/BMP180.py)｜示例：[test.py](../sensor/bmp180/test.py)
- **I2C 地址**：`0x77`（常量 `BMP180_I2C_ADDR`）。**README 建议被 BMP280 取代。**
- **构造**：`BMP180(i2c)`

| 方法 | 说明 |
| --- | --- |
| `measure()` | 触发温度/气压一次测量（`0xF4` 写 `0x2E`/`0x34`，各延时 5ms），读原始值 `UT`/`UP` |
| `get()` | 计算并返回 `[温度℃, 气压Pa]` |
| `getTemp()` | 仅温度（℃） |
| `getPress()` | 仅气压（Pa） |
| `getAltitude()` | 绝对高度 `44330*(1-(P/101325)^(1/5.255))` |
| `setReg/getReg/get2Reg/short` | 寄存器与符号转换原语 |

> 无 `poweron()/poweroff()`；血压式补偿参数 `AC1..AC6,B1,B2,MB,MC,MD` 在构造时读取。

### 2. BMP280 气压传感器 (`BMP280`)

- 驱动：[bmp280.py](../sensor/bmp280/bmp280.py)｜示例：[test.py](../sensor/bmp280/test.py)｜文档：[README.md](../sensor/bmp280/README.md)
- **I2C 地址**：默认 `0x76`，SDO 拉高为 `0x77`。
- **构造**：`BMP280(i2c)`；构造时读补偿系数 `dig_T1..T3`、`dig_P1..P9`，默认 `0xF4=0x2F`（正常模式）、`0xF5=0x0C`。

| 方法 | 说明 |
| --- | --- |
| `get()` | 返回 `[温度℃, 气压Pa]` |
| `getTemp()` / `getPress()` / `getAltitude()` | 单项温度/气压/高度 |
| `poweron()` | 进入 normal 模式（`0xF4=0x2F`） |
| `poweroff()` | 进入 sleep 模式（`0xF4=0`） |

### 3. BME280 气压 + 湿度传感器 (`BME280`)

- 驱动：[bme280.py](../sensor/bme280/bme280.py)｜示例：[test.py](../sensor/bme280/test.py)｜文档：[README.md](../sensor/bme280/README.md)
- **I2C 地址**：默认 `0x76`（SDO 高为 `0x77`）。
- 相比 BMP280 **增加了湿度**补偿系数 `dig_H1..H6` 与湿度测量。

| 方法 | 说明 |
| --- | --- |
| `get()` | 返回 `[温度℃, 气压Pa, 湿度%RH]` |
| `getTemp()` / `getPress()` / `getHumi()` / `getAltitude()` | 单项温度/气压/湿度/高度 |
| `poweron()` / `poweroff()` | normal / sleep 模式 |

### Bosch 示例

```python
from machine import I2C
from bmp280 import BMP280          # 或 bme280 / bmp180

b = BMP280(I2C(1))
print(b.get())                     # [温度, 气压]
print(b.getTemp(), b.getPress(), b.getAltitude())
b.poweroff(); b.poweron()
```

---

## 二、ST 系列

ST 驱动共享 `oneshot_mode()`/`ONE_SHOT()` 机制与 `int16()`/`getreg`/`setreg`/`get2reg` 原语；读取方法普遍带 `try/except MemoryError` 回退到 `*_irq()` 版本，以便在定时器中断中使用。多数具备 `power(on)`。

### 1. HTS221 温湿度传感器 (`HTS221`)

- 驱动：[hts221.py](../sensor/HTS221/hts221.py)｜示例：[hts221_demo.py](../sensor/HTS221/hts221_demo.py)、[hts221_irq_demo.py](../sensor/HTS221/hts221_irq_demo.py)
- **I2C 地址**：`0x5F`。版本 ver 2.0。

| 方法 | 说明 |
| --- | --- |
| `get()` | 返回 `(温度℃, 湿度%RH)` |
| `temperature()` / `humidity()` | 单项温/湿度（四舍五入到 0.1） |
| `oneshot_mode(oneshot=None)` | 设/取单次测量模式 |
| `power(on=None)` | 设/取电源（PD 位 0x80） |
| `temperature_irq()` / `humidity_irq()` / `get_irq()` | 中断上下文无分配读取路径 |

### 2. LPS22 气压传感器 (`LPS22`)

- 驱动：[LPS22.py](../sensor/LPS22/LPS22.py)｜示例：[LPS22_demo.py](../sensor/LPS22/LPS22_demo.py)、[LPS22_irq_demo.py](../sensor/LPS22/LPS22_irq_demo.py)
- **器件**：LPS22HB/HD/HH。**I2C 地址**：默认 `0x5D`（`LPS22(i2c, addr=0x5D)`）。版本 ver 2.0。

| 方法 | 说明 |
| --- | --- |
| `get()` | 返回 `(温度℃, 气压hPa)` |
| `temperature()` / `pressure()` | 单项（温度 `/100`，气压 `/4096`） |
| `altitude()` | 由气压+温度推算高度 |
| `oneshot_mode()` / `pressure_irq()` / `temperature_irq()` / `get_irq()` | 模式与中断路径 |

### 3. STTS751 温度传感器 (`STTS751`)

- 驱动：[STTS751.py](../sensor/STTS751/STTS751.py)｜示例：[STTS751_demo.py](../sensor/STTS751/STTS751_demo.py)、[STTS751_irq_demo.py](../sensor/STTS751/STTS751_irq_demo.py)
- **I2C 地址**：`0x4A`。

| 方法 | 说明 |
| --- | --- |
| `temperature()` | 返回温度（℃，`int16(高<<8|低)/256`） |
| `resolution(res=None)` | 设/取分辨率（9–12 位；`STTS751_RESOLUTION` 映射） |
| `oneshot_mode()` / `temperature_irq()` | 模式与中断路径 |

### 4. LIS2DW12 三轴加速度传感器 (`LIS2DW12`)

- 驱动：[LIS2DW12.py](../sensor/LIS2DW12/LIS2DW12.py)｜示例：[LIS2DW12_demo.py](../sensor/LIS2DW12/LIS2DW12_demo.py)、[LIS2DW12_irq_demo.py](../sensor/LIS2DW12/LIS2DW12_irq_demo.py)
- **I2C 地址**：`0x19`。量程常量 `LIS2DW12_SCALE=('2g','4g','8g','16g')`。

| 方法 | 说明 |
| --- | --- |
| `get()` | 返回 `[x, y, z]`（单位 mg） |
| `x()` / `y()` / `z()` | 单轴加速度（mg，`0.061 * scale`） |
| `x_raw()` / `y_raw()` / `z_raw()` / `get_raw()` | 原始有符号值（右移 2 位） |
| `scale(dat=None)` | 设/取量程（传字符串 `'2g'` 等） |
| `temperature()` / `temperature_irq()` | 片内温度 |
| `power(on=None)` / `oneshot_mode()` / `r_w_reg()` | 电源/模式/读改写 |

### 5. LIS2MDL 三轴磁力传感器 (`LIS2MDL`)

- 驱动：[LIS2MDL.py](../sensor/LIS2MDL/LIS2MDL.py)｜示例：[LIS2MDL_demo.py](../sensor/LIS2MDL/LIS2MDL_demo.py)、[LIS2MDL_irq_demo.py](../sensor/LIS2MDL/LIS2MDL_irq_demo.py)
- **I2C 地址**：`0x1E`。

| 方法 | 说明 |
| --- | --- |
| `get()` | 返回 `[x, y, z]`（单位 µT，换算 `*3//20`） |
| `x()` / `y()` / `z()` | 单轴磁场（µT） |
| `x_raw()` / `y_raw()` / `z_raw()` / `get_raw()` | 原始有符号值 |
| `oneshot_mode()` / `ONE_SHOT()` | 单次测量模式 |

> ⚠️ **源码缺陷**：文件中使用了 C 风格注释 `// unit uT`（见 [LIS2MDL.py](../sensor/LIS2MDL/LIS2MDL.py#L81-L93)），这是**非法 Python 语法**。使用前需删除这些注释行，否则整个模块无法加载。

### 6. LSM6DSO 6 轴 IMU (`LSM6DSO`)

- 驱动：[LSM6DSO.py](../sensor/LSM6DSO/LSM6DSO.py)｜示例：[LSM6DSO_demo.py](../sensor/LSM6DSO/LSM6DSO_demo.py)、[LSM6DSO_irq_demo.py](../sensor/LSM6DSO/LSM6DSO_irq_demo.py)
- **I2C 地址**：`0x6B`。量程常量 `LSM6DSO_SCALEA=('2g','16g','4g','8g')`、`LSM6DSO_SCALEG=('250','125','500','','1000','','2000')`。

| 方法 | 说明 |
| --- | --- |
| `ax()/ay()/az()` | 加速度（mg，`0.061 * scale_a_c`） |
| `gx()/gy()/gz()` | 角速度（mdps，`4.375 * scale_g_c`） |
| `get_a()/get_g()/get()` | 返回加速度/角速度三元组（`get()` 返回 `[a, g]`） |
| `ax_raw()..gz_raw()` | 原始有符号值 |
| `scale_a(dat=None)` / `scale_g(dat=None)` | 设/取加速度/角速度量程 |
| `temperature()` / `temperature_irq()` | 片内温度 |
| `power(on=None)` / `r_w_reg()` | 电源/读改写 |

> ⚠️ **源码缺陷**：`get_g` 与 `get` 在类中被**重复定义**，且后定义的 `get()` 调用了并不存在的 `get_g_raw()`（见 [LSM6DSO.py](../sensor/LSM6DSO/LSM6DSO.py#L128-L143)）。实际生效的是后定义版本，调用 `lsm.get()` 会抛 `NameError`。建议改用 `get_a()`/`get_g()` 或单项 `ax()/gx()`。

### ST 示例

```python
from machine import I2C
from LSM6DSO import LSM6DSO        # 或 HTS221 / LPS22 / LIS2DW12 / LIS2MDL / STTS751

lsm = LSM6DSO(I2C(1))
print(lsm.get_a())                 # [ax, ay, az] mg
print(lsm.gx(), lsm.gy(), lsm.gz())# 角速度 mdps
print(lsm.temperature())
```

---

## 三、APDS9930 环境光 + 接近传感器 (`APDS9930`)

- 驱动：[APDS9930.py](../sensor/APDS9930/APDS9930.py)
- 示例：[ALS_demo.py](../sensor/APDS9930/ALS_demo.py)（环境光）、[Proximity_demo.py](../sensor/APDS9930/Proximity_demo.py)（接近）
- 文档：[README.md](../sensor/APDS9930/README.md)
- **I2C 地址**：`0x39`。寄存器访问时地址与 `0xA0` 相或。
- **构造**：`APDS9930(i2c)`（构造中配置 ATIME/PTIME/WTIME/PERS/CONFIG/PPULSE/CONTROL，并启用 ALS 与 Power）

| 方法 | 说明 |
| --- | --- |
| `AGAIN(gain=None)` | 设/取 ALS 增益，可选 `1/8/16/120` |
| `PGAIN(gain=None)` | 设/取接近增益，可选 `1/2/4/8` |
| `Power(on=True)` | 电源开关 |
| `ALS_Enable(on=True)` / `Proximity_Enable(on=True)` / `Wait_Enable(on=True)` | 启用/禁用 ALS、接近、等待计时器 |
| `getALS()` | 环境光照度（lux），基于 Ch0/Ch1 与增益计算 |
| `getProximity()` | 接近值（需 `VL` 引脚接 3.3V，并先 `Proximity_Enable()`） |
| `ATIME(v=None)` / `getCH0()` / `getCH1()` | 积分时间与两通道原始值 |

### 示例

```python
from machine import I2C, Pin
import APDS9930, time

apds = APDS9930.APDS9930(I2C(sda=Pin(5), scl=Pin(4)))
while True:
    time.sleep_ms(500)
    print(apds.getALS())
```
