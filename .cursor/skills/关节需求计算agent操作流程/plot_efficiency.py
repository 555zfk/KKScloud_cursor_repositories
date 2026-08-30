"""
plot_efficiency.py
==================
绘制一条或多条电机扭矩-效率曲线（smoothing spline 平滑），导出 PNG 与 CSV。
每条曲线对应一种电机/关节效率配置，由用户提供原始数据点。

【使用前修改 ── USER CONFIG 区域】
"""

import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
from scipy.interpolate import make_smoothing_spline
from pathlib import Path

matplotlib.rcParams['font.family'] = 'Microsoft YaHei'
matplotlib.rcParams['axes.unicode_minus'] = False

# ════════════════════════════════════════════════════════════════════
# USER CONFIG
# ════════════════════════════════════════════════════════════════════

OUT_DIR = Path(r"<输出目录>") / "参考效率曲线"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 定义一条或多条效率曲线
# 格式：{ "曲线标签": { "torque": [...], "efficiency_pct": [...], "lam": 平滑系数, "color": 颜色 } }
# efficiency_pct 单位为 %（0~100），程序内部自动转换为小数
EFFICIENCY_CURVES = {
    "大扭矩关节": {
        "torque": [
            0.5,  1.4,  2.3,  3.5,  4.6,  5.6,  6.5,  7.4,  8.3,  9.7,
           10.6, 11.8, 12.5, 13.6, 14.5, 15.5, 16.3, 17.1, 18.7, 19.2,
           20.1, 21.6, 22.3, 23.0, 24.1, 25.1, 26.8, 27.5, 28.1, 29.4,
           30.0, 32.6, 33.9, 34.5, 35.9
        ],
        "efficiency_pct": [
            30, 55, 65, 64, 71, 75, 74, 74, 70, 77,
            74, 71, 70, 72, 72, 66, 66, 66, 66, 65,
            63, 61, 59, 58, 55, 51, 43, 40, 36, 28,
            20, 18, 14, 10,  4
        ],
        "lam":   1.2,
        "color": "#2563EB",
    },
    "小扭矩关节": {
        "torque": [
            1.6,  1.9,  2.2,  2.4,  2.7,  3.0,  3.3,  3.5,  3.7,  3.9,
            4.2,  4.4,  4.8,  5.0,  5.3,  5.7,  6.0,  6.3,  6.5,  6.8,
            7.1,  7.5,  7.7,  7.9,  8.3,  8.5,  8.7,  9.1,  9.3,  9.6,
           10.0, 10.3, 10.5, 11.2, 11.3
        ],
        "efficiency_pct": [
            48, 50, 53, 54, 59, 53, 54, 58, 52, 60,
            54, 53, 54, 49, 57, 48, 52, 53, 52, 45,
            45, 37, 40, 33, 33, 37, 28, 24, 22, 15,
            15, 13,  9,  6,  3
        ],
        "lam":   0.8,
        "color": "#059669",
    },
    # 如需添加更多曲线，复制上面一段并修改数据即可
}

# ════════════════════════════════════════════════════════════════════

fig, ax = plt.subplots(figsize=(8, 5))

for label, cfg in EFFICIENCY_CURVES.items():
    raw_t   = np.array(cfg["torque"])
    raw_e   = np.array(cfg["efficiency_pct"]) / 100.0
    spline  = make_smoothing_spline(raw_t, raw_e, lam=cfg["lam"])
    t_dense = np.linspace(raw_t.min(), raw_t.max(), 400)
    e_dense = np.clip(spline(t_dense), 0, 1)

    ax.scatter(raw_t, raw_e * 100, s=20, color=cfg["color"], alpha=0.65, zorder=5)
    ax.plot(t_dense, e_dense * 100, color=cfg["color"], lw=2, label=label)

    pk = np.argmax(e_dense)
    ax.annotate(f"峰值 {e_dense[pk]*100:.1f}% @ {t_dense[pk]:.1f} Nm",
                xy=(t_dense[pk], e_dense[pk]*100),
                xytext=(t_dense[pk] + (raw_t.max()-raw_t.min())*0.05,
                        e_dense[pk]*100 - 7),
                arrowprops=dict(arrowstyle="->", color="gray"), fontsize=8)

    # 导出 CSV
    pd.DataFrame({"torque_Nm": raw_t, "efficiency": raw_e}).to_csv(
        OUT_DIR / f"{label}_效率_原始.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame({"torque_Nm": np.round(t_dense, 4),
                  "efficiency": np.round(e_dense, 6)}).to_csv(
        OUT_DIR / f"{label}_效率_平滑.csv", index=False, encoding="utf-8-sig")
    print(f"[{label}] 峰值效率 {e_dense.max()*100:.1f}% @ {t_dense[np.argmax(e_dense)]:.2f} Nm")

ax.set_xlabel("扭矩 (Nm)", fontsize=10)
ax.set_ylabel("效率 (%)", fontsize=10)
ax.set_title("关节参考效率曲线", fontsize=11)
ax.set_ylim(0, 105)
ax.legend(fontsize=9)
ax.spines[["top", "right"]].set_visible(False)
ax.grid(True, linestyle="--", linewidth=0.4, alpha=0.6)
fig.tight_layout()
fig.savefig(OUT_DIR / "参考效率曲线.png", dpi=150, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"\n图表已保存 → {OUT_DIR}")
