# -*- coding: utf-8 -*-
"""交叉滚子环选型校核（THK 交叉滚子环样本 515-1E 公式）。

P0 = Fr + 2M/dp + 0.44·Fa      fs = C0/P0      普通≥2 / 冲击≥5 / 推荐≥7
静许用倾覆力矩 M0 = C0·dp/2（fs=1 损伤临界，非设计许用值）
双轴承成对（中心距 L）：P0 = M/L + Fr/2 + 0.44·Fa，许用弯矩 = C0·L/fs

用法：改下面 USER CONFIG 后 `python crossed_roller_check.py`
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ============================== USER CONFIG ==============================
OUT_DIR = r"<输出目录，如 cursor生成文件/任务主题_YYYYMMDD>"

# 候选轴承：(名称, d, D, B, dp[mm], C[kN], C0[kN], 质量[kg])，数值取自厂商尺寸表
BEARINGS = [
    ("RAU8005", 80, 91, 5, 84.7, 3.05, 5.43, 0.050),
    ("RA8008", 80, 96, 8, 87.0, 6.37, 11.30, 0.110),
    ("RB8016", 80, 120, 16, 98.0, 30.10, 42.10, 0.700),
]

PAIR_SPACING = 60.0     # 双轴承中心距 mm；None 则跳过成对布置分析

# 载荷来源：给定 CSV 走时程校核，否则用下面的定值工况
LOAD_CSV = None         # 由 wrench_decompose.py 导出的时程 CSV 路径
COL_M, COL_FR, COL_FA = "M_overturning_Nm", "F_radial_N", "F_axial_N"  # 列名子串

# 定值工况：(工况名, 倾覆力矩 N·m, 径向力 N, 轴向力 N)
CASES = [
    ("中位工况", 45.5, 207, 36),
    ("p99 工况", 220.2, 1286, 221),
    ("峰值工况", 584.0, 5073, 596),
]
# =========================================================================

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

X0, Y0 = 1.0, 0.44
FS_LEVELS = [(1, "损伤临界，不可用于设计"), (2, "THK 普通载荷下限"),
             (5, "THK 冲击载荷下限"), (7, "THK 推荐值")]


def p0_single(M, Fr, Fa, dp):
    """单只轴承的静等价径向载荷。M 单位 N·m，dp 单位 mm，返回 N。"""
    return X0 * (Fr + 2 * np.asarray(M) * 1000 / dp) + Y0 * np.asarray(Fa)


def p0_pair(M, Fr, Fa, L):
    """成对布置每只轴承的静等价径向载荷（弯矩走力偶，径向力跨中平分）。"""
    return np.asarray(M) * 1000 / L + np.asarray(Fr) / 2 + Y0 * np.asarray(Fa)


def load_timeseries():
    """从 wrench_decompose.py 导出的 CSV 读取 (M, Fr, Fa)。"""
    import csv as _csv
    with open(LOAD_CSV, encoding="utf-8-sig") as f:
        rd = _csv.reader(f)
        hdr = next(rd)
        data = np.array([[float(v) for v in r] for r in rd])
    def pick(sub):
        idx = [i for i, h in enumerate(hdr) if sub in h]
        if not idx:
            raise KeyError(f"CSV 中找不到含 '{sub}' 的列，实际列名：{hdr}")
        return data[:, idx[0]]
    return pick(COL_M), np.abs(pick(COL_FR)), np.abs(pick(COL_FA))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print("=" * 94)
    print("一、承载能力（fs=1 单一载荷极限，非设计许用值；三者不可叠加）")
    print("=" * 94)
    print(f"  {'型号':10s} {'d×D×B':15s} {'dp':>7s} {'C':>7s} {'C0':>7s} "
          f"{'许用径向':>9s} {'许用轴向':>9s} {'许用倾覆':>10s} {'质量':>7s}")
    print(f"  {'':10s} {'(mm)':15s} {'(mm)':>7s} {'(kN)':>7s} {'(kN)':>7s} "
          f"{'(kN)':>9s} {'(kN)':>9s} {'(N·m)':>10s} {'(kg)':>7s}")
    for nm, d, D, B, dp, C, C0, m in BEARINGS:
        print(f"  {nm:10s} {f'{d}×{D}×{B}':15s} {dp:7.1f} {C:7.2f} {C0:7.2f} "
              f"{C0:9.2f} {C0/Y0:9.2f} {C0*dp/2:10.1f} {m:7.3f}")

    print()
    print("=" * 94)
    print("二、设计许用倾覆力矩（纯弯矩，无径向/轴向载荷）")
    print("=" * 94)
    hdr = f"  {'型号':10s}" + "".join(f"{'fs='+str(f):>12s}" for f, _ in FS_LEVELS)
    print(hdr + "     单位 N·m")
    for nm, d, D, B, dp, C, C0, m in BEARINGS:
        line = f"  {nm:10s}" + "".join(f"{C0*dp/2/f:12.1f}" for f, _ in FS_LEVELS)
        print(line)
    for f, tag in FS_LEVELS:
        print(f"    fs={f}: {tag}")

    if PAIR_SPACING:
        L = PAIR_SPACING
        print()
        print("=" * 94)
        print(f"三、双轴承成对布置（中心距 L = {L:.0f} mm）")
        print("=" * 94)
        for nm, d, D, B, dp, C, C0, m in BEARINGS:
            arm = dp / 2
            print(f"  {nm}: 单只等效力臂 dp/2 = {arm:.2f} mm, 成对力臂 L = {L:.0f} mm, "
                  f"收益 = {L/arm:.2f}×")
            if L <= arm:
                print(f"    警告：L ≤ dp/2，成对布置不如单只，属浪费")
            print(f"    盈亏平衡跨距 L = dp/2 = {arm:.1f} mm；"
                  f"力偶/局部弯矩路径刚度相等跨距 L = dp/√2 = {dp/np.sqrt(2):.1f} mm")
            for f, _ in FS_LEVELS:
                print(f"    fs={f}: 单只 {C0*dp/2/f:7.1f} N·m -> 成对 {C0*L/f:7.1f} N·m")
        print("  注：纯力偶假设偏保守约 15%（两只轴承会分担局部弯矩），建议按此保守值取用。")

    # ------------------------------------------------------------ 载荷校核
    use_ts = LOAD_CSV is not None
    if use_ts:
        Mv, Frv, Fav = load_timeseries()
        print(f"\n载荷来源：{LOAD_CSV}（{len(Mv)} 样本）")
    print()
    print("=" * 94)
    print("四、静态安全系数校核")
    print("=" * 94)

    if use_ts:
        print(f"  {'型号':10s} {'布置':10s} {'fs中位':>8s} {'fs_p1':>7s} {'fs最小':>8s} "
              f"{'fs<5时长':>9s} {'fs<2时长':>9s} {'判定':>6s}")
        for nm, d, D, B, dp, C, C0, m in BEARINGS:
            plans = [("单只", p0_single(Mv, Frv, Fav, dp))]
            if PAIR_SPACING:
                plans.append((f"成对@{PAIR_SPACING:.0f}", p0_pair(Mv, Frv, Fav, PAIR_SPACING)))
            for tag, P0 in plans:
                fs = C0 * 1000 / P0
                ok = "合格" if np.percentile(fs, 1) >= 5 else "不合格"
                print(f"  {nm:10s} {tag:10s} {np.median(fs):8.2f} "
                      f"{np.percentile(fs,1):7.2f} {fs.min():8.2f} "
                      f"{(fs<5).mean()*100:8.1f}% {(fs<2).mean()*100:8.2f}% {ok:>6s}")
        print("\n  判定依据：第 1 百分位 fs ≥ 5（冲击载荷下限）。")
    else:
        print("  判定依据：fs ≥ 5（冲击载荷下限）。机器人关节存在落地冲击，")
        print("  即使中位工况也按冲击载荷要求，不用 fs ≥ 2。")
        for cname, M, Fr, Fa in CASES:
            print(f"\n  【{cname}】M={M} N·m, Fr={Fr} N, Fa={Fa} N")
            print(f"    {'型号':10s} {'布置':10s} {'P0(N)':>9s} {'fs':>7s} "
                  f"{'弯矩占比':>9s} {'判定':>6s}")
            for nm, d, D, B, dp, C, C0, m in BEARINGS:
                plans = [("单只", p0_single(M, Fr, Fa, dp), 2 * M * 1000 / dp)]
                if PAIR_SPACING:
                    plans.append((f"成对@{PAIR_SPACING:.0f}",
                                  p0_pair(M, Fr, Fa, PAIR_SPACING),
                                  M * 1000 / PAIR_SPACING))
                for tag, P0, mc in plans:
                    fs = C0 * 1000 / P0
                    print(f"    {nm:10s} {tag:10s} {P0:9.0f} {fs:7.2f} "
                          f"{mc/P0*100:8.1f}% {'合格' if fs>=5 else '不合格':>6s}")

    # ------------------------------------------------------------ 绘图
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5))
    fig.subplots_adjust(wspace=0.26)

    ax = axes[0]
    names = [b[0] for b in BEARINGS]
    xx = np.arange(len(names))
    w = 0.8 / len(FS_LEVELS)
    for i, (f, _) in enumerate(FS_LEVELS):
        vals = [b[6] * b[4] / 2 / f for b in BEARINGS]
        ax.bar(xx + (i - (len(FS_LEVELS) - 1) / 2) * w, vals, w, label=f"fs={f}")
    Mref = np.percentile(Mv, 99) if use_ts else CASES[min(1, len(CASES) - 1)][1]
    ax.axhline(Mref, color="k", ls="--", lw=1.6, label=f"需求 = {Mref:.0f} N·m")
    ax.set_yscale("log")
    ax.set_xticks(xx); ax.set_xticklabels(names)
    ax.set_ylabel("许用倾覆力矩 (N·m)")
    ax.set_title("单只轴承许用倾覆力矩 $M_0=C_0d_p/2\\,/\\,f_s$", fontsize=12, weight="bold")
    ax.legend(fontsize=9, ncol=2); ax.grid(alpha=0.3, axis="y", which="both")

    ax = axes[1]
    if PAIR_SPACING:
        Ls = np.linspace(10, max(200, PAIR_SPACING * 2), 300)
        for nm, d, D, B, dp, C, C0, m in BEARINGS:
            ax.plot(Ls, C0 * 1000 * Ls / 1000 / 5, lw=1.8, label=f"{nm} 成对 @fs=5")
            ax.axhline(C0 * dp / 2 / 5, ls=":", lw=1.2, alpha=0.7)
            ax.axvline(dp / 2, ls="--", lw=1.0, alpha=0.5)
        ax.axvline(PAIR_SPACING, color="magenta", lw=2.0,
                   label=f"L = {PAIR_SPACING:.0f} mm")
        ax.set_xlabel("两轴承中心距 L (mm)")
        ax.set_ylabel("许用弯矩 @fs=5 (N·m)")
        ax.set_title("成对布置许用弯矩随跨距线性增长\n"
                     "（虚线=单只同 fs 水平，竖虚线=盈亏平衡跨距 dp/2）",
                     fontsize=11.5, weight="bold")
        ax.legend(fontsize=8.5); ax.grid(alpha=0.3)
    elif use_ts:
        for nm, d, D, B, dp, C, C0, m in BEARINGS:
            ax.semilogy(C0 * 1000 / p0_single(Mv, Frv, Fav, dp), lw=0.9, label=nm)
        ax.axhline(5, color="purple", ls="-.", lw=1.2, label="fs≥5")
        ax.axhline(2, color="r", ls=":", lw=1.5, label="fs≥2")
        ax.set_xlabel("样本"); ax.set_ylabel("$f_s$")
        ax.legend(fontsize=9); ax.grid(alpha=0.3, which="both")

    fig.suptitle("交叉滚子环选型校核（THK 515-1E：$P_0=F_r+2M/d_p+0.44F_a$，$f_s=C_0/P_0$）",
                 fontsize=13.5, weight="bold", y=1.0)
    p = os.path.join(OUT_DIR, "交叉滚子环选型校核.png")
    fig.savefig(p, dpi=135, bbox_inches="tight")
    print(f"\nsaved: {p}")


if __name__ == "__main__":
    main()
