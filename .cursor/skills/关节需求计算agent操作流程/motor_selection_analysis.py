"""
motor_selection_analysis.py
============================
关节电机选型分析：
  1. 从仿真 CSV 计算各关节连续/短时扭矩需求（百分位覆盖）
  2. 与用户定义的电机规格对比，给出选型建议
  3. 绘制需求点与电机 TN 曲线对比图

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

OUT_DIR = Path(r"<输出目录>") / "电机选型分析"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 工况 CSV
CSV_FILES = {
    "工况1": r"<CSV路径1>",
    "工况2": r"<CSV路径2>",
    "工况3": r"<CSV路径3>",
}

# 分析关节
JOINTS = [
    ("hip_pitch",  "left_hip_pitch_joint",  "right_hip_pitch_joint"),
    ("hip_roll",   "left_hip_roll_joint",   "right_hip_roll_joint"),
    ("hip_yaw",    "left_hip_yaw_joint",    "right_hip_yaw_joint"),
    ("knee_pitch", "left_knee_joint",       "right_knee_joint"),
]

# 各关节扭矩缩放系数
TORQUE_SCALE = {j[0]: 1.0 for j in JOINTS}

# 覆盖率目标
COV_CONT = 0.85   # 连续工作区间
COV_PEAK = 0.98   # 短时工作区间

# TN 曲线参数
N_BASE = 60.0     # RPM，额定转速
N_MAX  = 150.0    # RPM，最高转速

# ── 可选电机规格 ─────────────────────────────────────────────────────────────
# 格式：{ "显示名": { "rated_nm": 额定扭矩, "rated_rpm": 额定转速,
#                    "peak_nm":  峰值扭矩, "peak_rpm":  峰值转速,
#                    "color": 曲线颜色 } }
MOTOR_SPECS = {
    "电机选项1": {"rated_nm":  7.0, "rated_rpm": 60, "peak_nm": 20.0, "peak_rpm": 120, "color": "#2563EB"},
    "电机选项2": {"rated_nm": 14.0, "rated_rpm": 60, "peak_nm": 32.5, "peak_rpm": 120, "color": "#DC2626"},
    "电机选项3": {"rated_nm":  3.0, "rated_rpm": 60, "peak_nm": 10.0, "peak_rpm": 120, "color": "#059669"},
}

# ════════════════════════════════════════════════════════════════════

START_T = 0.5
SAMPLE  = 0.02


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


def find_T(vel_all, tau_all, target, tol=1e-4):
    lo, hi = 0.0, tau_all.max() * 1.5
    for _ in range(80):
        mid = (lo + hi) / 2
        if np.mean(tau_all <= tn_value(vel_all, mid)) >= target:
            hi = mid
        else:
            lo = mid
        if hi - lo < tol:
            break
    return hi


def select_motor(T_cont, T_peak):
    for name, s in MOTOR_SPECS.items():
        if T_cont <= s["rated_nm"] and T_peak <= s["peak_nm"]:
            return name, "满足"
    return "超出所有选项", "需复核减速比"


def rated_power(nm, rpm):
    return nm * rpm * 2 * np.pi / 60


# ── 汇总散点 ──────────────────────────────────────────────────────────────────
results = {}
for jname, jL, jR in JOINTS:
    vel_all, tau_all = [], []
    for label, csv_path in CSV_FILES.items():
        df_raw = pd.read_csv(csv_path)
        df     = df_raw[df_raw["time_s"] >= START_T].reset_index(drop=True)
        df     = resample(df)
        jcol   = pick_side(df, jL, jR)
        scale  = TORQUE_SCALE.get(jname, 1.0)
        vel_all.append(np.abs(df["vel_"    + jcol].values) * 60 / (2 * np.pi))
        tau_all.append(np.abs(df["torque_" + jcol].values) * scale)
    vel_all = np.concatenate(vel_all)
    tau_all = np.concatenate(tau_all)
    T_cont  = find_T(vel_all, tau_all, COV_CONT)
    T_peak  = find_T(vel_all, tau_all, COV_PEAK)
    results[jname] = {"vel": vel_all, "tau": tau_all,
                      "T_cont": T_cont, "T_peak": T_peak,
                      "vel_max": vel_all.max()}

# ── 打印汇总 ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 72)
print(f"{'关节':<12} {'连续扭矩':>8} {'短时扭矩':>8} {'峰值转速':>8}  {'推荐选项':<16} {'状态'}")
print("-" * 72)
for jname, r in results.items():
    motor_name, status = select_motor(r["T_cont"], r["T_peak"])
    print(f"{jname:<12} {r['T_cont']:>7.2f}Nm {r['T_peak']:>7.2f}Nm "
          f"{r['vel_max']:>7.1f}rpm  {motor_name:<16} {status}")
print("=" * 72)

print("\n电机选项规格：")
print(f"{'名称':<14} {'额定扭矩':>8} {'额定功率':>8} {'峰值扭矩':>8} {'最大功率':>8}")
print("-" * 50)
for name, s in MOTOR_SPECS.items():
    print(f"{name:<14} {s['rated_nm']:>7.1f}Nm "
          f"{rated_power(s['rated_nm'],s['rated_rpm']):>7.1f}W "
          f"{s['peak_nm']:>7.1f}Nm "
          f"{rated_power(s['peak_nm'],s['peak_rpm']):>7.1f}W")

# ── 绘图 ──────────────────────────────────────────────────────────────────────
n_joints = len(results)
ncols    = 2
nrows    = (n_joints + 1) // ncols
rpm_x    = np.linspace(0, N_MAX * 1.1, 400)

fig, axes = plt.subplots(nrows, ncols, figsize=(7 * ncols, 5 * nrows))
axes = np.array(axes).flatten()

for ax, (jname, r) in zip(axes, results.items()):
    pwr  = r["tau"] * r["vel"] * 2 * np.pi / 60
    pnorm = pwr / (pwr.max() + 1e-9)
    ax.scatter(r["vel"], r["tau"], s=3 + 8 * pnorm,
               alpha=0.2, c=pwr, cmap="Blues", linewidths=0)
    for mname, ms in MOTOR_SPECS.items():
        nm_arr = np.where(rpm_x <= ms["rated_rpm"], ms["rated_nm"],
                 np.where(rpm_x <= ms["peak_rpm"],
                          ms["rated_nm"] * (ms["peak_rpm"] - rpm_x) /
                          (ms["peak_rpm"] - ms["rated_rpm"]), 0.0))
        ax.plot(rpm_x, nm_arr, color=ms["color"], lw=1.5, label=mname)
    ax.axhline(r["T_cont"], color="#1D4ED8", lw=1.2, linestyle="--",
               label=f"连续需求 {r['T_cont']:.1f}Nm")
    ax.axhline(r["T_peak"], color="#DC2626", lw=1.2, linestyle=":",
               label=f"短时需求 {r['T_peak']:.1f}Nm")
    ax.set_title(jname, fontsize=10)
    ax.set_xlabel("速度 (RPM)", fontsize=8)
    ax.set_ylabel("扭矩 (Nm)", fontsize=8)
    ax.set_xlim(0, N_MAX * 1.1)
    ax.set_ylim(0)
    ax.legend(fontsize=6, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(True, linestyle="--", linewidth=0.3, alpha=0.5)

for ax in axes[n_joints:]:
    ax.set_visible(False)

fig.suptitle("关节需求 vs 电机 TN 曲线对比", fontsize=11)
fig.tight_layout()
fig.savefig(OUT_DIR / "电机选型对比.png", dpi=150, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"\n对比图已保存 → {OUT_DIR / '电机选型对比.png'}")
