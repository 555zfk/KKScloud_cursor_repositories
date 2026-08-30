"""
scatter_abs.py
==============
为指定关节 × 多工况 CSV 生成 |扭矩(Nm)| vs |速度(RPM)| 散点图，
并在每个工况子文件夹中导出散点数据 CSV。

【使用前修改 ── USER CONFIG 区域】
"""

import shutil
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
from pathlib import Path

matplotlib.rcParams['font.family'] = 'Microsoft YaHei'
matplotlib.rcParams['axes.unicode_minus'] = False

# ════════════════════════════════════════════════════════════════════
# USER CONFIG  ── 按需修改以下内容
# ════════════════════════════════════════════════════════════════════

# 工况标签 → CSV 路径（可添加任意数量）
CSV_FILES = {
    "工况1": r"<CSV路径1>",
    "工况2": r"<CSV路径2>",
    "工况3": r"<CSV路径3>",
}

# 输出根目录（程序会自动清空并按工况重建子文件夹）
OUT_DIR = Path(r"<输出目录>") / "TN散点图"

# 关节定义列表：(显示名, 左侧列名后缀, 右侧列名后缀)
# 若某关节无左右之分，左右填相同值
JOINTS = [
    ("hip_pitch",   "left_hip_pitch_joint",   "right_hip_pitch_joint"),
    ("hip_roll",    "left_hip_roll_joint",     "right_hip_roll_joint"),
    ("hip_yaw",     "left_hip_yaw_joint",      "right_hip_yaw_joint"),
    ("knee_pitch",  "left_knee_joint",         "right_knee_joint"),
    ("ankle_pitch", "left_ankle_pitch_joint",  "right_ankle_pitch_joint"),
    ("ankle_roll",  "left_ankle_roll_joint",   "right_ankle_roll_joint"),
]

# 各关节扭矩缩放系数（默认 1.0，有减速比折算时修改）
TORQUE_SCALE = {
    "hip_pitch":   1.0,
    "hip_roll":    1.0,
    "hip_yaw":     1.0,
    "knee_pitch":  1.0,
    "ankle_pitch": 1.0,
    "ankle_roll":  1.0,
}

# 数据预处理参数
START_T = 0.5    # 忽略仿真前 N 秒
SAMPLE  = 0.02   # 重采样间隔(s)

# ════════════════════════════════════════════════════════════════════


def resample(df_raw, interval=SAMPLE):
    t   = df_raw["time_s"].values
    t_s = np.arange(t[0], t[-1], interval)
    idx = np.clip(np.searchsorted(t, t_s), 0, len(df_raw) - 1)
    return df_raw.iloc[idx].reset_index(drop=True)


def pick_side(df, jL, jR):
    pL = np.abs(df["torque_" + jL] * df["vel_" + jL]).values.max()
    pR = np.abs(df["torque_" + jR] * df["vel_" + jR]).values.max()
    return (jL, "L") if pL >= pR else (jR, "R")


# 清空并重建输出目录
if OUT_DIR.exists():
    shutil.rmtree(OUT_DIR)
gait_dirs = {}
for label in CSV_FILES:
    d = OUT_DIR / label
    d.mkdir(parents=True)
    gait_dirs[label] = d

gait_records = {label: [] for label in CSV_FILES}

for label, csv_path in CSV_FILES.items():
    df_raw = pd.read_csv(csv_path)
    df     = df_raw[df_raw["time_s"] >= START_T].reset_index(drop=True)
    df     = resample(df)

    for jname, jL, jR in JOINTS:
        jcol, side = pick_side(df, jL, jR)
        scale = TORQUE_SCALE.get(jname, 1.0)

        tau = np.abs(df["torque_" + jcol].values) * scale
        vel = np.abs(df["vel_"    + jcol].values) * 60 / (2 * np.pi)
        pwr = tau * np.abs(df["vel_" + jcol].values)

        fig, ax = plt.subplots(figsize=(5, 4))
        p_norm = pwr / (pwr.max() + 1e-9)
        ax.scatter(vel, tau, s=8 + 20 * p_norm, alpha=0.55,
                   c=pwr, cmap="viridis", linewidths=0)
        pk = np.argmax(pwr)
        ax.plot(vel[pk], tau[pk], "*k", ms=9)
        ax.annotate(f"{pwr[pk]:.0f} W", xy=(vel[pk], tau[pk]),
                    xytext=(5, 5), textcoords="offset points", fontsize=7)
        ax.set_xlim(0, vel.max() * 2)
        ax.set_ylim(0, tau.max() * 2)
        ax.set_xlabel("速度 (RPM)", fontsize=9)
        ax.set_ylabel("扭矩 (Nm)", fontsize=9)
        ax.set_title(f"{jname}  [{side}]  {label}", fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(True, linestyle="--", linewidth=0.4, alpha=0.6)
        fig.tight_layout()
        fig.savefig(gait_dirs[label] / f"{jname}_TN_scatter.png",
                    dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig)

        t_vals = df["time_s"].values
        for i in range(len(t_vals)):
            gait_records[label].append({
                "joint": jname, "side": side,
                "time_s":        round(float(t_vals[i]), 4),
                "torque_abs_Nm": round(float(tau[i]), 4),
                "vel_abs_rpm":   round(float(vel[i]), 4),
                "power_W":       round(float(pwr[i]), 4),
            })

    print(f"[{label}] 完成 → {gait_dirs[label]}")

for label, records in gait_records.items():
    pd.DataFrame(records).to_csv(
        gait_dirs[label] / "TN_scatter_data.csv", index=False, encoding="utf-8-sig")

print("全部完成。")
