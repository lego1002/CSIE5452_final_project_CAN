"""
CAN 排程分析起手程式
=====================
一個檔案同時做三件事:
  (1) 用 Tindell 經典公式算出每個訊息的「最差反應時間 (WCRT) 理論上界」
  (2) 用離散事件模擬，跑出每個訊息的「實測反應時間」
  (3) 比較兩種情境：A=全部 t=0 同時釋放、B=用 offset 錯開
      並畫成對照圖 + 匯流排甘特圖

執行方式（Mac / Linux / Windows 都可）：
    pip install matplotlib
    python can_scheduling.py

整份程式刻意寫成單一匯流排、週期性訊息、固定優先權、非搶占式，
跟你報告設定的範圍一致。要做進階方向（Davis 修正公式、時鐘漂移）
都可以從這個骨架長出來。
"""

import sys
import math
from dataclasses import dataclass, field
from collections import defaultdict

# 修正 Windows 終端機中文輸出
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# 1. 基本參數
# ---------------------------------------------------------------------------
BITRATE = 500_000           # 匯流排速率 500 kbit/s
TAU = 1.0 / BITRATE * 1000  # 一個位元的時間，單位 ms（= 0.002 ms）
T_SIM = 1000.0              # 模擬總時間 (ms)，越長取樣越多、worst case 越容易被觀察到


@dataclass
class Message:
    name: str
    can_id: int            # 數字越小 = 優先權越高
    period: float          # 週期 (ms)
    dlc: int               # 資料長度 (bytes)
    offset: float = 0.0    # 發布相位 offset (ms)，情境 A 全設 0，情境 B 錯開
    C: float = field(init=False)  # 傳輸時間 (ms)，自動算

    def __post_init__(self):
        self.C = frame_tx_time(self.dlc)


def frame_tx_time(n_bytes: int) -> float:
    """
    標準 CAN 2.0A 訊框最差傳輸時間（含最差位元填充 bit-stuffing）。
    公式：bits = 47 (固定位元) + 8n (資料) + floor((34 + 8n - 1)/4) (填充位元)
    """
    fixed = 47
    data_bits = 8 * n_bytes
    stuff_bits = (34 + 8 * n_bytes - 1) // 4
    total_bits = fixed + data_bits + stuff_bits
    return total_bits * TAU


# ---------------------------------------------------------------------------
# 2. WCRT 理論公式 (Tindell / Burns / Wellings)
# ---------------------------------------------------------------------------
def wcrt(messages):
    """回傳 {訊息名稱: 最差反應時間(ms)}。jitter 假設為 0。"""
    result = {}
    for m in messages:
        hp = [k for k in messages if k.can_id < m.can_id]   # 較高優先權
        lp = [k for k in messages if k.can_id > m.can_id]   # 較低優先權
        # 阻塞：最多被一個較低優先權的訊框卡住（非搶占）
        B = max((k.C for k in lp), default=0.0)
        # 迭代解排隊延遲 w
        w = B
        for _ in range(1000):
            interference = sum(math.ceil((w + TAU) / k.period) * k.C for k in hp)
            w_next = B + interference
            if abs(w_next - w) < 1e-9:
                w = w_next
                break
            w = w_next
        result[m.name] = w + m.C   # R = w + C
    return result


# ---------------------------------------------------------------------------
# 3. 離散事件模擬（非搶占、固定優先權）
# ---------------------------------------------------------------------------
def simulate(messages, t_sim=T_SIM):
    """
    回傳 (每個訊息的反應時間清單, 甘特圖區段清單)
    甘特區段格式: (訊息名稱, 開始時間, 結束時間)
    """
    # 產生所有訊框的釋放事件
    frames = []  # 每個元素: [release, can_id, C, name, sent?]
    for m in messages:
        t = m.offset
        while t < t_sim:
            frames.append([t, m.can_id, m.C, m.name, False])
            t += m.period

    responses = defaultdict(list)
    gantt = []
    clock = 0.0
    remaining = len(frames)

    while remaining > 0:
        # 找出此刻已釋放、還沒傳的訊框
        ready = [f for f in frames if not f[4] and f[0] <= clock]
        if not ready:
            # 沒有人就緒 → 時間快轉到下一個釋放點
            future = [f[0] for f in frames if not f[4]]
            if not future:
                break
            clock = min(future)
            continue
        # 仲裁：挑優先權最高（ID 最小）的
        f = min(ready, key=lambda x: x[1])
        start = clock
        finish = start + f[2]
        responses[f[3]].append(finish - f[0])  # 反應時間 = 完成 - 釋放
        gantt.append((f[3], start, finish))
        f[4] = True
        remaining -= 1
        clock = finish

    return responses, gantt


