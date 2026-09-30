# 精简分发与精确增量更新 — 设计文档

- 日期：2026-09-30
- 状态：已实现；稳定性问题已定位并修复（见 4.1）；CI 改为只负责发布（见 `docs/RELEASING.md`）
- 起点：v1.3.0 已发布，main @ 4a3300b（含窗口图标修复与 CI 超时加固，尚未发版）
- 前置：`2026-09-28-layered-distribution-design.md`（分层分发的基础机制）

## 1. 背景

分层分发已经上线（v1.3.0），日常更新从 1536 MB 降到 75 MB。但两个问题暴露出来：

**一、runtime id 过于敏感，把不该全量的更新判成了全量。** v1.3.1 只修了一个窗口图标的
bug，却要求所有用户重新下载 1536 MB。原因是 runtime id 哈希 `packaging/labeling_tool.spec`
**全文**，而那次改动只是在 `datas` 里加了图标路径 —— 与运行时层毫无关系。

**二、75 MB 的应用层里，真正属于我们的代码不到一成。** 实测构成：

| 组成 | 大小 | 是否随代码改动 |
|---|---|---|
| MobileSAM ONNX 模型 | 42.4 MB | 否，预训练权重几乎永不变 |
| exe 内嵌的 PYZ | 约 38 MB | 其中绝大部分是 torch / PyQt5 / numpy 自己的 `.py` 字节码 |
| 我们自己的代码 | 约 1 MB | 是 |

也就是说，改一行 Python 代码要投送 75 MB，其中 74 MB 是没有变化的东西。

## 2. 目标

- 只改 Python 代码时，更新包降到个位数 MB。
- 修改 `spec` 中与运行时层无关的部分（图标、应用层数据文件）不再触发全量重装。
- 在不牺牲可验证性的前提下，削减首次安装包体积。

**非目标**：不做文件级差分更新器。它能再小一个数量级，但要自行处理替换失败、断电中断、
回滚，以及替换正在运行的 exe —— 这些在第二期已评估并放弃，结论不变。

## 3. 已确认的决策

| 项 | 决策 | 放弃的备选与理由 |
|---|---|---|
| 增量粒度 | B 档：`noarchive=True` + ONNX 移入运行时层，应用包约 5 MB | A 档（仅移 ONNX，约 40 MB）不解决 exe 里夹带第三方字节码的问题；C 档（自建差分更新器）复杂度与风险远超收益 |
| runtime id 来源 | 运行时层文件的「相对路径 + 大小」清单 | 继续哈希 `spec` 全文：无法区分图标路径与 `collect_all` 的区别；抽取 spec 中的运行时配置到独立文件：仍需人工判断哪些配置算运行时相关，而清单法直接测量结果 |
| 体积精简 | 只排除确定不用的 `nvidia.nccl` 与 `nvidia.cuda_cupti` | 激进裁剪（cufft/cusparse/cusolver/curand/nvrtc，约 950 MB）：CI 没有 GPU，验证不了真实推理，只能靠人工真机验收，本期不做 |

## 4. runtime id：测量运行时层，而非推断

```
runtime id = "r" + sha256(每个运行时层文件的 "<相对路径>\0<字节数>\0"，按路径排序)[:8]
```

第二期曾用「哈希构建产物内容」，因 PyInstaller 产物不可重现而废弃（CI run 36421966949 与
36424404832 对同一提交得出 `ra9adeaed` 与 `r138b837f`）。不可重现的是文件**内容**——
时间戳被写入其中；**路径与大小不受影响**，因此清单法既稳定又直接反映运行时层的实际构成。

相较于哈希依赖清单，清单法不需要判断「哪些配置影响运行时层」：

| 场景 | 清单会变 | 期望行为 |
|---|---|---|
| 升级 torch、更换 CUDA | 是 | 全量重装 |
| 新增第三方依赖 | 是 | 全量重装 |
| 排除 nccl / cupti | 是 | 全量重装 |
| 修改 spec 的图标路径 | 否 | 增量更新 |
| 仅修改 Python 代码 | 否 | 增量更新 |

接口相应变化：`compute_runtime_id(dist_dir: Path) -> str`，参数从「仓库根 + pip freeze 文本」
变为「构建产物目录」。`pip freeze` 不再参与——依赖版本的任何变化都会体现在运行时层的文件清单上
（新增/删除文件，或文件大小改变），无需单独采集。CI 相应简化：不再需要 `pip freeze > runtime-freeze.txt`。

**实现的第一步必须验证稳定性**：同一提交连续构建两次，两次的 runtime id 必须相同。若不
相同，说明路径或大小仍受构建过程影响，退回第二期的方案（哈希 `pip freeze` 与
`packaging/labeling_tool.spec`），并在 ledger 中记录实测数据。

### 4.1 稳定性验证的实测结果

同一提交共构建了四次 CI 和两次本地：

