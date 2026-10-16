# API 参考

本页汇总所有驱动类、方法与常量的完整签名，便于按模块快速查阅。各模块的使用背景见对应模块章节。

> 约定：标注 *(内部)* 的方法一般不直接调用；带默认值的参数可省略。

---

## LCD

### `LCD1602` — I2C LCD1602
文件：[mp_i2c_lcd1602.py](../lcd/I2C_LCD1602/mp_i2c_lcd1602.py)｜常量 `LCD_I2C_ADDR`

```
LCD1602(i2c, addr=0)
  setReg(dat)                    (内部)
  send(dat)                      (内部)
  setcmd(cmd)                    (内部)
  setdat(dat)                    (内部)
  autoaddr()                     探测 I2C 地址 (内部)
  clear()
  backlight(on)                  on: 1/0
  on()
  off()
  shl() / shr()                  显示左移/右移
  char(ch, x=-1, y=0)
  puts(s, x=0, y=0)
  newline()
  print(s)                       流式打印（自动换行滚动）
```

### `HT1621B` — 段码 LCD 控制器
文件：[ht1621x.py](../lcd/3Wire-HT1621B-GDC03849/ht1621x.py)

```
HT1621B(_cs, _rd, _wr, _htdata)
  init(_timer=CMD_TIMER_DIS, _wdt=CMD_WDT_DIS, _scs=CMD_RC256K,
       _bias=CMD_B3C4, _tone=CMD_TONE4K, _irq=CMD_IRQ_DIS,
       _twc=CMD_F128, _mod=CMD_NORMAL)
  _wrData(_da)                   (内部)
  HT1621xWrCmd(_cmd)
  HT1621xWrOneData(_addr, _htdata)
  HT1621xWrAllData(_addr, _htdata)
  ALLSHOW(_addr, _nbit)          _nbit 1-32
  ALLCLEAR(_addr, _nbit)
  LCDON() / LCDOFF()
  HTBEEP(_t)                     _t 毫秒
```

**常量**：`FLAG_CMD/FLAG_READ/FLAG_WRITE/FLAG_MODIFY`；`CMD_LCDON/CMD_LCDOFF`；`CMD_SYSEN/CMD_SYSDIS`；`CMD_B2C2/B2C3/B2C4/B3C2/B3C3/B3C4`；`CMD_RC256K/CMD_EXT256K/CMD_XTAL32K`；`CMD_TIMER_EN/CMD_TIMER_DIS/CMD_CLR_TIMER`；`CMD_WDT_DIS/CMD_WDT_EN/CMD_CLR_WDT`；`CMD_TONE2K/CMD_TONE4K/CMD_TONEON/CMD_TONEOFF`；`CMD_F1..CMD_F128`；`CMD_IRQ_DIS/CMD_IRQ_EN`；`CMD_TEST/CMD_NORMAL`。

### `GDC03849` — 温湿度段码屏
文件：[gdc03849.py](../lcd/3Wire-HT1621B-GDC03849/gdc03849.py)

```
GDC03849(_ht1621x)
  viewTemp(_gdcdata)             浮点温度
  viewRH(_gdcdata)               浮点湿度
  LCDALLSHOW() / LCDALLCLEAR()
  TEMPCLEAR() / RHCLEAR()
```

**常量**：`NUMCODE_RH_HEX`、`NUMCODE_TEMP_HEX`。

---

## LED

### `OLED12864_I2C` — SSD1306 OLED
文件：[oled.py](../LED/OLED_I2C_ASC/oled.py)｜常量 `OLED_ADDR=0x3C`、`Font_6_8=1`、`Font_8_16=2`、`Font_12_24=3`、`Font_16_32=4`

```
OLED12864_I2C(i2c, ADDR=OLED_ADDR)
  command(c)                     (内部)
  set_pos(col=0, page=0)         (内部)
  pixel(x, y, color=1)
  invert(v=1) / on(v=1)
  clear(c=0)
  draw()
  line(x1,y1,x2,y2,c=1)          未实现（占位）
  hline(x, y, len, c=1) / vline(x, y, len, c=1)
  rect(x1, y1, x2, y2, c=1)
  scroll()
  char_6x8(x,y,ch,c=1)   text_6x8(x,y,s,c=1,wrap=0)
  char_8x16(...)         text_8x16(...)
  char_12x24(...)        text_12x24(...)
  char_16x32(...)        text_16x32(...)
  Font(Font)                     绑定字号，改变 self.char/self.text
  font(FONT)                     仅设 self.FONT 属性
  print(s, c=1, cr=1)            流式打印
```
属性：`width=128, height=64, MAX_X=127, MAX_Y=63`；`self.char`/`self.text` 动态绑定。

