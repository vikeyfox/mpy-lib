"""示例技能：前进 → 停止 → 原地转 → 停止，循环执行。

下发：
    python3 tools/pkgctl.py push examples/skill_demo --transport ble --name bot-c3-01
"""

_ctx = None
_t = 0
_phase = -1

PLAN_MS = (1200, 600, 1200, 600)


def setup(ctx):
    global _ctx, _t, _phase
    _ctx = ctx
    _t = 0
    _phase = -1
    ctx.emit("skill_start", {"name": "demo", "speed": ctx.param("speed", 60)})


def step(dt_ms):
    global _t, _phase
    _t += dt_ms
    if _t < PLAN_MS[0]:
        phase = 0
    elif _t < sum(PLAN_MS[:2]):
        phase = 1
    elif _t < sum(PLAN_MS[:3]):
        phase = 2
    else:
        phase = 3

    if phase != _phase:
        _phase = phase
        if phase == 0:
            _ctx.drive(_ctx.param("speed", 60), 0)
        elif phase == 2:
            _ctx.drive(0, _ctx.param("turn", 40))
        else:
            _ctx.drive(0, 0)
        _ctx.emit("phase", {"i": phase})

    if _t >= sum(PLAN_MS):
        _t = 0
        _phase = -1


def teardown():
    if _ctx is not None:
        _ctx.stop()


def snapshot():
    return {"t": _t, "phase": _phase}


def restore(state):
    global _t, _phase
    _t = state.get("t", 0)
    _phase = state.get("phase", -1)
