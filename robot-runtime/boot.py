# boot.py
# 只做最小初始化；业务与异常兜底放在 main.py，失败时保留 REPL。
import gc

gc.collect()
