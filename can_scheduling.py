"""
CAN 排程分析程式  ——  台大智慧型汽車導論 期末專題
=====================================================
架構（影片可照這四部分介紹）：
  Part 1  MAC 層訊框模型 frame_tx_time()  ── 對應 LEC-02 p.12~15（訊框格式、bit stuffing）
  Part 2  Tindell 原始 WCRT 公式 wcrt_tindell() ── 對應 LEC-02 p.27~29
  Part 3  Davis 修正 WCRT 公式 wcrt_davis()      ── 對應 LEC-02 p.30,32,36（busy period、多實例）
  Part 4  離散事件模擬 simulate()                ── 用模擬交叉驗證公式
三組資料：課堂例題（驗證）、專題例題（offset 實驗）、反駁例題（Tindell vs Davis）。

執行： pip install matplotlib ; python can_scheduling.py
"""

import sys, math, time, json, os
from dataclasses import dataclass, field
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# --- 解決中文字型方框：自動找系統可用的中文字型 ---
import matplotlib
import matplotlib.font_manager as fm
def setup_cjk_font():
    candidates = ["Microsoft JhengHei", "Microsoft YaHei", "PingFang TC",
                  "Heiti TC", "Arial Unicode MS", "Noto Sans CJK TC",
                  "Noto Sans CJK JP", "Noto Sans CJK SC", "WenQuanYi Zen Hei",
                  "SimHei", "STHeiti"]
    available = {f.name for f in fm.fontManager.ttflist}
    for c in candidates:
        if c in available:
            matplotlib.rcParams["font.sans-serif"] = [c]
            matplotlib.rcParams["axes.unicode_minus"] = False  # 修正負號變方框
            return c
    return None
_FONT = setup_cjk_font()

# ---------------------------------------------------------------------------
# Part 0  基本參數
# ---------------------------------------------------------------------------
BITRATE = 500_000             # 匯流排速率 500 kbit/s
TAU = 1.0 / BITRATE * 1000    # 一個位元的時間(ms)。同時當作公式裡的邊界 ε（LEC-02 p.30 的 τ）
T_SIM = 1000.0

# ---------------------------------------------------------------------------
# Part 1  MAC 層：CAN 訊框最差傳輸時間（含 bit stuffing）
#         bits = 47(固定) + 8n(資料) + floor((34+8n-1)/4)(填充)
#         8 bytes → 135 bits，與 LEC-02 p.15 完全一致
# ---------------------------------------------------------------------------
def frame_tx_time(n_bytes: int) -> float:
    fixed = 47
    data_bits = 8 * n_bytes
    stuff_bits = (34 + 8 * n_bytes - 1) // 4
    return (fixed + data_bits + stuff_bits) * TAU


@dataclass
class Message:
    name: str
    can_id: int            # 數字越小 = 優先權越高
    period: float          # 週期 T (ms)
    dlc: int = 0           # 資料長度 → 用 frame_tx_time 算 C（真實 MAC 層）
    C: float = None        # 若直接給定（課堂抽象例題），就用這個，不從 dlc 算
    offset: float = 0.0

    def __post_init__(self):
        if self.C is None:
            self.C = frame_tx_time(self.dlc)


# ---------------------------------------------------------------------------
# Part 2  Tindell 原始公式（只看第一個實例 q=0；只在 R<=T 時有效）
#         Q = B + Σ ceil((Q+τ)/Tj)·Cj   ;   R = Q + C   （LEC-02 p.27）
#         回傳 {name: (R, schedulable)}  ── schedulable=False 表示 R>T，原始分析失效
# ---------------------------------------------------------------------------
def wcrt_tindell(messages):
    out = {}
    for m in messages:
        hp = [k for k in messages if k.can_id < m.can_id]
        lp = [k for k in messages if k.can_id > m.can_id]
        B = max((k.C for k in lp), default=0.0)   # 阻塞：最長的較低優先權訊框
        Q, schedulable = B, True
        for _ in range(10000):
            rhs = B + sum(math.ceil((Q + TAU) / k.period) * k.C for k in hp)
            if rhs + m.C > m.period:               # LEC-02 p.29：R>T → 限制違反
                schedulable = False
                Q = rhs
                break
            if abs(rhs - Q) < 1e-9:
                break
            Q = rhs
        out[m.name] = (Q + m.C, schedulable)
    return out


