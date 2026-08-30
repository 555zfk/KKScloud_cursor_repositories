"""
plot_input_power.py
===================
计算指定关节的输入功率时间曲线。
P_in = |tau_motor × vel| / η(|tau_motor|)
其中 η 由用户提供的效率数据插值（含超范围线性外推）。

每个关节 × 每个工况 输出一张四子图（扭矩/转速/效率/输入功率），
并打印 RMS 功率汇总表。

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

OUT_DIR = Path(r"<输出目录>") / "关节输入功率"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 工况 CSV
CSV_FILES = {
    "工况1": r"<CSV路径1>",
    "工况2": r"<CSV路径2>",
    "工况3": r"<CSV路径3>",
}

# 分析关节：(显示名, 左侧列名后缀, 右侧列名后缀)
JOINTS = [
    ("hip_pitch",  "left_hip_pitch_joint",  "right_hip_pitch_joint"),
    ("hip_roll",   "left_hip_roll_joint",   "right_hip_roll_joint"),
    ("hip_yaw",    "left_hip_yaw_joint",    "right_hip_yaw_joint"),
    ("knee_pitch", "left_knee_joint",       "right_knee_joint"),
]

# 各关节扭矩缩放系数（默认 1.0）
TORQUE_SCALE = {
    "hip_pitch":  1.0,
    "hip_roll":   1.0,
    "hip_yaw":    1.0,
    "knee_pitch": 1.0,
}

# ── 效率数据（从电机效率曲线图手动读取）──────────────────────────────────────
# 所有关节共用同一效率曲线；如需按关节分配不同曲线，见下方说明
EFF_TORQUE = np.array([
    0.5,  1.4,  2.3,  3.5,  4.6,  5.6,  6.5,  7.4,  8.3,  9.7,
   10.6, 11.8, 12.5, 13.6, 14.5, 15.5, 16.3, 17.1, 18.7, 19.2,
   20.1, 21.6, 22.3, 23.0, 24.1, 25.1, 26.8, 27.5, 28.1, 29.4,
   30.0, 32.6, 33.9, 34.5, 35.9
])
EFF_VALS = np.array([
    30, 55, 65, 64, 71, 75, 74, 74, 70, 77,
    74, 71, 70, 72, 72, 66, 66, 66, 66, 65,
    63, 61, 59, 58, 55, 51, 43, 40, 36, 28,
    20, 18, 14, 10,  4
]) / 100.0

EFF_LAM      = 1.2    # smoothing spline 平滑系数
EFF_MIN      = 0.03   # 效率下限（防止除以极小值）
STALL_TORQUE = 42.0   # 估算堵转扭矩(Nm)，用于超出范围线性外推至 0

# 若不同关节使用不同效率曲线，可定义字典：
#   EFF_OVERRIDE = { "ankle_pitch": { "torque": [...], "eff": [...], "lam": 0.8,
#                                     "eff_min": 0.25, "stall": 13.5 } }
# 未在字典中的关节使用上方默认曲线
EFF_OVERRIDE = {}

# ════════════════════════════════════════════════════════════════════

START_T = 0.5
SAMPLE  = 0.02


def build_eff_fn(torque_arr, eff_arr, lam, eff_min, stall):
    sp       = make_smoothing_spline(torque_arr, eff_arr, lam=lam)
    eff_amax = float(np.clip(sp([torque_arr.max()]), eff_min, 1.0)[0])

    def get_eff(tau_abs):
        eff = np.empty_like(tau_abs, dtype=float)
        ok  = (tau_abs >= torque_arr.min()) & (tau_abs <= torque_arr.max())
        lo  = tau_abs < torque_arr.min()
        hi  = tau_abs > torque_arr.max()
        if ok.any():
            eff[ok] = np.clip(sp(tau_abs[ok]), eff_min, 1.0)
        if lo.any():
            eff[lo] = float(np.clip(sp([torque_arr.min()]), eff_min, 1.0)[0])
        if hi.any():
            slope   = -eff_amax / (stall - torque_arr.max())
            eff[hi] = np.clip(eff_amax + slope * (tau_abs[hi] - torque_arr.max()),
                              eff_min, eff_amax)
        return eff
    return get_eff, torque_arr.max()


# 构建默认效率函数
default_eff_fn, default_eff_max = build_eff_fn(
    EFF_TORQUE, EFF_VALS, EFF_LAM, EFF_MIN, STALL_TORQUE)

# 构建关节专属效率函数
joint_eff_fn  = {}
joint_eff_max = {}
for jname, cfg in EFF_OVERRIDE.items():
    fn, mx = build_eff_fn(
        np.array(cfg["torque"]), np.array(cfg["eff"]),
        cfg.get("lam", 1.0), cfg.get("eff_min", 0.03), cfg["stall"])
    joint_eff_fn[jname]  = fn
    joint_eff_max[jname] = mx


def resample(df_raw, interval=SAMPLE):
    t   = df_raw["time_s"].values
    t_s = np.arange(t[0], t[-1], interval)
    idx = np.clip(np.searchsorted(t, t_s), 0, len(df_raw) - 1)
    return df_raw.iloc[idx].reset_index(drop=True)


def pick_side(df, jL, jR):
    pL = np.abs(df["torque_" + jL] * df["vel_" + jL]).values.max()
    pR = np.abs(df["torque_" + jR] * df["vel_" + jR]).values.max()
    return (jL, "L") if pL >= pR else (jR, "R")


print(f"{'关节':<12} {'工况':<8} {'RMS输出(W)':>10} {'RMS输入(W)':>10} "
      f"{'RMS清洁(W)':>10} {'峰值输入(W)':>12} {'饱和点':>6}")
print("-" * 72)

for jname, jL, jR in JOINTS:
    eff_fn  = joint_eff_fn.get(jname,  default_eff_fn)
    eff_max = joint_eff_max.get(jname, default_eff_max)
    scale   = TORQUE_SCALE.get(jname, 1.0)

    for label, csv_path in CSV_FILES.items():
        df_raw = pd.read_csv(csv_path)
        df     = df_raw[df_raw["time_s"] >= START_T].reset_index(drop=True)
        df     = resample(df)

        jcol, side = pick_side(df, jL, jR)
        t_arr   = df["time_s"].values
        tau_sim = df["torque_" + jcol].values
        vel_sim = df["vel_"    + jcol].values

        tau_m   = np.abs(tau_sim) * scale
        vel_abs = np.abs(vel_sim)
        out_pwr = tau_m * vel_abs
        eff     = eff_fn(tau_m)
        in_pwr  = out_pwr / eff

        sat_mask  = tau_m > eff_max
        n_sat     = sat_mask.sum()
        rms_out   = np.sqrt(np.mean(out_pwr ** 2))
        rms_in    = np.sqrt(np.mean(in_pwr  ** 2))
        rms_clean = np.sqrt(np.mean(in_pwr[~sat_mask] ** 2)) if (~sat_mask).any() else rms_in
        peak_in   = in_pwr.max()

        flag = "*" if n_sat > 0 else ""
        print(f"{jname:<12} {label:<8} {rms_out:>10.1f} {rms_in:>10.1f} "
              f"{rms_clean:>10.1f} {peak_in:>12.1f} {n_sat:>5}{flag}")

        # ── 绘图 ────────────────────────────────────────────────────────────
        fig, axes = plt.subplots(4, 1, figsize=(10, 10), sharex=True)
        scale_label = f"(×{scale})" if scale != 1.0 else ""
        plot_data = [
            (f"扭矩 (Nm){scale_label}", tau_sim * scale, "#1D4ED8"),
            ("转速 (RPM)",               vel_sim * 60 / (2 * np.pi), "#059669"),
            ("效率 (%)",                  eff * 100,  "#D97706"),
            ("输入功率 (W)",              in_pwr,     "#DC2626"),
        ]
        for ax, (title, data, col) in zip(axes, plot_data):
            ax.plot(t_arr, data, color=col, lw=0.8)
            if title == "输入功率 (W)" and n_sat > 0:
                ax.scatter(t_arr[sat_mask], in_pwr[sat_mask],
                           color="orange", s=15, zorder=5, label=f"饱和点 n={n_sat}")
                ax.legend(fontsize=7)
            ax.set_ylabel(title, fontsize=8)
            ax.spines[["top", "right"]].set_visible(False)
            ax.grid(True, linestyle="--", linewidth=0.3, alpha=0.5)
        axes[-1].set_xlabel("时间 (s)", fontsize=9)
        fig.suptitle(f"输入功率  {jname}[{side}]  {label}\n"
                     f"RMS输出={rms_out:.1f}W  RMS输入={rms_in:.1f}W  "
                     f"RMS清洁={rms_clean:.1f}W  峰值={peak_in:.0f}W", fontsize=9)
        fig.tight_layout()
        fig.savefig(OUT_DIR / f"{jname}_{label}_输入功率.png",
                    dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig)

print("\n* 表示存在超出效率曲线范围的饱和点，RMS清洁为排除后的值")
print(f"\n全部图表已保存 → {OUT_DIR}")
