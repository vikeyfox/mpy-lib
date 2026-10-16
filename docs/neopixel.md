# Neopixel 模块

目录：[neopixel/](../neopixel)｜面向 ESP8266/ESP32 的 WS2812 16×16 全彩灯板，基于 MicroPython 内置 `neopixel` 模块。**显示时灯板必须使用外部供电。**

---

## 1. 单色位图显示 (`neo16x16`)

- 驱动：[neo16x16.py](../neopixel/neo_16x16/neo16x16.py)｜示例：[test.py](../neopixel/neo_16x16/test.py)｜文档：[README.md](../neopixel/neo_16x16/README.md)
- **构造**：`neo16x16(pin)`（内部创建 `neopixel.NeoPixel(pin, 256)`，默认颜色 `(0,0,8)`）

| 方法 | 说明 |
| --- | --- |
| `clear()` | 关闭所有灯 |
| `set(n, color='')` | 设置第 `n`（0–255）个灯为 `color`；不传颜色用默认色 |
| `setcolor(color)` | 设置默认显示颜色 |
| `show(dat, offset=0, clear=True, color='')` | 显示 16×16 位图数据；`dat[x]` 的低 16 位表示该列 16 个灯亮灭，`offset` 为水平偏移并控制奇偶列扫描方向 |

**位图数据格式**：`dat` 为整数列表，每个元素对应一列（bit0–bit15 对应该列 16 行）。

### 示例

```python
from machine import Pin
from neo16x16 import neo16x16
import time

np = neo16x16(Pin(2))
npdat = [0x2008, 0x1FFC, 0x3FF8, ...]   # 见 test.py 中的完整图样
n = 0
while 1:
    np.show(npdat, n)
    n = (n + 1) % 70
    time.sleep_ms(200)
```

---

## 2. 彩色位图显示 (`neo16x16_img`)

- 驱动：[neo16x16_img.py](../neopixel/neo_16x16_img/neo16x16_img.py)｜示例：[test.py](../neopixel/neo_16x16_img/test.py)、[demo.bmp](../neopixel/neo_16x16_img/demo.bmp)｜文档：[README.md](../neopixel/neo_16x16_img/README.md)
- **构造**：`neo16x16_img(pin)`

| 方法 | 说明 |
| --- | --- |
| `clear()` | 关闭所有灯 |
| `set(n, color)` | 设置第 `n`（0–255）个灯颜色 |
| `show(dat, pos=0)` | 显示彩色位图数据 |

**彩色数据格式**：`dat` 为整数列表，每 2 个元素编码一列的上下 8 行；每个整数中 4 位一组表示 R/G/B（`r=t%16, g=(t>>4)%16, b=(t>>8)%16`，高 12 位为另半列）。`pos` 的奇偶决定扫描方向。

> 与 `neo16x16` 不同，`neo16x16_img` 的 `show()` 不做 fill/清屏，需按需调用 `clear()`。