# ---------------------------------------------------------------------------
# Part 3  Davis 修正公式（busy period 內逐一檢查所有實例，取最大）
#         移除「R<=T」限制；當 R>T 時，較晚的實例可能才是最差 → 原始公式會低估
# ---------------------------------------------------------------------------
def wcrt_davis(messages, return_detail=False):
    out, detail = {}, {}
    for m in messages:
        hp = [k for k in messages if k.can_id < m.can_id]
        lp = [k for k in messages if k.can_id > m.can_id]
        B = max((k.C for k in lp), default=0.0)
        # (1) 求 priority level-i busy period 長度 L（含 m 自己與所有較高優先權）
        L = m.C
        for _ in range(100000):
            rhs = (B + sum(math.ceil(L / k.period) * k.C for k in hp)
                   + math.ceil(L / m.period) * m.C)
            if abs(rhs - L) < 1e-9:
                break
            L = rhs
        n_inst = max(1, math.ceil(L / m.period))   # busy period 內 m 的實例數
        # (2) 對每個實例 q 算反應時間
        Rs = []
        for q in range(n_inst):
            w = B + q * m.C
            for _ in range(100000):
                rhs = B + q * m.C + sum(math.ceil((w + TAU) / k.period) * k.C for k in hp)
                if abs(rhs - w) < 1e-9:
                    break
                w = rhs
            Rs.append(w - q * m.period + m.C)
        out[m.name] = max(Rs)
        detail[m.name] = Rs
    return (out, detail) if return_detail else out


# ---------------------------------------------------------------------------
# Part 4  離散事件模擬（非搶占、固定優先權）
# ---------------------------------------------------------------------------
def simulate(messages, t_sim=T_SIM):
    frames = []   # [release, id, C, name, sent?]
    for m in messages:
        t = m.offset
        while t < t_sim:
            frames.append([t, m.can_id, m.C, m.name, False])
            t += m.period
    responses, gantt = defaultdict(list), []
    clock, remaining = 0.0, len(frames)
    while remaining > 0:
        ready = [f for f in frames if not f[4] and f[0] <= clock]
        if not ready:
            clock = min(f[0] for f in frames if not f[4]); continue
        f = min(ready, key=lambda x: x[1])         # 仲裁：挑 ID 最小
        start, finish = clock, clock + f[2]
        responses[f[3]].append(finish - f[0])
        gantt.append((f[3], f[0], start, finish))  # (name, release, start, finish)
        f[4], remaining, clock = True, remaining - 1, finish
    return responses, gantt


# ---------------------------------------------------------------------------
# Part 5  三組資料
# ---------------------------------------------------------------------------
# (A) 課堂 Example #5（LEC-02 p.24~29）—— 直接給 C，用來驗證公式
COURSE = [
    Message("u0", 0, 50,  C=10),
    Message("u1", 1, 200, C=40),
    Message("u2", 2, 200, C=10),
    Message("u3", 3, 200, C=40),
]   # 課堂手算答案：R0=50, R1=100, R2=120

# (B) 專題 offset 例題（真實 CAN 訊框，C 由 frame_tx_time 算）
def build_project(offsets):
    spec = [("Engine", 0x100, 1, 4), ("Wheel", 0x200, 1, 4),
            ("Brake", 0x300, 2, 8), ("Body", 0x400, 2, 8)]
    return [Message(n, i, p, dlc=d, offset=offsets.get(i, 0.0)) for n, i, p, d in spec]
SCEN_A = build_project({})                                            # 全部 t=0
SCEN_B = build_project({0x100: 0, 0x300: 0.25, 0x200: 0.5, 0x400: 0.75})  # 錯開

# (C) 反駁例題（util=0.895）—— 讓 Davis 抓到「第二個實例才是最差」
REFUTE = [
    Message("High", 0, 7,  C=3),
    Message("Mid",  1, 10, C=3),
    Message("Low",  2, 6,  C=1),
]

RESULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "result")


