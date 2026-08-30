# -*- coding: utf-8 -*-
"""关节六维力分解：轴向扭矩 / 倾覆力矩 / 径向力 / 轴向力。

输入：仿真导出的 npz（含 joint_wrench_world、joint_axis_world 等字段）
输出：统计表 + 时程图 + 逐样本 CSV

用法：改下面 USER CONFIG 后 `python wrench_decompose.py`
"""

import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ============================== USER CONFIG ==============================
NPZ_PATH = r"<npz文件路径>"
OUT_DIR = r"<输出目录，如 cursor生成文件/任务主题_YYYYMMDD>"

# 要分析的关节名（须与 joint_names 中一致）
JOINTS = ["left_knee_joint", "right_knee_joint"]

# 对应的执行器名，用于对比轴向扭矩与执行器扭矩；无对应项写 None
ACTUATORS = ["knee_left", "knee_right"]

ROBOT_MASS = None      # kg，留 None 则由静止段的地面反力自动估算
FLIGHT_FRAC = 0.05     # 地面反力低于 FLIGHT_FRAC×体重 判为腾空

# 字段名（不同导出脚本可能不同，先打印键名再改）
K_TIME, K_JNAME = "time", "joint_names"
K_WRENCH, K_AXIS = "joint_wrench_world", "joint_axis_world"
K_QUAT = "joint_quaternion_world_wxyz"
K_ANAME, K_ATORQUE = "actuator_names", "actuator_output_torque"
K_LINK_EXT = "link_external_wrench_world"
# =========================================================================

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False


def quat_to_R(q):
    """(N,4) wxyz -> (N,3,3)，局部系到世界系。"""
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    R = np.empty((len(q), 3, 3))
    R[:, 0, 0] = 1 - 2 * (y * y + z * z)
    R[:, 0, 1] = 2 * (x * y - w * z)
    R[:, 0, 2] = 2 * (x * z + w * y)
    R[:, 1, 0] = 2 * (x * y + w * z)
    R[:, 1, 1] = 1 - 2 * (x * x + z * z)
    R[:, 1, 2] = 2 * (y * z - w * x)
    R[:, 2, 0] = 2 * (x * z - w * y)
    R[:, 2, 1] = 2 * (y * z + w * x)
    R[:, 2, 2] = 1 - 2 * (x * x + y * y)
    return R