### `TM1637` — 两线四位数码管
文件：[TM1637.py](../LED/TM1637/TM1637.py)｜常量 `TM1637_CMD1=0x40`、`TM1637_CMD2=0xC0`、`TM1637_CMD3=0x80`、`TM1637_DELAY=10`、`_SEGMENTS`

```
TM1637(clk, dio, intensity=7, number=4)
  on() / off()
  intensity(val=None)            val 0-8
  clear()
  showbit(num, bit=0)
  showDP(bit=1, show=True)
  shownum(num)
  showhex(num)
```

### `FourDigitDisplay` — TM1650/HBS650 四位数码管
文件：[FourDigitDisplay.py](../LED/TM1650/FourDigitDisplay.py)｜常量 `COMMAND_I2C_ADDRESS=0x24`、`DISPLAY_I2C_ADDRESS=0x34`

```
FourDigitDisplay(i2c)
  intensity(dat=-1)              dat 0-8
  cmd(c)  (内部)   dat(bit, d)  (内部)
  on() / off()
  clear()
  showbit(num, bit=0)
  shownum(num) / showhex(num)
  showDP(bit=1, show=True)
```

---

## Sensor — Bosch

### `BMP180`
文件：[BMP180.py](../sensor/bmp180/BMP180.py)｜常量 `BMP180_I2C_ADDR=0x77`

```
BMP180(i2c)
  short(dat)   setReg(reg,dat)   getReg(reg)   get2Reg(reg)   (内部)
  measure()                     触发一次测量 (内部/可调)
  get()                         -> [温度℃, 气压Pa]
  getTemp() / getPress() / getAltitude()
```

### `BMP280`
文件：[bmp280.py](../sensor/bmp280/bmp280.py)｜常量 `BMP280_I2C_ADDR=0x76`

```
BMP280(i2c)
  short/setReg/getReg/get2Reg   (内部)
  get()                         -> [温度℃, 气压Pa]
  getTemp() / getPress() / getAltitude()
  poweron() / poweroff()
```

### `BME280`
文件：[bme280.py](../sensor/bme280/bme280.py)｜常量 `BME280_I2C_ADDR=0x76`

```
BME280(i2c)
  short/setReg/getReg/get2Reg   (内部)
  get()                         -> [温度℃, 气压Pa, 湿度%RH]
  getTemp() / getPress() / getHumi() / getAltitude()
  poweron() / poweroff()
```

---

## Sensor — ST

通用内部方法（各 ST 类均有）：`int16(d)`、`setreg(reg,dat)`、`getreg(reg)`、`get2reg(reg)`、`r_w_reg(reg,dat,mask)`（部分）。

### `HTS221`
文件：[hts221.py](../sensor/HTS221/hts221.py)｜地址 `0x5F`

```
HTS221(i2c)
  get()                         -> (温度℃, 湿度%RH)
  temperature() / humidity()
  oneshot_mode(oneshot=None)
  power(on=None)
  temperature_irq() / humidity_irq() / get_irq()
```

### `LPS22`
文件：[LPS22.py](../sensor/LPS22/LPS22.py)｜地址 `LPS22(i2c, addr=0x5D)`

```
LPS22(i2c, addr=0x5D)
  get()                         -> (温度℃, 气压hPa)
  temperature() / pressure() / altitude()
  oneshot_mode() / ONE_SHOT(b)  (内部)
  temperature_irq() / pressure_irq() / get_irq()
```

### `STTS751`
文件：[STTS751.py](../sensor/STTS751/STTS751.py)｜地址 `0x4A`｜常量 `STTS751_RESOLUTION`

```
STTS751(i2c)
  temperature()
  resolution(res=None)          9-12 位
  oneshot_mode() / ONE_SHOT()  / temperature_irq()
```

### `LIS2DW12`
文件：[LIS2DW12.py](../sensor/LIS2DW12/LIS2DW12.py)｜地址 `LIS2DW12(i2c, addr=0x19)`｜常量 `LIS2DW12_SCALE=('2g','4g','8g','16g')`

```
LIS2DW12(i2c, addr=0x19)
  get()                         -> [x, y, z] mg
  x() / y() / z()               单轴 mg
  x_raw() / y_raw() / z_raw() / get_raw()
  scale(dat=None)               '2g' 等
  temperature() / temperature_irq()
  power(on=None) / oneshot_mode()
```

### `LIS2MDL`
文件：[LIS2MDL.py](../sensor/LIS2MDL/LIS2MDL.py)｜地址 `0x1E`

```
LIS2MDL(i2c)
  get()                         -> [x, y, z] µT
  x() / y() / z()               单轴 µT（*3//20）
  x_raw() / y_raw() / z_raw() / get_raw()
  oneshot_mode() / ONE_SHOT()
```

> ⚠️ 源码含非法 `//` 注释，需删除后方可加载。