# ---------------------------------------------------------------------------
# Part 6  主流程
# ---------------------------------------------------------------------------
def plot_verification(save_dir, ts):
    """驗證圖：上半描述訊息特徵（公式的輸入），下半三方對照結果。"""
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import numpy as np
    t = wcrt_tindell(COURSE)
    formula = {m.name: t[m.name][0] for m in COURSE}
    rsim, _ = simulate(COURSE, 4000)
    sim = {m.name: max(rsim[m.name]) for m in COURSE}
    lecture = {"u0": 50, "u1": 100, "u2": 120, "u3": None}
    role = {"u0": "最高優先權，不被任何訊息阻擋",
            "u1": "傳輸時間最長之一（C=40）",
            "u2": "← 被驗證的目標訊息",
            "u3": "最低優先權，是最大的阻塞來源"}

    names = ["u0", "u1", "u2", "u3"]
    fig = plt.figure(figsize=(12, 9))
    gs = gridspec.GridSpec(2, 1, height_ratios=[1, 2.1], hspace=0.28)

    # 上：訊息特徵表（描述每個訊息「是什麼」）
    axt = fig.add_subplot(gs[0]); axt.axis("off")
    axt.set_title("訊息特徵：這就是公式的輸入（取自課堂 Example #5）", fontsize=13, fontweight="bold")
    cols = ["訊息", "優先權", "傳輸時間 C (ms)", "週期 T (ms)", "特性說明"]
    cells = [[m.name, f"P={m.can_id}（{'最高' if m.can_id==0 else '最低' if m.can_id==3 else '中'}）",
              f"{m.C:.0f}", f"{m.period:.0f}", role[m.name]] for m in COURSE]
    tbl = axt.table(cellText=cells, colLabels=cols, cellLoc="center", loc="center",
                    colWidths=[0.08, 0.16, 0.18, 0.15, 0.43])
    tbl.auto_set_font_size(False); tbl.set_fontsize(10.5); tbl.scale(1, 1.7)
    for j in range(len(cols)):
        tbl[0, j].set_facecolor("#34495e"); tbl[0, j].get_text().set_color("white")
    for i in range(1, len(COURSE) + 1):
        tbl[i, 0].set_facecolor("#ecf0f1")

    # 下：三方對照結果
    ax = fig.add_subplot(gs[1])
    x, w = np.arange(len(names)), 0.27
    lec_vals = [lecture[n] if lecture[n] is not None else np.nan for n in names]
    ax.bar(x - w, lec_vals, w, label="課堂手算 (LEC-02 p.28)", color="#c0392b", alpha=0.85)
    ax.bar(x,     [formula[n] for n in names], w, label="我的公式 (Tindell)", color="#2980b9", alpha=0.85)
    ax.bar(x + w, [sim[n] for n in names], w, label="我的模擬 (觀測最大)", color="#27ae60", alpha=0.5, hatch="//")
    for i, n in enumerate(names):
        if lecture[n] is not None:
            ax.text(x[i] - w, lec_vals[i] + 1.5, f"{lec_vals[i]:.0f}", ha="center", fontsize=8)
            if abs(lecture[n] - formula[n]) < 1e-6:
                ax.text(x[i] - w / 2, max(formula[n], lec_vals[i]) + 7, "✓ 相符",
                        ha="center", fontsize=10, color="#c0392b", fontweight="bold")
        ax.text(x[i], formula[n] + 1.5, f"{formula[n]:.0f}", ha="center", fontsize=8)
        ax.text(x[i] + w, sim[n] + 1.5, f"{sim[n]:.0f}", ha="center", fontsize=8)
    ax.text(x[3], formula["u3"] + 7, "(課堂練習題)", ha="center", fontsize=8, color="gray")
    ax.set_ylabel("最差反應時間 R (ms)"); ax.set_xticks(x); ax.set_xticklabels(names)
    ax.set_title("驗證結果：我的公式 = 課堂手算（證明算對）｜ 模擬 ≤ 公式（上界安全）")
    ax.legend(loc="upper left"); ax.grid(axis="y", ls="--", alpha=0.4); ax.set_ylim(0, 150)

    path = os.path.join(save_dir, f"verification_{ts}.png")
    fig.savefig(path, dpi=140, bbox_inches="tight")
    return path