def stats(x):
    return dict(max=x.max(), rms=float(np.sqrt((x ** 2).mean())),
                p95=float(np.percentile(x, 95)), p99=float(np.percentile(x, 99)),
                cube=float(np.mean(x ** 3) ** (1 / 3)) if (x >= 0).all() else np.nan)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    d = np.load(NPZ_PATH, allow_pickle=True)
    t = d[K_TIME]
    fs_hz = 1.0 / np.median(np.diff(t))
    jn = [str(s) for s in d[K_JNAME]]
    W_all, AX_all = d[K_WRENCH], d[K_AXIS]
    has_quat = K_QUAT in d
    has_act = K_ANAME in d and K_ATORQUE in d
    an = [str(s) for s in d[K_ANAME]] if has_act else []

    # 真实地面反力：必须对所有 link 求和，只取足部会被闭链约束力污染
    Fg = None
    if K_LINK_EXT in d:
        Fg = d[K_LINK_EXT][:, :, 2].sum(axis=1)
        neg = (Fg < -1.0).sum()
        print(f"地面反力自检：min={Fg.min():.1f} N, 负样本数={neg} "
              f"({'正常' if neg < len(Fg) * 0.01 else '异常，检查字段或求和范围'})")

    mass = ROBOT_MASS
    if mass is None and Fg is not None:
        tail = Fg[int(len(Fg) * 0.85):]                 # 末段通常静止
        mass = float(np.median(tail) / 9.807)
    BW = mass * 9.807 if mass else None
    if mass:
        print(f"整机质量 ≈ {mass:.2f} kg (体重 {BW:.1f} N)")
    print(f"采样率 ≈ {fs_hz:.1f} Hz，样本数 {len(t)}\n")

    air = (Fg < FLIGHT_FRAC * BW) if (Fg is not None and BW) else np.zeros(len(t), bool)

    rows, results = [], {}
    for k, name in enumerate(JOINTS):
        ji = jn.index(name)
        W = W_all[:, ji, :]
        F, M = W[:, :3], W[:, 3:]
        a = AX_all[:, ji, :]
        a = a / np.linalg.norm(a, axis=1, keepdims=True)

        tau_ax = np.einsum("ij,ij->i", M, a)                        # 轴向扭矩
        M_perp = np.linalg.norm(M - tau_ax[:, None] * a, axis=1)    # 倾覆力矩
        F_ax = np.einsum("ij,ij->i", F, a)                          # 轴向力
        F_rad = np.linalg.norm(F - F_ax[:, None] * a, axis=1)       # 径向力

        # 转到关节子体系，分解为两个正交弯矩分量，并自检变换正确性
        M_loc, perp_idx = None, None
        if has_quat:
            R = quat_to_R(d[K_QUAT][:, ji, :])
            M_loc = np.einsum("nji,nj->ni", R, M)
            a_loc = np.einsum("nji,nj->ni", R, a)
            ax_idx = int(np.argmax(np.abs(a_loc).mean(axis=0)))
            perp_idx = [i for i in range(3) if i != ax_idx]
            sd = a_loc.std(axis=0).max()
            print(f"[{name}] 回转轴在子体系 = {np.round(a_loc.mean(axis=0),4)}, "
                  f"标准差 {sd:.6f} -> {'变换自洽' if sd < 1e-3 else '异常，检查四元数顺序/转置'}")

        results[name] = dict(tau_ax=tau_ax, M_perp=M_perp, F_ax=F_ax, F_rad=F_rad,
                             M_loc=M_loc, perp_idx=perp_idx)

        print(f"\n【{name}】")
        print(f"  {'量':24s} {'最大':>10s} {'RMS':>9s} {'p95':>9s} {'p99':>9s} {'立方平均':>9s}")
        items = [("倾覆力矩 M_perp (N·m)", M_perp), ("轴向扭矩 |Tz| (N·m)", np.abs(tau_ax)),
                 ("径向力 F_rad (N)", F_rad), ("轴向力 |F_ax| (N)", np.abs(F_ax))]
        for lbl, x in items:
            s = stats(x)
            print(f"  {lbl:24s} {s['max']:10.1f} {s['rms']:9.1f} {s['p95']:9.1f} "
                  f"{s['p99']:9.1f} {s['cube']:9.1f}")
            rows.append([name, lbl, f"{s['max']:.2f}", f"{s['rms']:.2f}",
                         f"{s['p95']:.2f}", f"{s['p99']:.2f}", f"{s['cube']:.2f}"])

        ratio = np.median(M_perp / np.maximum(np.abs(tau_ax), 1e-3))
        print(f"  倾覆/轴向 比值中位数 = {ratio:.2f}")

        # 峰值可信性：检查是否在单个采样步内建立
        kp = int(np.argmax(M_perp))
        lo, hi = max(0, kp - 20), min(len(t), kp + 20)
        jump = np.diff(M_perp[lo:hi]).max()
        print(f"  倾覆峰值 {M_perp[kp]:.1f} N·m @ t={t[kp]:.3f}s, "
              f"邻域最大单步跃升 {jump:.1f} N·m ({jump/M_perp[kp]*100:.0f}% of 峰值) "
              f"-> {'欠解析，仅作定性参考' if jump > 0.5*M_perp[kp] else '上升过程已解析'}")
        if has_act and k < len(ACTUATORS) and ACTUATORS[k] in an:
            tau = d[K_ATORQUE][:, an.index(ACTUATORS[k])]
            slew = np.abs(np.diff(tau[lo:hi])).max() * fs_hz
            print(f"  同邻域执行器扭矩最大变化率 {slew/1000:.1f} kN·m/s "
                  f"-> {'控制跳变假象' if slew > 1e5 else '实机大致可实现，属接触冲击'}")
        if Fg is not None and BW:
            print(f"  峰值时刻地面反力 = {Fg[kp]/BW:.2f} BW，相位 = "
                  f"{'腾空' if air[kp] else '接触'}")

    # ---------------------------------------------------------------- 绘图
    n = len(JOINTS)
    fig, axes = plt.subplots(3, 1, figsize=(15, 10), sharex=True)
    fig.subplots_adjust(hspace=0.30)
    colors = plt.cm.tab10(np.linspace(0, 1, 10))

    def shade(ax):
        if not air.any():
            return
        idx = np.where(air)[0]
        g, cur = [], [idx[0]]
        for i in idx[1:]:
            if i == cur[-1] + 1:
                cur.append(i)
            else:
                g.append(cur); cur = [i]
        g.append(cur)
        for s in g:
            if len(s) >= 5:
                ax.axvspan(t[s[0]], t[s[-1]], color="#87CEEB", alpha=0.25, zorder=0)

    ax = axes[0]
    shade(ax)
    for i, name in enumerate(JOINTS):
        r = results[name]
        ax.plot(t, r["M_perp"], lw=1.1, color=colors[i], label=f"{name} 倾覆力矩")
        p99 = np.percentile(r["M_perp"], 99)
        ax.axhline(p99, color=colors[i], ls="--", lw=1.1, alpha=0.7,
                   label=f"{name} p99 = {p99:.0f} N·m")
    ax.set_ylabel("倾覆力矩 (N·m)")
    ax.set_title("关节倾覆力矩时程（垂直于回转轴的合成弯矩，关于关节点）— 蓝色区为腾空",
                 fontsize=12.5, weight="bold")
    ax.legend(fontsize=8.5, ncol=2); ax.grid(alpha=0.3)

    ax = axes[1]
    shade(ax)
    for i, name in enumerate(JOINTS):
        r = results[name]
        ax.plot(t, r["M_perp"], lw=1.1, color=colors[i], label=f"{name} 倾覆")
        ax.plot(t, np.abs(r["tau_ax"]), lw=0.9, ls="--", color=colors[i],
                alpha=0.75, label=f"{name} |轴向|")
    ax.set_ylabel("力矩 (N·m)")
    ax.set_title("倾覆力矩 vs 轴向扭矩（倾覆通常为轴向的 2～2.5 倍）",
                 fontsize=11.5, weight="bold")
    ax.legend(fontsize=8.5, ncol=2); ax.grid(alpha=0.3)

    ax = axes[2]
    shade(ax)
    for i, name in enumerate(JOINTS):
        r = results[name]
        ax.plot(t, r["F_rad"], lw=1.1, color=colors[i], label=f"{name} 径向力")
        ax.plot(t, np.abs(r["F_ax"]), lw=0.9, ls="--", color=colors[i],
                alpha=0.75, label=f"{name} |轴向力|")
    if Fg is not None:
        ax.plot(t, Fg, lw=0.9, color="gray", alpha=0.6, label="地面反力 Fz（参照）")
    ax.set_ylabel("力 (N)"); ax.set_xlabel("时间 (s)")
    ax.set_title("径向力 / 轴向力（用于输出轴承等效动载荷与寿命校核）",
                 fontsize=11.5, weight="bold")
    ax.legend(fontsize=8.5, ncol=3); ax.grid(alpha=0.3)

    ttl = f"关节六维力分解 · {fs_hz:.0f} Hz"
    if mass:
        ttl += f" · m≈{mass:.1f} kg"
    fig.suptitle(ttl, fontsize=14, weight="bold", y=0.995)
    p_png = os.path.join(OUT_DIR, "关节六维力分解.png")
    fig.savefig(p_png, dpi=135, bbox_inches="tight")
    print(f"\nsaved: {p_png}")

    # ---------------------------------------------------------------- 导出
    p_stat = os.path.join(OUT_DIR, "关节六维力统计.csv")
    with open(p_stat, "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f)
        wr.writerow(["joint", "quantity", "max", "rms", "p95", "p99", "cube_mean"])
        wr.writerows(rows)
    print(f"saved: {p_stat}")

    p_ts = os.path.join(OUT_DIR, "关节六维力时程.csv")
    with open(p_ts, "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f)
        hdr = ["time_s"]
        for name in JOINTS:
            hdr += [f"{name}_M_overturning_Nm", f"{name}_tau_axial_Nm",
                    f"{name}_F_radial_N", f"{name}_F_axial_N"]
        if Fg is not None:
            hdr += ["ground_reaction_N", "is_flight"]
        wr.writerow(hdr)
        for i in range(len(t)):
            row = [f"{t[i]:.4f}"]
            for name in JOINTS:
                r = results[name]
                row += [f"{r['M_perp'][i]:.3f}", f"{r['tau_ax'][i]:.3f}",
                        f"{r['F_rad'][i]:.2f}", f"{r['F_ax'][i]:.2f}"]
            if Fg is not None:
                row += [f"{Fg[i]:.2f}", int(air[i])]
            wr.writerow(row)
    print(f"saved: {p_ts}")


if __name__ == "__main__":
    main()
