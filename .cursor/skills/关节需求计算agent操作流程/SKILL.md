---
name: joint-motor-requirement-analysis
description: >-
  从仿真 CSV（含 time_s、torque_*、vel_* 列）计算机器人各关节的连续/短时扭矩与功率需求，
  推导需求 TN 曲线（梯形模型、按覆盖率二分），对比电机规格给出选型建议，并生成扭矩-速度散点、
  TN 曲线、效率曲线、输入功率/合计功率等对比图。当用户需要做关节电机选型、关节扭矩/转速/功率
  需求分析、TN 曲线、减速比复核或处理仿真导出的关节 CSV 时使用。
---

# 关节需求计算 / 电机选型操作流程

本技能用于从仿真导出的关节数据（CSV，含 `time_s`、`torque_<joint>`、`vel_<joint>` 列）
分析关节扭矩/转速/功率需求并完成电机选型。所有脚本顶部都有 `USER CONFIG` 区域，
使用前必须修改其中的 CSV 路径、输出目录、关节列表、电机规格等占位符。

## 工作流程

1. **明确输入**：确认仿真 CSV 路径、要分析的关节（左右两侧列名）、工况划分。
2. **散点摸底**：运行 `scatter_abs.py` 生成各关节 |扭矩(Nm)| vs |速度(RPM)| 散点图并导出散点 CSV。
3. **需求 TN 曲线**：运行 `plot_required_TN.py`，用梯形 TN 模型 + 二分法求满足指定覆盖率的最小 T_flat。
4. **电机选型**：运行 `motor_selection_analysis.py`，计算连续(COV_CONT)/短时(COV_PEAK)扭矩需求，
   与 `MOTOR_SPECS` 中候选电机对比，打印选型表并绘制需求点 vs 电机 TN 曲线对比图。
5. **功率/效率分析（可选）**：
   - `plot_efficiency.py`：绘制电机扭矩-效率曲线（spline 平滑）。
   - `plot_input_power.py`：单关节输入功率时间曲线 `P_in = |tau×vel| / η(|tau|)`。
   - `plot_total_power.py`：全身关节合计输入功率时间曲线 + 堆叠面积图，打印 RMS/峰值功率。

## 脚本说明

| 脚本 | 作用 |
|------|------|
| `scatter_abs.py` | 关节 × 工况的 \|扭矩\| vs \|速度\| 散点图与散点数据 CSV |
| `plot_required_TN.py` | 由仿真数据推导关节需求 TN 曲线（梯形模型，二分覆盖率） |
| `motor_selection_analysis.py` | 连续/短时扭矩需求计算 + 电机选型建议 + TN 对比图 |
| `plot_efficiency.py` | 电机扭矩-效率曲线绘制与导出 |
| `plot_input_power.py` | 单关节输入功率时间曲线（四子图：扭矩/转速/效率/功率） |
| `plot_total_power.py` | 全身合计输入功率时间曲线与堆叠面积图 |

## 关键约定

- 运行前务必编辑脚本顶部 `USER CONFIG`：替换 `<输出目录>`、`<CSV路径>` 等占位符。
- 覆盖率参数：`COV_CONT`（连续，默认 0.85）、`COV_PEAK`（短时，默认 0.98）。
- TN 曲线参数：`N_BASE`（额定转速）、`N_MAX`（最高转速）。
- 依赖 `numpy`、`pandas`、`matplotlib`；中文绘图字体使用 `Microsoft YaHei`。
- 生成的图片/CSV 按工作区规则放入 `cursor生成文件/` 下的任务子文件夹。
- 输入 CSV 可由 `D:\WorkFiles\mujoco_ws` 的 `controller.py` 直接产出，列名已对齐，
  无需转换（见「MuJoCo仿真工作区记录」）。

## 详细参考

- 完整操作步骤见 [关节性能需求梳理方法.md](关节性能需求梳理方法.md)
- 背景与总体说明见 [README.md](README.md)