| 构建 | 环境 | runtime id |
|---|---|---|
| CI 36673458395 | 镜像 20260922.246.2 | `ra7115365` |
| CI 36675906669 | 镜像 **20260925.250.1** | `r7c92a36d` |
| CI 36679103375 / 36679106493（并行） | 镜像 20260922.246.2 | `ra7115365`（8082 个文件，清单逐行一致） |
| 本地两次 | 同一 VM | `r678b0538`（两次一致） |

**PyInstaller 构建本身是确定的**，问题不在清单法。id 变动来自构建环境泄漏进了运行时层，
有两个来源：

1. **构建机的系统 DLL**：`_internal/` 顶层的 47 个文件（`api-ms-win-*`、`ucrtbase`、
   `vcruntime140*`、`msvcp140*`，共 3 MB），PyInstaller 从构建机的 Windows 或 SDK 里收集，
   大小随 runner 镜像变化。GitHub 每周更新镜像。
2. **未锁定的依赖和 runner 预装的包**：CI 直接用 runner 自带的 Python，里面预装的 `filelock`
   （4.0.1，本地全新 venv 解析出的是 3.32.3）、`packaging`、`argcomplete` 被打包进去，
   版本随镜像变化。

因此不回退到第二期的方案，而是堵住这两处泄漏：

- runtime id 排除构建机的系统 DLL（`layers.is_build_machine_file`，只匹配 `_internal/` 的
  直接子文件；PyQt5 wheel 自带的同名 DLL 仍然计入）。这些文件照常随完整包发布。
- 新增 `packaging/build-lock.txt`，锁定全部 52 个依赖的版本，本地与 CI 共用。
- CI 改为在全新的 venv 里构建。

第一次演练（CI 36682820480）时本地和 CI 仍差 5 个文件：sam2 仓库里的 `sam2/sam2_hiera_*.yaml`
是符号链接，runner 上的 git 会展开它们，本地 git 默认 `core.symlinks=false`，只写出 30 字节的
占位文件。两边都显式设置 `core.symlinks=true` 之后，**本地与 CI 的 runtime id 一致（`r88c8d3f0`）**，
发布前就能在本地确认这次是增量更新还是完整安装。
CI 每次还会上传 `runtime-manifest`（id 所依据的清单）作为诊断产物，id 意外变化时可以直接 diff。

## 5. 应用层瘦身

### 5.1 `noarchive=True`

`Analysis(..., noarchive=True)` 使纯 Python 模块以 `.pyc` 文件散落在 `_internal/` 下各自的
包目录中，而非压缩进 exe 内嵌的 PYZ。已用最小样例验证目录形态：

```
_internal/mypkg/__init__.pyc     ← 自有包独立成目录
_internal/mypkg/core.pyc
_internal/abc.pyc                ← 标准库散落在顶层
exe                              ← 0.09 MB，仅余引导程序
```

套用到本项目，分层归属自然成立，无需修改现有白名单逻辑：

| 路径 | 层 |
|---|---|
| `_internal/labeling_tool/**.pyc` | 应用层 |
| `_internal/annotation_tool/**.pyc` | 应用层 |
| `_internal/torch/**.pyc`、`PyQt5/`、`numpy/`、标准库 | 运行时层 |
| `LM_LabelingTool.exe` | 应用层（仅引导程序，数百 KB） |

**代价**：`_internal` 将新增上万个小文件（torch 的每个 `.py` 各成一个 `.pyc`）。需验证三项：
应用启动速度、sam2 的 hydra 配置能否正常解析（它在运行时按路径查找 yaml）、Inno 编译耗时
是否显著增加。前两项由 CI 既有的 `--selftest=full` 与启动冒烟测试覆盖，第三项观察构建时长。

### 5.2 ONNX 模型移入运行时层

MobileSAM 的两个 ONNX 文件共 42.4 MB，是固定的预训练权重，归运行时层；若日后更换模型，
那一次走全量重装，这与「更换大文件即全量」的原则一致。

**实现时的修正**：最初的方案是保留模型在 `_internal/labeling_tool/models/`，再用
`APP_LAYER_EXCLUSIONS` 把它排除出应用层。CI run 36670089766 证明这行不通：应用包安装前，
`installer.iss` 会整体清空 `{app}\_internal\labeling_tool`（以此清除已删除模块留下的旧
`.pyc`），而模型已不在应用包里，被删后无从恢复，安装应用包后自检报
`MobileSAM ONNX models: FileNotFoundError`。

最终做法：冻结构建把模型放在包**旁边**的 `_internal/models/sam/`，运行时通过
`app_paths.bundled_path()` 定位；源码目录不变。`APP_LAYER_EXCLUSIONS` 因此为空，并规定它
**永远不得**指向 `_internal/labeling_tool/` 下的任何路径——那恰好描述了这次的 bug：运行时层
文件放在了应用安装器会清空的目录里。`test_nothing_runtime_layer_lives_under_the_cleared_directory`
强制这一约束。