### `LSM6DSO`
文件：[LSM6DSO.py](../sensor/LSM6DSO/LSM6DSO.py)｜地址 `LSM6DSO(i2c, addr=0x6B)`｜常量 `LSM6DSO_SCALEA`、`LSM6DSO_SCALEG`

```
LSM6DSO(i2c, addr=0x6B)
  ax() / ay() / az()            加速度 mg
  gx() / gy() / gz()            角速度 mdps
  get_a() / get_g() / get()
  ax_raw()..gz_raw()
  scale_a(dat=None) / scale_g(dat=None)
  temperature() / temperature_irq()
  power(on=None)
```

> ⚠️ `get()` 被错误覆盖并调用未定义的 `get_g_raw()`，建议用 `get_a()`/`get_g()`。

### `APDS9930`
文件：[APDS9930.py](../sensor/APDS9930/APDS9930.py)｜地址 `0x39`｜常量 `APDS9930_AGAIN=(1,8,16,120)`、`APDS9930_PGAIN=(1,2,4,8)`

```
APDS9930(i2c)
  AGAIN(gain=None) / PGAIN(gain=None)
  Power(on=True)
  ALS_Enable(on=True) / Proximity_Enable(on=True) / Wait_Enable(on=True)
  getALS()                       lux
  getProximity()
  ATIME(v=None) / getCH0() / getCH1()
```

---

## Misc

### `AT24XX`
文件：[AT24XX.py](../misc/AT24XX/AT24XX.py)｜常量 `AT24CXX_I2C_ADDRESS=80`（0x50）

```
AT24XX(i2c)
  write_byte(addr, dat) / read_byte(addr)
  write_word(addr, dat) / read_word(addr)
  write_dword(addr, dat) / read_dword(addr)
  write_buf(addr, buf) / read_buf(addr, num)
```

### `DS1302`
文件：[DS1302.py](../misc/DS1302/DS1302.py)｜常量 `DS1302_REG_*`

```
DS1302(clk, dio, cs)
  DecToHex(dat) / HexToDec(dat)  (内部)
  write_byte(dat) / read_byte()   (内部)
  getReg(reg) / setReg(reg, dat)  (内部)
  wr(reg, dat)                    (内部)
  start() / stop()
  Year(y=None) Month Month ... Second(s=None)   get/set（不传参=读）
  DateTime(dat=None)             [年,月,日,星期,时,分,秒]
  ram(reg, dat=None)             31 字节 RAM
```

### `DS1307`
文件：[DS1307.py](../misc/DS1307/DS1307.py)｜常量 `DS1307_I2C_ADDRESS=104`（0x68）

```
DS1307(i2c)
  setReg / getReg / DecToHex / HexToDec   (内部)
  start() / stop()
  DateTime(DT=None)
  Year/Month/Day/Weekday/Hour/Minute/Second (get/set)
  ram(reg, dat=None)             56 字节 RAM
```

### `DS3231`
文件：[DS3231.py](../misc/DS3231/DS3231.py)｜常量 `DS3231_I2C_ADDR=0x68`、`PER_DISABLE/PER_MINUTE/PER_HOUR/PER_DAY/PER_WEEKDAY/PER_MONTH`

```
DS3231(i2c)
  DecToHex / HexToDec / setReg / getReg   (内部)
  Year/Month/Day/Weekday/Hour/Minute/Second (get/set)
  Date(dat=None)                [年,月,日]
  Time(dat=None)                [时,分,秒]
  DateTime(dat=None)            [年,月,日,星期,时,分,秒]
  ALARM(day, hour, minute, repeat)
  ClearALARM()
  Temperature()
```

### `irqUART`
文件：[irqUART.py](../misc/irqUART/irqUART.py)

```
irqUART(uart, rx_pin, rx_irq=None, frame_irq=None, CHR_TMO=3, FRAME_TMO=100)
  _RXPIN_IRQ(t)                 引脚中断 (内部)
  _TMRX_IRQ(t)                  定时器中断 (内部)
```

---

## Neopixel

```
neo16x16(pin)                  文件 neo16x16.py
  clear()
  set(n, color='') / setcolor(color)
  show(dat, offset=0, clear=True, color='')

neo16x16_img(pin)              文件 neo16x16_img.py
  clear()
  set(n, color)
  show(dat, pos=0)
```

---

## Keyboard

### `KEYBOARD`
文件：[keyboard.py](../keyboard/mechanical-button/single-button/keyboard.py)

```
KEYBOARD(_btnKey, _tmBtn, _btnDef=1, even_djlong=None, even_lj=None, _pull=None)
  doBtnScan(t)                  定时器回调，自动注册
```

事件回调：`even_djlong(con)`（长按）、`even_lj(con)`（连续点击）。