# ---------------------------------------------------------------------------
# 4. 你的訊息集合（可自由修改）
# ---------------------------------------------------------------------------
def build_messages(offsets):
    """offsets: dict {can_id: offset_ms}"""
    spec = [
        # name,            id,     period, dlc
        ("Engine_Status",  0x100,  10,     8),
        ("Brake_Data",     0x110,  10,     8),
        ("Wheel_Speed",    0x120,  10,     8),
        ("Transmission",   0x300,  20,     8),
        ("Body_Control",   0x400,  50,     8),
        ("Diagnostics",    0x500,  100,    8),
    ]
    return [Message(n, i, p, d, offset=offsets.get(i, 0.0)) for n, i, p, d in spec]


# 情境 A：全部 t=0 同時釋放
SCEN_A = build_messages({})
# 情境 B：把三個 10ms 訊息錯開
SCEN_B = build_messages({0x100: 0.0, 0x110: 3.0, 0x120: 6.0})


# ---------------------------------------------------------------------------
# 5. 跑分析並輸出
# ---------------------------------------------------------------------------
def main():
    bound = wcrt(SCEN_A)                 # 理論上界（與 offset 無關，看的是最差對齊）
    resp_a, gantt_a = simulate(SCEN_A)
    resp_b, gantt_b = simulate(SCEN_B)

    names = [m.name for m in SCEN_A]

    # --- 文字表格 ---
    print(f"{'Message':<16}{'C(ms)':>8}{'WCRT界':>10}{'A實測max':>11}{'B實測max':>11}")
    print("-" * 56)
    for m in SCEN_A:
        a = max(resp_a[m.name])
        b = max(resp_b[m.name])
        print(f"{m.name:<16}{m.C:>8.3f}{bound[m.name]:>10.3f}{a:>11.3f}{b:>11.3f}")

    # --- 圖表 ---
    try:
        import matplotlib.pyplot as plt
        import numpy as np

        # 圖一：每個訊息的反應時間對照（理論界 vs A vs B）
        x = np.arange(len(names))
        w = 0.27
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(x - w, [bound[n] for n in names], w, label="WCRT bound (theory)")
        ax.bar(x,     [max(resp_a[n]) for n in names], w, label="Scenario A (all t=0)")
        ax.bar(x + w, [max(resp_b[n]) for n in names], w, label="Scenario B (offset)")
        ax.set_ylabel("Response time (ms)")
        ax.set_title("CAN message response time: theory vs simulation")
        ax.set_xticks(x); ax.set_xticklabels(names, rotation=20, ha="right")
        ax.legend()
        fig.tight_layout()
        fig.savefig("response_time_comparison.png", dpi=130)
        print("\n已存圖：response_time_comparison.png")

        # 圖二：匯流排甘特圖（前 30ms），看 offset 怎麼把訊框錯開
        fig2, axes = plt.subplots(2, 1, figsize=(11, 5), sharex=True)
        for ax, gantt, title in [(axes[0], gantt_a, "Scenario A: all released at t=0"),
                                 (axes[1], gantt_b, "Scenario B: offsets applied")]:
            row = {n: i for i, n in enumerate(names)}
            for nm, s, e in gantt:
                if s > 30:
                    continue
                ax.barh(row[nm], e - s, left=s, height=0.6)
            ax.set_yticks(range(len(names))); ax.set_yticklabels(names)
            ax.set_title(title); ax.set_xlim(0, 30)
        axes[1].set_xlabel("time (ms)")
        fig2.tight_layout()
        fig2.savefig("bus_gantt.png", dpi=130)
        print("已存圖：bus_gantt.png")
        plt.show()
    except ImportError:
        print("\n（要看圖請先 pip install matplotlib）")


if __name__ == "__main__":
    main()