### 5.3 预期结果

应用层 ≈ 自有代码的 `.pyc`（约 1 MB）+ 引导程序（数百 KB）+ 少量数据文件，压缩后个位数 MB。

**实测**（CI run 36673458395，提交 `9a2f234`）：

| 项 | 第二期 | 本期 |
|---|---|---|
| 应用层（未压缩） | 81 MB | **0.9 MB，86 个文件** |
| 构建产物总量 | — | 4097.7 MB |

应用层只占构建产物的 0.02%，好于「个位数 MB」的目标。CI 的 20 MB 护栏留有 20 倍余量。

`noarchive` 的三项代价实测：

- hydra 配置解析：`--selftest=full` 的 `SAM2 hydra config composes` 在装完整包、再叠加应用包
  之后都通过。
- 启动：启动冒烟测试（登录界面保持 20 秒）通过。
- Inno 编译：完整包 337.6 秒（快速压缩）。上万个小文件没有让打包明显变慢；整轮 CI 18.5 分钟，
  基线是 22 分钟。安装完整包耗时约 3.5 分钟。

## 6. 排除确定不用的 CUDA 库

`spec` 的 `excludes` 增加：

- `nvidia.nccl` — 240 MB，多 GPU 间集合通信。本工具是单机单卡推理，不存在调用路径。
- `nvidia.cuda_cupti` — 43 MB，CUDA Profiling Tools Interface，性能分析器使用。

合计 283 MB 未压缩，预计安装包减少约 100 MB。

**实测**：排除后 `import torch`、`import sam2.*` 与 hydra 配置组合全部通过（CI run
36673458395）。安装包体积只能在打 tag 的构建上测量：验证构建使用快速压缩，体积不代表发布
版本。v1.4.0 发布时从 release 资产读取，并对照第二期的 1536 MB 写回此处。

**验证边界必须明确**：GitHub runner 无 GPU，CI 的自检只能证明 `import torch`、`import sam2`
与 hydra 配置组合不受影响，**无法验证真实推理**。这两个库的用途明确且与单机推理无交集，
故判定为安全；更激进的裁剪（cufft / cusparse / cusolver / curand / nvrtc，约 950 MB）需要
在真实 GPU 机器上完整跑一遍 few-shot 标注流程才能确认，本期不做。

## 7. 发布影响

本次改动必然改变 runtime id（运行时层新增上万个 `.pyc`、移入 ONNX、排除两个 CUDA 库），
因此**发布后需要一次全量重装**。这是算法切换的一次性成本。

此后进入稳定状态：只改 Python 代码的版本，runtime id 不变，用户收到个位数 MB 的更新。

v1.3.1 已因本设计撤回（标签已删除，未产出 release）。窗口图标修复与 CI 超时加固已在 main
上，将随本次改动一并发布。

## 8. 风险

| 风险 | 影响 | 应对 |
|---|---|---|
| 运行时层的路径+大小清单不稳定 | runtime id 每次构建都变，增量更新失效 | 实现第一步即验证：同一提交构建两次比对。不稳定则退回哈希 `pip freeze` + `spec` |
| `noarchive` 破坏 sam2 的 hydra 配置解析 | few-shot 工具无法启动 | CI 的 `--selftest=full` 会组合 hydra 配置，失败即暴露 |
| `noarchive` 显著拖慢启动 | 用户体验劣化 | CI 的启动冒烟测试观察；若明显变慢，放弃 `noarchive`，退回 A 档（仅移 ONNX，约 40 MB） |
| 上万个小文件拖慢 Inno 编译 | CI 时长增加 | 观察构建耗时；固实压缩对小文件反而有利，预期影响有限 |
| 排除的 CUDA 库实际被用到 | 真实 GPU 上推理崩溃，CI 无法发现 | 仅排除用途明确无交集的两个；发布后由用户在真机跑一遍 few-shot 流程确认 |

## 9. 测试

- `compute_runtime_id` 的单元测试改为基于文件清单：路径变化、大小变化、新增/删除文件均改变 id；
  文件**内容**变化但路径与大小不变时 id 不变（这是有意的取舍，需显式测试以表明它是设计而非缺陷）。
- `is_app_layer` 的排除规则测试：`_internal/labeling_tool/models/x.onnx` 属运行时层，
  而 `_internal/labeling_tool/app.pyc` 仍属应用层。
- CI 新增：同一构建内连续两次计算 runtime id 并断言相同（廉价的稳定性回归）。
- CI 记录并打印应用层实测体积，便于回归时发现意外膨胀。
- 全量测试套件保持绿（起点基线 449；实现完成后本地 464，CI 463 通过、1 个跳过）。

## 10. 下一步

本文档确认后进入实现计划。