def main():
    # === (1) 用課堂例題驗證公式 ===
    print("=" * 60)
    print("(1) 驗證：課堂 Example #5（LEC-02 p.24~29）")
    print("-" * 60)
    t = wcrt_tindell(COURSE)
    print(f"{'msg':<6}{'Tindell R':>12}{'課堂手算':>12}")
    ans = {"u0": 50, "u1": 100, "u2": 120, "u3": "(練習)"}
    for m in COURSE:
        print(f"{m.name:<6}{t[m.name][0]:>12.1f}{str(ans[m.name]):>12}")

    # === (2) Tindell vs Davis：反駁例題 ===
    print("\n" + "=" * 60)
    print("(2) Tindell vs Davis（反駁例題 util=0.895）")
    print("-" * 60)
    t2 = wcrt_tindell(REFUTE)
    d2, detail = wcrt_davis(REFUTE, return_detail=True)
    for m in REFUTE:
        R_t, ok = t2[m.name]
        flag = "" if ok else "  ← R>T，原始分析失效/低估"
        print(f"{m.name:<6} Tindell={R_t:>5.1f}{flag}")
    print(f"\n關鍵：最低優先權 'Low'")
    print(f"  原始 Tindell（只看第一個實例）   = {t2['Low'][0]:.1f}")
    print(f"  Davis busy period 各實例 R(q)    = {[round(x,1) for x in detail['Low']]}")
    print(f"  Davis 取最大（真正的 WCRT）       = {d2['Low']:.1f}")
    print(f"  → 第 {detail['Low'].index(max(detail['Low']))} 個實例才是最差，原始公式低估了！")

    # === (3) offset 實驗 + 畫圖 ===
    bound = {m.name: wcrt_tindell(SCEN_A)[m.name][0] for m in SCEN_A}
    resp_a, gantt_a = simulate(SCEN_A)
    resp_b, gantt_b = simulate(SCEN_B)
    names = [m.name for m in SCEN_A]
    print("\n" + "=" * 60)
    print("(3) offset 實驗：情境A(t=0) vs 情境B(錯開)")
    print("-" * 60)
    print(f"{'Message':<10}{'C':>7}{'WCRT界':>9}{'A_max':>9}{'B_max':>9}")
    for m in SCEN_A:
        print(f"{m.name:<10}{m.C:>7.3f}{bound[m.name]:>9.3f}"
              f"{max(resp_a[m.name]):>9.3f}{max(resp_b[m.name]):>9.3f}")

    try:
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
        import matplotlib.patches as mpatches
        import numpy as np
        os.makedirs(RESULT_DIR, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        cmap = plt.get_cmap("tab10")
        col = {n: cmap(i) for i, n in enumerate(names)}

        fig = plt.figure(figsize=(13, 16))
        fig.suptitle(f"CAN 排程分析  [{ts}]" if _FONT else f"CAN Scheduling  [{ts}]",
                     fontsize=14, y=0.997)
        gs = gridspec.GridSpec(3, 1, figure=fig, hspace=0.45, height_ratios=[1, 1.2, 1.2])
        ax1, axA, axB = fig.add_subplot(gs[0]), fig.add_subplot(gs[1]), fig.add_subplot(gs[2])

        # 子圖①：反應時間對照
        x, w = np.arange(len(names)), 0.27
        ax1.bar(x - w, [bound[n] for n in names], w, label="WCRT 理論上界", color="dimgray", alpha=0.55)
        ax1.bar(x,     [max(resp_a[n]) for n in names], w, label="情境A 實測 (t=0)",
                color=[col[n] for n in names], alpha=0.9)
        ax1.bar(x + w, [max(resp_b[n]) for n in names], w, label="情境B 實測 (offset)",
                color=[col[n] for n in names], alpha=0.45, hatch="//")
        ax1.set_ylabel("反應時間 (ms)"); ax1.set_xticks(x); ax1.set_xticklabels(names)
        ax1.set_title("① 反應時間：理論上界 vs 模擬")
        ax1.legend(loc="upper left"); ax1.grid(axis="y", ls="--", alpha=0.4)

        # 子圖②③：甘特圖。兩張用「同一個時間軸」(視窗=2×最長週期)，可看到每個訊息兩個週期
        # 淺色=等待排隊、深色=傳輸中，兩段總長 = 反應時間 R（每個實例上方標數字）
        window = 2 * max(m.period for m in SCEN_A)
        def gantt(ax, g, title):
            row = {n: i for i, n in enumerate(names)}
            for nm, rel, s, e in g:
                if rel >= window: continue
                if s - rel > 1e-6:
                    ax.barh(row[nm], s - rel, left=rel, height=0.42, color=col[nm], alpha=0.18)
                ax.barh(row[nm], e - s, left=s, height=0.42, color=col[nm], alpha=0.95,
                        edgecolor="black", linewidth=0.4)
                ax.text(rel, row[nm] + 0.27, f"{e - rel:.2f}", fontsize=7,
                        color=col[nm], ha="left", va="bottom", fontweight="bold")
            ax.set_yticks(range(len(names))); ax.set_yticklabels(names)
            ax.set_ylim(-0.55, len(names) - 0.05); ax.set_xlim(0, window)
            ax.set_title(title); ax.set_xlabel("時間 (ms)"); ax.grid(axis="x", ls=":", alpha=0.4)
            ax.legend(handles=[mpatches.Patch(facecolor="gray", alpha=0.18, label="等待排隊"),
                               mpatches.Patch(facecolor="gray", alpha=0.95, label="傳輸中"),
                               mpatches.Patch(facecolor="white", edgecolor="white",
                                              label="數字 = 反應時間 R(ms)")],
                      loc="upper right", fontsize=8)
        gantt(axA, gantt_a, "② 甘特圖 情境A：全部 t=0 同時釋放")
        gantt(axB, gantt_b, "③ 甘特圖 情境B：offset 錯開")

        path = os.path.join(RESULT_DIR, f"charts_{ts}.png")
        fig.savefig(path, dpi=130, bbox_inches="tight")
        vpath = plot_verification(RESULT_DIR, ts)
        print(f"\n已存圖：{path}")
        print(f"已存驗證圖：{vpath}   （使用字型：{_FONT or '英文 fallback'}）")
        plt.show()
    except ImportError:
        print("\n（要看圖請先 pip install matplotlib）")


if __name__ == "__main__":
    main()