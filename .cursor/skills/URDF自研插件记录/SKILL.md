---
name: urdf-self-developed-plugin-notes
description: >-
  Engineering memory ("URDF自研插件记录") for the URDF_Studio_Limx_KKS desktop app
  (SolidWorks→URDF exporter, author limx_Kang). Use when working on this project:
  reading overridden mass/COM/inertia via SolidWorks COM, building URDF trees,
  exporting per-link STL meshes, generating sw2urdf-style ROS packages, or
  packaging the app. Records key decisions, COM pitfalls, and conventions.
---

# URDF自研插件记录

独立 Windows 桌面工具 URDF_Studio_Limx_KKS（**非插件**），直连 SolidWorks，替代 sw2urdf 的
step6–step10：直接读取每个 link 子装配体"覆盖后"的质量/质心/惯量，可视化构建 URDF 树，
导出与 sw2urdf 同构的 ROS 包（URDF + STL + csv/config/launch）。作者 **limx_Kang**。

- 源码目录：`d:\WorkFiles\Cursor\URDF_Studio\`
- 发布目录：`D:\WorkFiles\2026.6\Limx KKS URDF导出工具制作\URDF_Studio_Limx_KKS_versionX.Y\`
- 参考模型(sw2urdf 真值)：`D:\WorkFiles\2026.6\URDF自研插件测试模型\HU_M01_01_URDFfiles\`
- 当前版本：**v0.4**

> 本文件是该项目的"长期记忆"，后续每次有新决策/修复都应**追加更新**这里。

## 源码文件职责

| 文件 | 职责 |
|---|---|
| `main.py` | 入口 |
| `app.py` | Tkinter GUI（三大模块：模型读取 / URDF 树构建 / URDF 导出）；`VERSION` 常量 |
| `com_core.py` | SW COM 连接 + 主 API 早绑定 + **swconst 常量加载** + 选择/byref 辅助 |
| `com_worker.py` | STA COM 线程（所有 COM 调用须在此线程内） |
| `model_reader.py` | 遍历装配体顶层组件→link；坐标系/参考轴/覆盖质量属性；转 base 相对值 |
| `mass_props.py` | 读 `IMassProperty2` 覆盖后质量属性（SI：米/千克） |
| `geometry.py` | 坐标变换、旋转矩阵↔RPY、逆变换 |
| `joint_data.py` | `.urdfproj` 工程数据、URDF 树、自动构建、`exports_dir()`(=`output/`) |
| `postprocess.py` | 轴归正、镜像惯量、角度→弧度、命名/结构校验 |
| `exporter.py` | 生成 URDF/CSV、写完整 ROS 包结构、COM 导出 STL |
| `theme.py` | 浅灰+白简约 ttk 主题 |
| `make_icon.py` | PNG→简笔画 app.ico（`--sketch` 默认） |
| `build_and_package_vX.Y.ps1` | 一键：生图标→PyInstaller→拷贝到发布目录 |

## SolidWorks COM 关键经验（踩坑总结）

1. **必须早绑定**：纯后期绑定 `Dispatch` 解析不到 `CreateMassProperty` 等成员
   (DISP_E_MEMBERNOTFOUND)。用 `gencache.EnsureModule` 生成主 API 类型库
   (GUID `{83A33D31-27C5-11CE-BFD4-00400513BB57}`)，再用 `com_core.wrap(obj, "IXxx")`
   按接口名包裹原始 `_oleobj_`。版本号 major 从注册表 TypeLib 读（十六进制→十进制，
   SW2021=29）。冻结 exe 需把 `win32com.__gen_path__` 指到可写的 LOCALAPPDATA。
2. **枚举常量不要硬编码**：用 `com_core.get_sw_const()` 加载 swconst 类型库
   (GUID `{4687F359-55D0-4CD3-B6CF-2EB42C11F989}`)，按名取值；`com_core.const(name, default)`
   带内置回退。已知值：`swExportStlUnits=211`、`swMETER=2`、`swSTLQuality=78`、
   `swSTLQuality_Coarse=1`、`swSTLBinaryFormat=69`、`swSTLComponentsIntoOneFile=72`。
3. **覆盖质量属性**：组件被用户"覆盖"质量属性后，读 `comp.GetModelDoc2` 的
   `IMassProperty2`（含 override），返回值是 SI（米、千克），与文档显示单位无关。
4. **坐标系**：link 坐标系命名约定 `{去掉_link的词干}_sys`（如 `waist_B_cp_link`→
   `waist_B_cp_sys`）。`Extension.GetCoordinateSystemTransformByName` **区分大小写**；
   先精确匹配，再小写、再模糊包含匹配（解决 `base_link`→`Base_sys` 大小写不一致）。
5. **参考轴**：特征名 `{词干}_axis`，`IRefAxis.GetRefAxisParams()` 两端点求方向。
6. **byref 参数**：用 `com_core.make_byref_long()`(`VARIANT(VT_BYREF|VT_I4)`)。
7. **空 dispatch 参数传 `NULL_CALLOUT`（`VARIANT(VT_DISPATCH, None)`），不要传 Python
   `None`** —— 否则 `DISP_E_TYPEMISMATCH(-2147352571, "类型不匹配")`。
8. 沙箱：从源码运行 GUI 须用关闭沙箱的方式（`required_permissions: ["all"]`），
   否则报 `Sandbox policy 'workspace_readwrite' not supported`。

## Mesh 导出（核心，复刻 sw2urdf）

目标：每个 link 的 STL = **该 link 子装配体** 的几何，表达在 **该 link 的 `{link}_sys`** 坐标系下。

实现（`exporter.export_meshes`，在 COMWorker 线程内）：

1. 设全局 STL 偏好：`swSTLBinaryFormat=True`、`swSTLDontTranslateToPositive=True`、
   `swSTLShowInfoOnSave=False`、`swSTLPreview=False`、`swSTLComponentsIntoOneFile=True`、
   `swExportStlUnits=swMETER`、`swSTLQuality=Coarse`。
2. 取 `SelectionManager.CreateSelectData()` 得 `SelectData`。
3. 逐 link：**选中其余顶层组件并 `HideComponent2()`**（仅保留该 link 子装配体可见，
   目标始终可见以保留其子件）→ 设输出坐标系 → `SaveAs3` 导出 → 复原可见性。
4. 选中用 **`Component2.Select4(True, sel_data, False)`**（对象引用，隐藏后仍可选中）；
   回退顺序：SelectData → NULL_CALLOUT → `Extension.SelectByID2(name,"COMPONENT",...)`。
5. 输出坐标系：`app.SetUserPreferenceStringValue(swExportOutputCoordinateSystem, cs)`
   （同时设 `swFileSaveAsCoordinateSystem` 兜底）。
6. 导出：`doc.Extension.SaveAs3(path, ver, Silent|Copy, NULL_CALLOUT, NULL_CALLOUT, errs, warns)`。
   `Copy` 选项防止把活动装配体改名为 .STL。
7. 导出后清零 STL 80 字节文件头（`_correct_stl_header`），兼容性更好。

**两个曾导致"导出整机"的 bug（已修，勿回退）：**
- ❌ `comp.Visible = 0/1` 设可见性 **无效（空操作）** → 全可见 → 整机。
- ❌ `Select4` 第二参数传 `NULL_CALLOUT` 常抛异常被静默吞掉 → 选中 0 个 → 没隐藏 → 整机。
  正解：用 `SelectData` 对象 + 对象引用选中，并打印 `已选其余 X 个组件, 隐藏=成功`。

## URDF / 包结构约定

- **robot name = 包名**；URDF 文件名 = `<包名>.urdf`，CSV = `<包名>.csv`。
- **mesh 以米导出 → URDF `<mesh>` 不带 `scale` 属性**（与 sw2urdf 一致）。
- link 几何/COM/惯量/joint origin **统一表达在该 `{link}_sys`**；visual/collision
  `<origin>` 恒为 `0 0 0`（这就是 URDF 规则的核心：四者同参考系、自洽）。
- joint origin = 子 `*_sys` 相对父 `*_sys` 的位姿；fixed 关节也输出 `<axis xyz="0 0 0"/>`。
- 默认材质灰 `rgba="0.75294 0.75294 0.75294 1"`；每个 link 都有 collision 块。
- 完整包结构（`exporter.write_package` 复刻参考文件夹）：
  ```
  <包名>/ package.xml  CMakeLists.txt  export.log  <包名>.urdfproj
    ├ config/  joint_names_<包名>.yaml        (controller_joint_names: ['', ...])
    ├ launch/  display.launch  gazebo.launch
    ├ meshes/  <link>.STL                     (仅"导出 URDF + mesh"时)
    ├ textures/
    └ urdf/    <包名>.urdf   <包名>.csv        (CSV 60 列，结构对齐 sw2urdf)
  ```
- 导出按钮：**「仅导出 URDF(不含 mesh)」**(`force_no_mesh=True`) 与 **「导出 URDF + mesh」**。

## 数据精度

| 项 | 精度/约定 |
|---|---|
| 质量 | 0.001 kg |
| 质心 | 1e-8 m |
| 惯量 | 固定 8 位小数 kg·m² |
| 坐标系位姿(显示) | 8 位，尾随 0 省略 |
| 关节角度限位 | 录入为度，导出 URDF 转 4 位弧度；prismatic 录入为米 |
| 转轴 | 归正（绝对值最大分量取正） |

## 刻意"不改"的项（用户要求忽略，勿擅自修复）

1. 转轴符号归正（与 sw2urdf 个别关节 `0 0 -1` 不同，保持归正）。
2. 关节 effort/velocity 默认 0、限位默认 ±1.5708。
3. 质量四舍五入到 0.001（与 sw2urdf 更高精度不同）。
4. 根 link 名 `Base_link`（大写 B，sw2urdf 用小写 `base_link`）。

## 构建/打包与验证

- 从源码跑（验证用，GUI）：`python main.py`（须关沙箱）。改了 `.py` 需**重启**应用。
- 打包：`powershell -ExecutionPolicy Bypass -File .\build_and_package_vX.Y.ps1`，
  成功输出 `PACKAGE_OK vX.Y`。
- 终端有时无响应/被沙箱拦截：用 `required_permissions:["all"]` 后台运行，读
  `terminals/<id>.txt` 看输出。
- 导出后验证：把包丢进 RViz / `display.launch`，所有关节为 0 时整机应严丝合缝拼合、
  无错位穿模；否则多为该 link 的 `*_sys` 没建在关节处（建模问题，非工具）。

## 版本历史

- **v0.4** — mesh 重构复刻 sw2urdf（隐藏其余组件+输出坐标系+米/低精度+清STL头，正确得
  "子装配体+link坐标系"）；URDF 去 `scale`、robot name=包名；新增"仅导出 URDF"；
  补全 sw2urdf 同构 ROS 包（csv/config/launch/package.xml/CMakeLists/export.log/textures）。
  修复 `SaveAs` 传 None 的类型不匹配、`comp.Visible` 与 `Select4` 选择失败两个"整机"bug。
- **v0.3** — 表内双击直接编辑；树拖拽高亮+同级/子级；URDF 对齐示例(注释头/material/
  collision/fixed axis)；导出目录改名 `output`；图标简笔画。
- **v0.2** — URDF 树自动构建+拖拽、URDF 导出模块、临时保存、浅灰白主题+图标。
- **v0.1** — 模型读取、手动编辑、URDF 树构建、JSON 导出。
