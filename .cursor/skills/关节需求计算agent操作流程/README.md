# 关节电机需求计算工具集

**作者：Limx_Kang**

---

## 概述

本工具集用于从机器人仿真数据出发，完成关节电机的选型分析全流程：

```
仿真 CSV → TN 散点图 → 效率曲线 → 需求 TN 曲线 → 输入功率 → 全身功率 → 选型建议
```

工具设计为**完全通用**，不绑定特定机器人、电机型号或工况名称，仅需修改每个脚本顶部的 `USER CONFIG` 区域即可适配新项目。

---

## 文件列表

| 文件 | 说明 |
|------|------|
| `SKILL.md` | Agent 技能描述（触发条件、工作流程摘要） |
| `scatter_abs.py` | 生成关节扭矩-速度散点图及数据 CSV |
| `plot_efficiency.py` | 绘制电机扭矩-效率曲线并导出数据 |
| `plot_required_TN.py` | 基于覆盖率推导关节需求 TN 曲线 |
| `plot_input_power.py` | 计算并绘制关节输入功率时间曲线 |
| `plot_total_power.py` | 计算全身合计输入功率堆叠图 |
| `motor_selection_analysis.py` | 关节需求与电机规格对比选型 |
| `关节性能需求梳理方法.md` | 算法细节与参数说明（供 Agent 参考） |
| `README.md` | 本使用说明文档 |

---

## 环境要求

| 依赖 | 版本要求 |
|------|---------|
| Python | ≥ 3.8 |
| numpy | 任意 |
| pandas | 任意 |
| matplotlib | 任意 |
| scipy | ≥ 1.7（需 `make_smoothing_spline`） |

安装命令：

```bash
pip install numpy pandas matplotlib scipy
```

---

## 输入数据格式

### CSV 文件结构

每个仿真工况对应一个 CSV 文件，列格式如下：

```
time_s, torque_<关节列名>, vel_<关节列名>, ...
```

示例列名：

```
time_s, torque_left_hip_pitch_joint, vel_left_hip_pitch_joint,
        torque_right_hip_pitch_joint, vel_right_hip_pitch_joint, ...
```

- `time_s`：时间（秒），通常步长约 0.001 s
- `torque_*`：关节扭矩（N·m）
- `vel_*`：关节角速度（rad/s）

### 多工况组织方式

将不同工况的 CSV 路径填入字典，**标签可自定义**：

```python
CSV_FILES = {
    "工况A": r"D:\data\scenario_a\joint_data.csv",
    "工况B": r"D:\data\scenario_b\joint_data.csv",
}
```

---

## 使用步骤

### 第一步：生成 TN 散点图

**脚本：** `scatter_abs.py`

**修改 USER CONFIG：**

```python
CSV_FILES = {
    "工况标签": r"<CSV文件路径>",
}

OUT_DIR = Path(r"<输出根目录>") / "TN散点图"

JOINTS = [
    ("关节显示名", "左侧列名后缀", "右侧列名后缀"),
    # 例：("hip_pitch", "left_hip_pitch_joint", "right_hip_pitch_joint")
]

TORQUE_SCALE = {
    "关节名": 1.0,   # 有传动比折算时修改此系数
}
```

**输出：** 每个工况一个子文件夹，包含各关节散点 PNG 和汇总 `TN_scatter_data.csv`。

---

### 第二步：绘制效率曲线

**脚本：** `plot_efficiency.py`

从电机数据手册或效率测试图中读取数据点，填入配置：

```python
EFFICIENCY_CURVES = {
    "效率曲线名称": {
        "torque":         [0.5, 1.4, 2.3, ...],   # 扭矩点 (Nm)
        "efficiency_pct": [30,  55,  65,  ...],    # 对应效率 (%)
        "lam":   1.2,       # 平滑系数（越大越平滑，建议 0.5~2.0）
        "color": "#2563EB", # 曲线颜色（hex）
    },
    # 可同时定义多条
}
```

**输出：** 效率曲线对比 PNG，以及每条曲线的原始数据和平滑数据 CSV。

---

### 第三步：推导需求 TN 曲线

**脚本：** `plot_required_TN.py`

基于二分法找到满足覆盖率要求的最小额定扭矩：

```python
CSV_FILES  = { ... }   # 参与分析的工况（可合并多个）
JOINTS     = [ ... ]   # 参与分析的关节
TORQUE_SCALE = { ... }

N_BASE   = 60.0    # 额定转速 (RPM)
N_MAX    = 150.0   # 最高转速 (RPM)
COV_CONT = 0.85    # 连续工作区间覆盖率（推荐 0.80~0.90）
COV_PEAK = 0.98    # 短时工作区间覆盖率（推荐 0.95~0.99）

TITLE = "本次分析描述"
```

**覆盖率说明：**

| 设置 | 含义 |
|------|------|
| `COV_CONT = 0.85` | 连续额定扭矩需覆盖 85% 的仿真工作点 |
| `COV_PEAK = 0.98` | 峰值扭矩需覆盖 98% 的仿真工作点 |

**输出：** 需求 TN 曲线 PNG，控制台打印额定扭矩、额定功率、峰值扭矩、峰值功率。

---

### 第四步：计算关节输入功率

**脚本：** `plot_input_power.py`

```python
EFF_TORQUE   = np.array([...])        # 效率数据：扭矩点 (Nm)
EFF_VALS     = np.array([...]) / 100  # 效率数据：效率值 (%)→小数
EFF_LAM      = 1.2                    # 平滑系数
EFF_MIN      = 0.03                   # 效率下限（防止功率无穷大）
STALL_TORQUE = 42.0                   # 估算堵转扭矩 (Nm)
```

