# 故障排查与常见问题（FAQ）

本页汇总使用本仓库驱动时的常见问题与处理办法。

---

## 加载 / 部署类

**Q：`ImportError: no module named 'xxx'`？**
1. 确认驱动 `.py` 已复制到开发板文件系统（根目录或 `sys.path` 内目录）。
2. 注意**文件名大小写**：仓库中部分文件名为大写（如 `BMP180.py`），而示例 `import` 用小写（`import bmp180`）。在区分大小写的文件系统上二者必须一致，必要时重命名。
3. 确认驱动内部依赖也已拷贝：
   - OLED 需要 `Font_6x8.py`、`Font_8x16.py`、`Font_12x24.py`、`Font_16x32.py`；
   - GDC03849 需要 `ht1621x.py`。

**Q：文件拷进去了但内容没更新？**
PyBoard/Windows 下虚拟磁盘有写入延迟，拷贝后执行 `os.sync()`，或安全弹出/复位后再运行。

**Q：MicroPython 固件没有 `neopixel` 模块？**
neopixel 驱动依赖固件自带的 `neopixel`。请烧录带该模块的 ESP8266/ESP32 固件。

---

## I2C 类

**Q：扫描/读取出错，`OSError: [Errno 19] ENODEV` / 设备无响应？**
- 确认 **I2C 地址**（见 [runtime.md 地址速查](runtime.md#4-各模块-i2c-地址速查)）。BMP280/BME280 默认 `0x76`，SDO 拉高时为 `0x77`；LCD1602 是 `0x27`(PCF8574) 或 `0x3F`(PCF8574A)。
- 检查 SDA/SCL 接线与上拉电阻（多数模块板载上拉）。
- 用 `i2c.scan()` 确认总线上是否存在目标器件。

**Q：`LCD1602` 构造时抛 `I2C address detect error!`？**
`autoaddr()` 仅探测 `0x20` 与 `0x3F`。若你的模块地址为 `0x27`，请在构造时显式传入：`LCD1602(i2c, 0x27)`。

**Q：I2C 读多个寄存器得到乱值？**
部分驱动用 `get2reg(reg)` 读连续两字节，要求器件地址自增开启。若器件被配置为非自增，需逐寄存器读取。

---

## 传感器类

**Q：读数在某器件上偶尔触发 `MemoryError`，尤其放进定时器回调后？**
这是**中断上下文无法分配内存**导致。改用驱动的 `*_irq()` / `get_irq()` 方法（无内存分配路径），参考 [architecture.md 3.3](architecture.md#33-中断中安全读取memoryerror-回退)。

**Q：APDS9930 `getProximity()` 一直是 0？**
接近功能需要 **`VL` 引脚接 3.3V**，且先调用 `Proximity_Enable()` 再读取。

**Q：LSM6DSO 调用 `get()` 抛 `NameError: get_g_raw`？**
源码缺陷：`get()` 被重复定义且引用了未定义的 `get_g_raw()`。请改用 `get_a()` / `get_g()`，或单项 `ax()`/`gx()`。

**Q：`import LIS2MDL` 直接报语法错误？**
源码中含 C 风格 `// unit uT` 注释（非法 Python 语法）。删除这些注释行后即可加载。

**Q：BMP180 的读数与预期不符 / 想换传感器？**
仓库 README 明确建议用 **BMP280** 替代 BMP180。

---

## 显示类

**Q：OLED 传了 `Font('Font_12x24')` 但字号没变？**
- 必须调用**大写** `Font(...)`（会重新绑定 `self.char/self.text`）；小写 `font(...)` 只是写属性、不生效。
- 传参可用常量（`Font_12_24`）或字符串（`'Font_12x24'`）。

**Q：OLED 调用 `line()` 没反应？**
`line()` 在 `oled.py` 中是**空实现（占位）**，请改用 `hline()`/`vline()`/`rect()`。

**Q：`FourDigitDisplay.showDP()` 索引越界？**
该方法直接以 `bit` 索引 `dbuf`，请保证 `bit` 在 0–3 之间。

**Q：Neopixel 亮度低/颜色错乱甚至损坏？**
灯板**必须外部供电**，不要仅靠 MCU 引脚供电。

---

## RTC 类

**Q：DS1302 写入时间不生效？**
DS1302 有写保护寄存器。驱动的 `wr()` 已自动在写入前后切换写保护（`DS1302_REG_WP`），若自行调用 `setReg()` 直接写则可能被保护拦截。

**Q：读到的年份是 2000+ 偏移？**
RTC 只存两位年，读写时驱动会做 `+2000` / `%100` 处理；请以 `DateTime()` 返回的完整年份为准。

**Q：DS3231 闹钟中断后 SQW 一直有效？**
需要手动调用 `ClearALARM()` 清除标志以复位输出。

---

## 通信 / 其它

**Q：irqUART 大量接收丢数据？**
- 增大 UART `rxbuf`；
- 调整 `CHR_TMO`（依波特率、缓冲区大小）与 `FRAME_TMO`（依帧间隔）。

**Q：irqUART 在 PyBoard 与 ESP32 行为不同？**
驱动内部按 `sys.platform` 切换定时器模式（pyboard 用 `ONE_SHOT`，其它用 `PERIODIC`）。撰写跨平台代码时注意该差异。

**Q：按键事件回调里执行了耗时操作就报错？**
`KEYBOARD.doBtnScan()` 运行于定时器中断，回调须尽量短（只做标记/入队打印），耗时逻辑放到主循环。计时长按与定时长按由 `staLon` 二选一。

---

## 兼容性 / 移植

**Q：换 MCU 平台后驱动不工作？**
驱动仅依赖 `machine`（`I2C`/`Pin`/`Timer`/`UART`），移植时主要改动：
- I2C 构造形式（`I2C(1)` vs `I2C(sda=..., scl=...)` vs 软件 `I2C(-1, ...)`）；
- 引脚名（`Pin('B7')` 端口名 vs `Pin(22)` 数字）；
- 定时器模式（见上）。
个别驱动（`HT1621B`、`DS1302`、`TM1637`）依赖 `pin.init(mode, pull, value)` 与 `pin.value()/on()/off()`，需目标固件支持。

---

## 仍无法解决

- 对照对应驱动目录的 `README.md`（多为中英双语）核对接线与 API；
- 参考同目录 `test.py` / `*_demo.py` 的最小可用写法；
- HT1621B/GDC03849 与 DS1302 的时序细节可查 [DataSheet/](../lcd/3Wire-HT1621B-GDC03849/DataSheet)。
