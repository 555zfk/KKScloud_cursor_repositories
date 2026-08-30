"""
plot_total_power.py
===================
计算全身所有关节（左右两侧）合计输入功率时间曲线，按工况分别输出。
生成堆叠面积图 + 合计折线图，并打印 RMS / 峰值功率。

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

OUT_DIR = Path(r"<输出目录>") / "全身功率"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 工况 CSV
CSV_FILES = {
    "工况1": r"<CSV路径1>",
    "工况2": r"<CSV路径2>",
    "工况3": r"<CSV路径3>",
}

# 全部关节对：(显示名, 左侧列名后缀, 右侧列名后缀)
JOINT_PAIRS = [
    ("hip_pitch",      "left_hip_pitch_joint",     "right_hip_pitch_joint"),
    ("hip_roll",       "left_hip_roll_joint",       "right_hip_roll_joint"),
    ("hip_yaw",        "left_hip_yaw_joint",        "right_hip_yaw_joint"),
    ("knee_pitch",     "left_knee_joint",           "right_knee_joint"),
    ("ankle_pitch",    "left_ankle_pitch_joint",    "right_ankle_pitch_joint"),
    ("ankle_roll",     "left_ankle_roll_joint",     "right_ankle_roll_joint"),
    ("shoulder_pitch", "left_shoulder_pitch_joint", "right_shoulder_pitch_joint"),
    ("shoulder_roll",  "left_shoulder_roll_joint",  "right_shoulder_roll_joint"),
]

# 各关节扭矩缩放系数（默认 1.0）
TORQUE_SCALE = {
    "ankle_pitch": 1.0,   # 如有减速比折算，在此修改
}

# ── 效率配置 ─────────────────────────────────────────────────────────────────
# 定义多条效率曲线
EFFICIENCY_DEFS = {
    "大扭矩关节": {
        "torque": [
            0.5,  1.4,  2.3,  3.5,  4.6,  5.6,  6.5,  7.4,  8.3,  9.7,
           10.6, 11.8, 12.5, 13.6, 14.5, 15.5, 16.3, 17.1, 18.7, 19.2,
           20.1, 21.6, 22.3, 23.0, 24.1, 25.1, 26.8, 27.5, 28.1, 29.4,
           30.0, 32.6, 33.9, 34.5, 35.9
        ],
        "eff": [
            30, 55, 65, 64, 71, 75, 74, 74, 70, 77,
            74, 71, 70, 72, 72, 66, 66, 66, 66, 65,
            63, 61, 59, 58, 55, 51, 43, 40, 36, 28,
            20, 18, 14, 10,  4
        ],
        "lam": 1.2, "eff_min": 0.03, "stall": 42.0,
    },
    "小扭矩关节": {
        "torque": [
            1.6,  1.9,  2.2,  2.4,  2.7,  3.0,  3.3,  3.5,  3.7,  3.9,
            4.2,  4.4,  4.8,  5.0,  5.3,  5.7,  6.0,  6.3,  6.5,  6.8,
            7.1,  7.5,  7.7,  7.9,  8.3,  8.5,  8.7,  9.1,  9.3,  9.6,
           10.0, 10.3, 10.5, 11.2, 11.3
        ],
        "eff": [
            48, 50, 53, 54, 59, 53, 54, 58, 52, 60,
            54, 53, 54, 49, 57, 48, 52, 53, 52, 45,
            45, 37, 40, 33, 33, 37, 28, 24, 22, 15,
            15, 13,  9,  6,  3
        ],
        "lam": 0.8, "eff_min": 0.25, "stall": 13.5,
    },
}

# 各关节使用的效率曲线标签（必须与 EFFICIENCY_DEFS 的键对应）
JOINT_EFF_MAP = {
    "hip_pitch":      "大扭矩关节",
    "hip_roll":       "大扭矩关节",
    "hip_yaw":        "大扭矩关节",
    "knee_pitch":     "大扭矩关节",
    "shoulder_pitch": "大扭矩关节",
    "shoulder_roll":  "大扭矩关节",
    "ankle_pitch":    "小扭矩关节",
    "ankle_roll":     "小扭矩关节",
    # 未列出的关节默认使用第一条曲线
}

# ════════════════════════════════════════════════════════════════════

START_T = 0.5
SAMPLE  = 0.02
COLORS  = ["#1D4ED8","#DC2626","#059669","#D97706",
           "#7C3AED","#0891B2","#BE185D","#65A30D"]


def build_eff_fn(cfg):
    t_arr = np.array(cfg["torque"])
    e_arr = np.array(cfg["eff"]) / 100.0
    sp    = make_smoothing_spline(t_arr, e_arr, lam=cfg["lam"])
    emin  = cfg["eff_min"]
    stall = cfg["stall"]
    emax  = float(np.clip(sp([t_arr.max()]), emin, 1.0)[0])

    def fn(tau):
        eff = np.empty_like(tau, dtype=float)
        ok  = (tau >= t_arr.min()) & (tau <= t_arr.max())
        lo  = tau < t_arr.min()
        hi  = tau > t_arr.max()
        if ok.any(): eff[ok] = np.clip(sp(tau[ok]), emin, 1.0)
        if lo.any(): eff[lo] = float(np.clip(sp([t_arr.min()]), emin, 1.0)[0])
        if hi.any():
            slope   = -emax / (stall - t_arr.max())
            eff[hi] = np.clip(emax + slope * (tau[hi] - t_arr.max()), emin, emax)
        return eff
    return fn


eff_fns      = {k: build_eff_fn(v) for k, v in EFFICIENCY_DEFS.items()}
default_key  = next(iter(EFFICIENCY_DEFS))


def resample(df_raw, interval=SAMPLE):
    t   = df_raw["time_s"].values
    t_s = np.arange(t[0], t[-1], interval)
    idx = np.clip(np.searchsorted(t, t_s), 0, len(df_raw) - 1)
    return df_raw.iloc[idx].reset_index(drop=True)


for label, csv_path in CSV_FILES.items():
    df_raw = pd.read_csv(csv_path)
    df     = df_raw[df_raw["time_s"] >= START_T].reset_index(drop=True)
    df     = resample(df)
    t_arr  = df["time_s"].values
    n      = len(t_arr)

    joint_in_pwr = {}
    for jname, jL, jR in JOINT_PAIRS:
        cols = [f"torque_{jL}", f"vel_{jL}", f"torque_{jR}", f"vel_{jR}"]
        if not all(c in df.columns for c in cols):
            continue
        scale  = TORQUE_SCALE.get(jname, 1.0)
        eff_fn = eff_fns[JOINT_EFF_MAP.get(jname, default_key)]
        total  = np.zeros(n)
        for jcol in [jL, jR]:
            tau_m = np.abs(df["torque_" + jcol].values) * scale
            vel_a = np.abs(df["vel_"    + jcol].values)
            total += (tau_m * vel_a) / eff_fn(tau_m)
        joint_in_pwr[jname] = total

    if not joint_in_pwr:
        print(f"[{label}] 未找到有效关节列，跳过")
        continue

    total_in   = np.sum(list(joint_in_pwr.values()), axis=0)
    rms_total  = np.sqrt(np.mean(total_in ** 2))
    peak_total = total_in.max()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    labels_list  = list(joint_in_pwr.keys())
    data_stack   = np.array(list(joint_in_pwr.values()))
    ax1.stackplot(t_arr, data_stack, labels=labels_list,
                  colors=COLORS[:len(labels_list)], alpha=0.75)
    ax1.set_ylabel("各关节输入功率 (W)", fontsize=9)
    ax1.legend(loc="upper right", fontsize=7, ncol=2)
    ax1.spines[["top", "right"]].set_visible(False)
    ax1.grid(True, linestyle="--", linewidth=0.3, alpha=0.5)

    ax2.plot(t_arr, total_in, color="#1D4ED8", lw=1.2, label="合计输入功率")
    ax2.axhline(rms_total, color="#DC2626", lw=1, linestyle="--",
                label=f"RMS = {rms_total:.0f} W")
    ax2.set_xlabel("时间 (s)", fontsize=9)
    ax2.set_ylabel("合计输入功率 (W)", fontsize=9)
    ax2.legend(fontsize=8)
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.grid(True, linestyle="--", linewidth=0.3, alpha=0.5)

    fig.suptitle(f"全身合计输入功率  {label}\nRMS={rms_total:.0f} W  峰值={peak_total:.0f} W",
                 fontsize=10)
    fig.tight_layout()
    fname = OUT_DIR / f"全身输入功率_{label}.png"
    fig.savefig(fname, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[{label}]  RMS={rms_total:.0f} W  峰值={peak_total:.0f} W")

print(f"\n全部图表已保存 → {OUT_DIR}")
