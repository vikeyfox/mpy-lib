# 机械按键模块（Keyboard）

目录：[keyboard/mechanical-button/single-button/](../keyboard/mechanical-button/single-button)
**驱动**：`KEYBOARD`｜[keyboard.py](../keyboard/mechanical-button/single-button/keyboard.py)｜[README.md](../keyboard/mechanical-button/single-button/README.md)
**作者/许可**：Robin Chen，MIT。

---

## 功能概述

识别**单个机械按键**的多种动作并在定时器回调中触发用户事件：

- **长按（定时式）**：保持按下达到设定时长后触发**一次**（常用于复位）。
- **长按（计时/计次式）**：保持按下期间按固定间隔持续触发（可用于自动累加/调节）。
- **连续点击**：在设定间隔内反复按下松开，回调返回点击次数（1 次=单击）。

实现方式：`machine.Timer` 周期性扫描 GPIO 电平，通过计数器识别按下/弹起状态。

---

## 类 `KEYBOARD`

**构造**：

```python
KEYBOARD(_btnKey, _tmBtn, _btnDef=1, even_djlong=None, even_lj=None, _pull=None)
```

| 参数 | 取值 | 默认 | 说明 |
| --- | --- | --- | --- |
| `_btnKey` | `machine.Pin` 对象 | — | 按键所在 IO 引脚 |
| `_tmBtn` | `machine.Timer` 对象 | — | 用于扫描按键的定时器（驱动内部 `init(freq=1000/clock)` 并注册回调） |
| `_btnDef` | `0` 或 `1` | `1` | 按键初始电平：`1` 表示高电平、低电平闭合 |
| `even_djlong` | `None` 或 函数 | `None` | 长按事件回调（`None` 表示不启用） |
| `even_lj` | `None` 或 函数 | `None` | 连续点击事件回调（`None` 表示不启用） |
| `_pull` | `"UP"`/`"DOWN"`/`None` | `None` | 触发方式：上拉/下拉/无 |

**内部关键属性**：`clock=10`（定时器扫描周期，ms）、`staLon`（1=长按计时、0=长按计次）、`tLon=3000`（长按延时 ms）、`TIME_CONT_CLICKS=50`（连击时间间隔）。

**唯一公开方法**：

| 方法 | 说明 |
| --- | --- |
| `doBtnScan(t)` | 定时器回调（周期扫描按键、判定动作、派发事件）。由 `_tmBtn.callback()` 自动注册 |

**事件回调签名**：

- `even_djlong(con)` — 长按事件。`staLon=1`（计时模式）时无参调用；`staLon=0`（计次模式）时携带 `con`（连续有效计时次数，实际时长 ≈ `con × 扫描周期`）。
- `even_lj(con)` — 连续点击事件，`con` 为点击次数（`1` 即单击）。

> ⚠️ 事件回调内**不要执行耗时程序**，否则会触发定时器错误（回调运行于中断上下文）。计时长按与定时长按二选一（由 `staLon` 决定，构造后若需切换要自行设置）。

---

## 用法示例

```python
from keyboard import KEYBOARD
from machine import Pin, Timer

p = Pin('B3')           # 按键引脚
s = Timer(1)            # 扫描定时器

def evn_long(con):      # 长按事件（计次模式）
    print("长按保持 ", (con * 10) / 1000, " 秒")

def evn_con(con):       # 连续点击事件
    print("连续点击 ", con, " 次")

sw = KEYBOARD(p, s, 0, evn_long, evn_con, "UP")
```

> 上例中 `_btnDef=0`（低电平闭合）、`_pull="UP"`（上拉），与多数开发板的按键接法一致。
