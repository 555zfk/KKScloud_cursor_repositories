"""
plot_required_TN.py
===================
从仿真 CSV 中推导关节需求 TN 曲线（梯形模型）。
通过二分法找到满足指定覆盖率的最小 T_flat。

支持：多工况合并 / 仅指定工况 / 多关节合并分析

【使用前修改 ── USER CONFIG 区域】
"""

import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
from pathlib import Path

matplotlib.rcParams['font.family'] = 'Microsoft YaHei'
matplotlib.rcParams['axes.unicode_minus'] = False

# ════════════════════════════════════════════════════════════════════
# USER CONFIG
# ════════════════════════════════════════════════════════════════════

# 输出目录
OUT_DIR = Path(r"<输出目录>") / "需求TN曲线"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 图表标题（说明本次分析的关节/场景）
TITLE = "关节需求 TN 曲线"

# 参与分析的工况 CSV（可只填一个）
CSV_FILES = {
    "工况1": r"<CSV路径1>",
    "工况2": r"<CSV路径2>",
    "工况3": r"<CSV路径3>",
}

# 参与分析的关节：(显示名, 左侧列名后缀, 右侧列名后缀)
JOINTS = [
    ("hip_pitch",  "left_hip_pitch_joint",  "right_hip_pitch_joint"),
    ("hip_roll",   "left_hip_roll_joint",   "right_hip_roll_joint"),
    ("hip_yaw",    "left_hip_yaw_joint",    "right_hip_yaw_joint"),
    ("knee_pitch", "left_knee_joint",       "right_knee_joint"),
]

# 关节扭矩缩放系数（默认 1.0）
TORQUE_SCALE = {
    "hip_pitch":  1.0,
    "hip_roll":   1.0,
    "hip_yaw":    1.0,
    "knee_pitch": 1.0,
}

# TN 曲线参数
N_BASE    = 60.0    # RPM，额定（基速）
N_MAX     = 150.0   # RPM，最高转速
COV_CONT  = 0.85    # 连续工作区间覆盖率目标
COV_PEAK  = 0.98    # 短时工作区间覆盖率目标

# 数据预处理
START_T = 0.5
SAMPLE  = 0.02

# ════════════════════════════════════════════════════════════════════


def resample(df_raw, interval=SAMPLE):
    t   = df_raw["time_s"].values
    t_s = np.arange(t[0], t[-1], interval)
    idx = np.clip(np.searchsorted(t, t_s), 0, len(df_raw) - 1)
    return df_raw.iloc[idx].reset_index(drop=True)


def pick_side(df, jL, jR):
    pL = np.abs(df["torque_" + jL] * df["vel_" + jL]).values.max()
    pR = np.abs(df["torque_" + jR] * df["vel_" + jR]).values.max()
    return jL if pL >= pR else jR


def tn_value(speed, T_flat):
    s = np.asarray(speed, dtype=float)
    return np.where(s <= N_BASE, T_flat,
           np.where(s <= N_MAX, T_flat * (N_MAX - s) / (N_MAX - N_BASE), 0.0))


def coverage(vel_all, tau_all, T_flat):
    return np.mean(tau_all <= tn_value(vel_all, T_flat))


def find_T_for_coverage(vel_all, tau_all, target, tol=1e-4):
    lo, hi = 0.0, tau_all.max() * 1.5
    for _ in range(80):
        mid = (lo + hi) / 2
        if coverage(vel_all, tau_all, mid) >= target:
            hi = mid
        else:
            lo = mid
        if hi - lo < tol:
            break
    return hi


# ── 汇总散点 ──────────────────────────────────────────────────────────────────
vel_all, tau_all = [], []

for label, csv_path in CSV_FILES.items():
    df_raw = pd.read_csv(csv_path)
    df     = df_raw[df_raw["time_s"] >= START_T].reset_index(drop=True)
    df     = resample(df)
    for jname, jL, jR in JOINTS:
        jcol  = pick_side(df, jL, jR)
        scale = TORQUE_SCALE.get(jname, 1.0)
        tau_all.append(np.abs(df["torque_" + jcol].values) * scale)
        vel_all.append(np.abs(df["vel_"    + jcol].values) * 60 / (2 * np.pi))

vel_all = np.concatenate(vel_all)
tau_all = np.concatenate(tau_all)

# ── 求解 ──────────────────────────────────────────────────────────────────────
T_cont = find_T_for_coverage(vel_all, tau_all, COV_CONT)
T_peak = find_T_for_coverage(vel_all, tau_all, COV_PEAK)
cov_c  = coverage(vel_all, tau_all, T_cont) * 100
cov_p  = coverage(vel_all, tau_all, T_peak) * 100
P_cont = T_cont * N_BASE * 2 * np.pi / 60
P_peak = T_peak * N_BASE * 2 * np.pi / 60

print("=" * 55)
print(f"  {TITLE}")
print(f"  连续：T_flat={T_cont:.2f} Nm  覆盖{cov_c:.1f}%  额定功率{P_cont:.1f} W")
print(f"  短时：T_flat={T_peak:.2f} Nm  覆盖{cov_p:.1f}%  峰值功率{P_peak:.1f} W")
print(f"  N_BASE={N_BASE} rpm  N_MAX={N_MAX} rpm")
print("=" * 55)

# ── 绘图 ──────────────────────────────────────────────────────────────────────
rpm_x  = np.linspace(0, N_MAX * 1.05, 400)
pwr_all = tau_all * vel_all * 2 * np.pi / 60
p_norm  = pwr_all / (pwr_all.max() + 1e-9)

fig, ax = plt.subplots(figsize=(7, 5))
ax.scatter(vel_all, tau_all, s=4 + 10 * p_norm, alpha=0.2,
           c=pwr_all, cmap="Blues", linewidths=0, label="仿真散点（合并）")
ax.plot(rpm_x, tn_value(rpm_x, T_cont), color="#2563EB", lw=2,
        label=f"连续 {T_cont:.1f} Nm  ({cov_c:.0f}%)  {P_cont:.0f} W")
ax.plot(rpm_x, tn_value(rpm_x, T_peak), color="#DC2626", lw=2, linestyle="--",
        label=f"短时 {T_peak:.1f} Nm  ({cov_p:.0f}%)  {P_peak:.0f} W")
ax.axvline(N_BASE, color="gray", lw=1, linestyle=":", alpha=0.7)
ax.text(N_BASE + 1, ax.get_ylim()[0] + 0.5, f"N_base={N_BASE:.0f}",
        fontsize=7, color="gray")
ax.set_xlabel("速度 (RPM)", fontsize=10)
ax.set_ylabel("扭矩 (Nm)", fontsize=10)
ax.set_title(TITLE, fontsize=11)
ax.set_xlim(0, N_MAX * 1.1)
ax.set_ylim(0)
ax.legend(fontsize=8)
ax.spines[["top", "right"]].set_visible(False)
ax.grid(True, linestyle="--", linewidth=0.4, alpha=0.5)
fig.tight_layout()
fig.savefig(OUT_DIR / "需求TN曲线.png", dpi=150, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"图表已保存 → {OUT_DIR / '需求TN曲线.png'}")