若不同关节需要使用不同效率曲线：

```python
EFF_OVERRIDE = {
    "ankle_pitch": {
        "torque": [...],
        "eff":    [...],
        "lam":    0.8,
        "eff_min": 0.25,
        "stall":  13.5
    }
}
```

**输出：** 每个关节×每个工况一张四子图（扭矩 / 转速 / 效率 / 输入功率时间图），控制台打印 RMS 功率汇总表。

> **饱和点（`*` 标注）：** 仿真扭矩超出效率数据范围时，程序用线性外推估算效率，该点被标记为饱和点，`RMS清洁` 为排除饱和点后的保守估计值。

---

### 第五步：全身合计功率

**脚本：** `plot_total_power.py`

```python
# 定义效率曲线（支持多条，格式同 plot_efficiency.py）
EFFICIENCY_DEFS = {
    "大扭矩关节": { "torque": [...], "eff": [...], "lam": 1.2, "eff_min": 0.03, "stall": 42.0 },
    "小扭矩关节": { "torque": [...], "eff": [...], "lam": 0.8, "eff_min": 0.25, "stall": 13.5 },
}

# 指定各关节使用哪条效率曲线
JOINT_EFF_MAP = {
    "hip_pitch":   "大扭矩关节",
    "ankle_pitch": "小扭矩关节",
    # 未列出的关节默认使用第一条
}
```

**注意：** 本脚本对每个关节**左右两侧均计入**（`for jcol in [jL, jR]`），得到双侧总功率。

**输出：** 每个工况一张堆叠面积图（各关节贡献）+ 合计折线图，控制台打印 RMS 和峰值功率。

---

### 第六步：电机选型分析

**脚本：** `motor_selection_analysis.py`

```python
MOTOR_SPECS = {
    "电机选项名称": {
        "rated_nm":  7.0,    # 额定扭矩 (Nm)
        "rated_rpm": 60,     # 额定转速 (RPM)
        "peak_nm":   20.0,   # 短时峰值扭矩 (Nm)
        "peak_rpm":  120,    # 峰值转速 (RPM)
        "color":     "#2563EB",
    },
    # 添加所有候选电机
}
```

**选型逻辑：** 遍历电机选项，找到第一个同时满足 `T_cont ≤ rated_nm` 且 `T_peak ≤ peak_nm` 的选项。

**输出：** 控制台打印选型建议表，输出各关节需求点与所有候选电机 TN 曲线的对比 PNG。

---

## 参数调优建议

### 覆盖率设置

| 应用场景 | `COV_CONT` | `COV_PEAK` |
|---------|-----------|-----------|
| 严格选型（高可靠性） | 0.90 | 0.99 |
| 标准选型 | 0.85 | 0.98 |
| 宽松选型（成本优先） | 0.75 | 0.95 |

### 效率样条平滑系数 `lam`

| `lam` 值 | 效果 |
|---------|------|
| 0.3~0.8 | 曲线紧贴原始数据，保留局部波动 |
| 1.0~1.5 | 标准平滑，推荐默认值 |
| 2.0 以上 | 高度平滑，趋近整体趋势 |

### 堵转扭矩 `STALL_TORQUE`

用于超出效率曲线范围时的线性外推。若不清楚实际堵转扭矩，可取效率数据最大扭矩的 **1.5~2 倍**作为估算值。设置偏小会使超范围点的效率下降更快（输入功率估算偏大），选型更保守。

### 扭矩缩放 `TORQUE_SCALE`

适用于存在**减速比**或**力矩传递系数**的关节：

```python
# 例：电机通过 0.6 倍传动系数驱动关节
TORQUE_SCALE = { "ankle_pitch": 0.6 }
```

---

## 常见问题

**Q：运行时报 `KeyError: 'torque_left_xxx'`？**
A：检查 CSV 文件中实际列名，确保 `JOINTS` 中填写的后缀与列名完全匹配。

**Q：效率曲线出现负值或超过 100%？**
A：增大 `lam` 平滑系数，或检查原始数据是否存在异常点。

**Q：RMS 输入功率异常偏大（数倍于输出）？**
A：存在扭矩饱和点（仿真扭矩超出效率数据范围），参考控制台输出的 `RMS清洁` 值，并检查 `STALL_TORQUE` 设置是否合理。

**Q：`make_smoothing_spline` 报错？**
A：升级 scipy：`pip install --upgrade scipy`（需 ≥ 1.7）。

**Q：中文图表显示方框？**
A：Windows 默认已有微软雅黑，若在 Linux/Mac 运行需替换字体：
```python
matplotlib.rcParams['font.family'] = 'SimHei'  # Linux
matplotlib.rcParams['font.family'] = 'Arial Unicode MS'  # macOS
```

---

## 扩展指南

### 增加新工况

在所有脚本的 `CSV_FILES` 字典中添加一行即可，无需修改其他代码：

```python
CSV_FILES = {
    "工况A": r"路径A",
    "工况B": r"路径B",
    "新增工况": r"新路径",   # ← 添加这一行
}
```

### 增加新关节

在 `JOINTS` 列表中添加一行：

```python
JOINTS = [
    ...
    ("新关节名", "left_新关节_joint", "right_新关节_joint"),
]
```

### 分析单侧关节（无左右）

将左右列名填为相同值：

```python
JOINTS = [
    ("waist_pitch", "waist_pitch_joint", "waist_pitch_joint"),
]
```

---

## 相关文档

- 技能触发条件与工作流程摘要见 [SKILL.md](SKILL.md)
- 完整算法细节与参数速查表见 [关节性能需求梳理方法.md](关节性能需求梳理方法.md)

---

*作者：Limx_Kang*
