# Linux deb 分发 — 设计文档

> **已被部分取代（2026-10-02）**：`2026-10-02-single-package-release-design.md` 取代了本文的
> 以下部分：runtime / app 双 deb 结构（改为单个 `lm-labeling-tool_<版本>_amd64.deb`）、
> app deb 的 `Depends: lm-labeling-tool-runtime (= 0~<id>)` 精确锁定与“错配守卫”、
> `reuse_runtime.py` 对 runtime deb 的复用（Linux 现在每次发布都重建单个 deb）、
> `deb.py` 的 `--app-only` / `--runtime-id` 模式、依赖守卫步骤，以及“日常更新安装 app deb”
> 的更新方式（改为约 1–2 MB 的 `update-*-linux.zip`，由程序用 `pkexec` 自行应用）。
> 仍然有效的部分：22.04 构建、24.04 兼容、`RUNTIME_DEPENDS` 依赖声明、runtime id 的测量方式、
> 安装冒烟测试的思路。版本号也已重排（下一个版本为 v0.2.0），下文出现的 1.x / 2.x 版本号仅为历史记录。

- 日期：2026-09-30
- 状态：设计已确认，待实现
- 起点：main @ bab9299（v1.4.1 已发布，Windows 侧分层增量更新已稳定运行）
- 前置：`2026-09-28-layered-distribution-design.md`（分层机制）、
  `2026-09-30-lean-incremental-updates-design.md`（runtime id 的测量方式）

## 1. 背景

Windows 侧的分发链路已经成型并稳定：PyInstaller onedir 输出经 `packaging/layers.py`
按白名单切成应用层与运行时层，运行时层按「文件相对路径 + 大小」哈希出 runtime id，
Inno Setup 编出完整包与应用包两个安装程序，客户端每次启动查 GitHub Release 决定下
哪一个。日常代码更新约 2 MB，完整安装约 1.5 GB。

Linux 侧目前没有任何分发产物，使用者只能从源码运行。需要一个 deb 分发，且**版本号
与功能都与 Windows 严格对齐**。

## 2. 目标

- 交付 Linux deb 安装包，安装、启动、桌面集成的体验与 Windows 安装包对等。
- 保留分层增量更新：运行时未变时，Linux 更新同样只投送应用层。
- 应用内更新检查在两个平台上行为一致（每次启动检查、退出时提示）。
- 版本号同源：同一个 tag 同时产出两个平台的产物，挂在同一个 Release 下。
- 功能对等可机械验证，而不是靠人记得同步。

**非目标**：
- 不架设内部 apt 仓库。分发仍走 GitHub Release + 应用内更新器。
- 不支持 macOS（见 2026-09-30 的决策记录，公司内部只用 Windows 与 Linux）。
- 不做 AppImage / tar.gz 等免安装形态。使用者有 sudo 权限，deb 的桌面集成价值更高。

## 3. 已确认的决策

| 项 | 决策 | 放弃的备选与理由 |
|---|---|---|
| 包结构 | 双 deb：`lm-labeling-tool-runtime` + `lm-labeling-tool` | 单 deb 全量：每次发版所有用户下 1.5 GB，与「对齐 Windows」冲突；单 deb + 用户目录覆盖层：同一份代码在 `/opt` 与 `~` 各存一份，加载顺序成为新的故障面，而使用者已接受提权弹框，换不到对等收益 |
| 运行时绑定 | app 包 `Depends: lm-labeling-tool-runtime (= 0~<runtime-id>)` | 照搬 Windows 的做法（资产文件名带 runtime id + 安装器内手工校验 `build-info.json`）：dpkg 原生就能表达这个约束，手工校验是 Windows 上没有依赖系统才不得已 |
| runtime 包版本号 | `0~<runtime-id>`，如 `0~r3f8a1c92` | 用递增序号：需要额外维护序号与 runtime id 的映射表，且映射表本身会与产物脱节 |
| 目标发行版 | 在 Ubuntu 22.04 构建，支持 22.04 与 24.04 | 在 24.04 构建：glibc 只向上兼容，22.04 用户装不上 |
| GPU / few-shot | 包含，与 Windows 一致（torch 2.5.1+cu124 + sam2） | 纯 ONNX 版（约 150 MB）：与 Windows 功能不对等 |
| 可写状态位置 | `~/.local/share/lm-labeling-tool/`，配置与数据同目录 | 严格 XDG 拆分（config 进 `~/.config`）：与 Windows 的「状态集中在一个目录」心智模型不一致，而拆分带来的收益对本工具没有实际用途 |
| deb 组装方式 | `packaging/deb.py` 生成 control 后调 `dpkg-deb --build` | `dpkg-buildpackage` + `debian/` 目录：我们打的是二进制包而非源码包，其规则体系在此全是负担，且逻辑无法单测 |
| 安装动作 | `pkexec dpkg -i <runtime.deb> <app.deb>`，同步等待退出码 | `apt-get install ./x.deb`：会因 runtime 包版本号非单调而拒绝（需额外 `--allow-downgrades`），而 `dpkg -i` 默认允许降级；与 Windows 一样 detach 后立刻退出：Linux 不受「无法替换运行中可执行文件」限制，同步等待能拿到失败原因并报告给用户 |
| deb 文件名 vs 包版本 | 文件名与 `Version` 分担职责：app 文件名带 runtime id、包版本为纯版本号；runtime 文件名只带版本号、包版本为 `0~<runtime-id>` | 文件名与包版本一致：全量更新时客户端不知道新 runtime id，无法拼出 runtime deb 的文件名 |
| 工作流结构 | 单 workflow 三 job：`build-windows` / `build-linux` / `publish` | 两个独立 workflow + `workflow_run`：跨 workflow 依赖难用且容易悬空，无法可靠实现「四个资产齐了才发布」 |

## 4. 包结构与版本绑定

两个 deb 均安装到 `/opt/lm-labeling-tool/`，布局与 Windows 的 onedir 输出一一对应：

```
/opt/lm-labeling-tool/
├── LM_LabelingTool          ← 应用层（可执行文件）
├── build-info.json          ← 应用层
└── _internal/
    ├── labeling_tool/       ← 应用层
    ├── annotation_tool/     ← 应用层
    ├── models/sam/*.onnx    ← 运行时层
    └── (torch, PyQt5, ...)  ← 运行时层
```

分层规则复用 `packaging/layers.py` 的白名单，仅把入口名平台化：Windows 为
`LM_LabelingTool.exe`，Linux 为 `LM_LabelingTool`。`_SYSTEM_RUNTIME_PREFIXES`
（排除构建机 Windows 系统 DLL 的规则）在 Linux 上为空元组。

### 4.1 为什么 runtime 包的版本号是 runtime id

app 包不能装在不匹配的运行时上，否则得到一个无法启动的程序。Windows 上这个约束靠
`installer.iss` 的 `InitializeSetup()` 手工维持：读安装目录的 `build-info.json`，
字符串匹配 `"runtime":"rXXXXXXXX"`。这段 Pascal 代码踩过花括号解析坑（CI run
36518723697，guard 静默失效）和 `MsgBox` 挂起坑（CI 一个 job 卡 96 分钟）。

Linux 上这个约束是 dpkg 的原生能力。把 runtime id 放进 runtime 包的版本号，app 包
就能用一行 `Depends: lm-labeling-tool-runtime (= 0~r3f8a1c92)` 表达它，装错时由
dpkg 在安装阶段拒绝并打印缺失的依赖。上述整段手工 guard 在 Linux 侧不存在。

`0~` 前缀保证 runtime 包的版本在 dpkg 的版本序中永远排在任何真实应用版本号之前
（`~` 排在空字符串之前），避免它被误读为应用版本。

**已知代价**：runtime id 是哈希而非序号，runtime 包的版本号不单调递增。`apt upgrade`
依赖版本号递增来发现更新，因此运行时层的切换必须由更新器显式执行 `dpkg -i`，不能指望
`apt upgrade` 自行发现。对当前的分发模型（GitHub Release + 应用内更新器）无影响；将来
若要架内部 apt 仓库，此处需重新设计。

这也是安装动作选用 `dpkg -i` 而非 `apt-get install ./x.deb` 的原因之一：`apt` 遇到
「待装版本号小于已装版本号」会拒绝，须额外传 `--allow-downgrades`；而 `dpkg -i` 默认
允许降级，仅打印一行 warning。对一个版本号本就无序的包，后者语义更贴切。

## 5. 可写状态的位置

Windows 上 `app_paths.app_home()` 返回可执行文件所在目录，`config.json`、`data/`、
`checkpoint/`、`classes.json` 都写在那里——安装是单用户的，整个目录可搬移。Linux 上
`/opt/lm-labeling-tool/` 属 root 且只读，这套直接失效。

在 `labeling_tool/core/app_paths.py` 新增：

```python
def user_data_home() -> Path:
    """Where the app may write. Beside the executable on Windows (the install
    is per-user and portable); XDG on Linux, where the install lives under
    /opt and is root-owned."""
    if not is_frozen():
        return REPO_ROOT
    if sys.platform == "win32":
        return app_home()
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share"
    return Path(base) / "lm-labeling-tool"
```

`writable_path()` 的 frozen 分支由 `app_home()` 改为 `user_data_home()`。
**Windows 的行为必须逐字节不变**——已发布的 Windows 安装量不能因为 Linux 支持而
发生数据搬迁。由 `test_app_paths.py` 断言。

配置与数据同放 `~/.local/share/lm-labeling-tool/`，不按严格 XDG 拆分，理由见决策表。
`checkpoint/` 体积可能很大，放数据目录也比配置目录合适。

下载中的更新包是唯一例外，放 `~/.cache/lm-labeling-tool/`：它是可丢弃的临时文件，
放数据目录会被用户的备份无谓带上。

`bundled_path()` 与 `resource_path()`（ONNX 模型、图标、BPE 词表）不受影响，它们本
就是只读资源，继续从 `_internal/` 解析。

## 6. 版本与功能对等

### 6.1 版本号同源与发布完整性

一个 tag 触发两个平台的构建，两边 `build-info.json` 的 `version` 同取自该 tag，产物
挂在同一个 Release 下。

`publish` job 在收齐两个平台的产物之前不创建 Release，四个资产（Windows full/app、
Linux runtime/app）缺任何一个即整体失败；Linux 的 runtime deb 即便本次是复用上一个
release 的产物也必须在列（见 7.2.1）。这条门禁的重要性高于其它检查：客户端只按
名字查找资产，找不到就静默不更新，一边构建失败而另一边照常发布，是**无声的**故障。

### 6.2 依赖清单的漂移防护

`packaging/build-lock.txt` 锁的是 Windows 构建环境，其中 `pefile`、`pywin32-ctypes`
是 PyInstaller 的 Windows 专用构建期依赖，Linux 无法安装；Linux 侧亦有自己的平台专用
项。因此必须有第二份 `packaging/build-lock-linux.txt`。

两份清单一旦分开就会各自漂移——在一侧升级了 opencv 而另一侧遗漏，功能便悄悄不一致。
对策是 `test_lock_parity.py`：解析两份清单，断言**除一份显式的平台专用白名单外，每个
包的版本号逐字相同**；白名单中每一项都须注明为何只存在于一侧。漂移由此成为一个失败的
测试，而不是数月后用户报的怪 bug。

### 6.3 图标

`labeling_tool/app.py:107` 当前加载 `icon.ico`。Qt 在 Linux 上的 ICO 支持取决于相应
插件是否被 PyInstaller 收入，不可靠。仓库已有 `icon.svg`，改为由它生成一张 PNG，两个
平台的 `setWindowIcon` 与 Linux 的 `.desktop` `Icon=` 同用该 PNG。`.ico` 仅保留给
Windows 的安装包与可执行文件资源。

### 6.4 CUDA

Linux 的 `torch==2.5.1+cu124` wheel 自带 CUDA 运行时库，与 Windows 一样无需用户安装
CUDA Toolkit，但**需要宿主机具备 NVIDIA 驱动**。这一点两平台相同。deb **不得**声明对
驱动包的依赖，否则纯 CPU 机器无法安装。行为对等：有驱动走 GPU，无驱动时 few-shot 的
回落/报错行为与 Windows 当前一致。

`sam2` 的 git symlink 问题已由 323f53a 在两侧处理，Linux 侧无需再动。

## 7. 更新流程

### 7.1 UpdateInfo 由单资产改为资产列表

Windows 的完整安装包是单文件、自带两层；Linux 的完整安装是两个独立 deb。因此
`checker.UpdateInfo` 的 `asset_name` / `asset_url` / `size` / `sha256` 四个标量字段
改为一个资产列表：Windows 恒为长度 1；Linux 的 `kind="app"` 长度 1、`kind="full"`
长度 2。下载与 SHA256 校验相应循环，`ui.py` 的进度按总字节数计算。

这是本设计中唯一侵入既有 Windows 代码路径的改动，须由测试钉住「Windows 侧列表长度恒
为 1 且行为不变」。

### 7.2 资产命名

**deb 的文件名与包内 `Version` 字段是两回事**，dpkg 不要求二者一致。这里刻意让它们承担
不同职责：文件名要让客户端能在只知道版本号的情况下拼出来，`Version` 字段要表达运行时
绑定。

| | Windows | Linux 文件名 | Linux 包内 `Version` |
|---|---|---|---|
| 应用层 | `LM_LabelingTool-App-v1.4.1-r3f8a1c92.exe` | `lm-labeling-tool_1.4.1-r3f8a1c92_amd64.deb` | `1.4.1` |
| 运行时层 | （含于完整包内） | `lm-labeling-tool-runtime_1.4.1_amd64.deb` | `0~r3f8a1c92` |

app deb 的**文件名**带 runtime id，与 Windows 完全对称：客户端用自己的 runtime id 拼出
文件名，命中则说明这个应用层包正是为本机运行时构建的，无需下载即可判断。其**包版本**则
是干净的 `1.4.1`，因为运行时绑定由 `Depends` 表达，不必挤进版本号。

runtime deb 的**文件名**只带发布版本，不带 runtime id。这是必须的：全量更新时客户端要
下载新的 runtime deb，而它只知道目标版本号、**不知道新的 runtime id**——若文件名含 id
便无从拼出。其**包版本**是 `0~<runtime-id>`，承担 4.1 的绑定职责。

### 7.2.1 每个 release 都必须挂一份 runtime deb

即便运行时未变、当次发布无人需要下载它，runtime deb 也必须以**本次版本**的文件名出现在
release 中。理由与 `packaging/reuse_full.py` 开头记录的完全相同：需要全量安装的人
（新装机器、运行时不匹配的旧安装）只会去查最新 release 里 `lm-labeling-tool-runtime_<最新版本>_amd64.deb`
这一个名字，缺了它，这些人将得不到任何可安装的东西，且故障是静默的。

因此 Linux 侧要有与 `reuse_full.py` 对等的逻辑：运行时未变时不重新构建（省去 1.4 GB 的
xz 压缩），而是下载上一个 release 的 runtime deb、核对其已发布的校验和、以本次版本的文件
名重新发布。判定「运行时未变」的依据同样取自上一个 release 自身——其 app deb 文件名中的
runtime id 若与本次相同，则其 runtime deb 逐字节就是本次所需的那一个。

### 7.3 安装动作

```
pkexec dpkg -i <runtime.deb> <app.deb>
```

两个包写在同一条命令中：dpkg 先 unpack 全部、再统一 configure，因此 app 包对 runtime
包的依赖在同一次调用内即可满足，无需分两次安装，也无需关心顺序。`kind="app"` 的更新
只传 app 包一个参数。

选用 `dpkg -i` 而非 `apt-get install ./x.deb` 的理由见 4.1（版本号非单调）。手动安装
时使用者执行的是同一条命令，与更新器一致：

```bash
sudo dpkg -i lm-labeling-tool-runtime_1.4.1_amd64.deb \
             lm-labeling-tool_1.4.1-r3f8a1c92_amd64.deb
```

与 Windows 的关键差异是**可以同步等待并取得退出码**。Windows 上应用必须 detach 安装
器后立刻退出，安装失败时应用无从得知；Linux 上可以等 `dpkg` 返回，失败则将 stderr
报告给用户。流程为：下载 → 校验 → pkexec 同步安装 → 成功后提示重启生效 →
`os.execv` 拉起新进程。

### 7.4 三种失败须区别对待

`dpkg -i` 不解析依赖，这带来一种 `apt` 路径下不会出现的失败，更新器必须分辨：

| 情形 | 判据 | 处理 |
|---|---|---|
| 用户在 polkit 密码框取消 | `pkexec` 退出码 126 | 静默返回应用，不报错 |
| 缺系统库依赖 | dpkg 退出码非 0 且 stderr 含 `dependency problems` | 提示使用者执行 `sudo apt-get install -f` 补齐后重试，并在消息中列出 dpkg 报出的缺失包名 |
| 其它安装失败 | 其余非 0 退出码 | 弹出错误并附 stderr |

第二种情形是 `dpkg -i` 的固有限制：它不会从仓库拉取 `libxcb-xinerama0` 这类系统库。
但这是**在安装阶段**被拒绝，而非装完后启动时崩在
`could not load the Qt platform plugin "xcb"`——失败更早、指向更明确。为使它尽量不
发生，runtime 包声明的系统库依赖须限于目标发行版桌面安装默认已有的集合，超出部分在
9.2 的干净容器测试中暴露。

已下载的 deb 留在 `~/.cache/lm-labeling-tool/`，下次更新前清理。

## 8. 构建与 CI

### 8.1 工作流结构

现有 `build-windows.yml` 中构建与发布是一体的，而 6.1 的资产完整性门禁要求发布步骤能
同时看到两个平台的产物。改为单 workflow 三个 job：

- `build-windows`（`windows-latest`）——现有构建步骤原样迁入
- `build-linux`（`ubuntu-22.04`）
- `publish`（`needs: [build-windows, build-linux]`）——现有发布步骤迁入

`ubuntu-22.04` 是刻意选择而非 `ubuntu-latest`：glibc 2.35 向上兼容 24.04，反之不然。
此选择须在 workflow 中注明理由，否则将来一次「顺手升级 runner」会悄然放弃 22.04 用户。

### 8.2 deb 的组装

新增 `packaging/deb.py`，生成两个包的 `DEBIAN/control` 并调用 `dpkg-deb --build`，
角色与 `installer.iss` 对等。逻辑置于 Python 中以便单测，与 `layers.py`、
`reuse_full.py` 保持同一模式。

**runtime 包必须声明系统库依赖。** PyInstaller 打包了 Python 侧的一切，但 Qt 的 xcb
平台插件需链接宿主的 `libgl1`、`libglib2.0-0`、`libxkbcommon-x11-0`、
`libxcb-icccm4` 等。不声明则在较干净的机器上能装上、一启动即报
`could not load the Qt platform plugin "xcb"`。这组依赖归 runtime 包（服务于运行时
层），app 包只依赖 runtime 包。

由于安装走 `dpkg -i`（不解析依赖，见 7.3），这里声明的系统库须限于目标发行版桌面安装
默认已具备的集合；任何超出部分都会让使用者的手动安装中断。9.2 的干净容器测试强制这一
约束。若某个库确实必需而默认不具备，正确的做法是在 PyInstaller 侧把它收进运行时层，而
不是声明成依赖。

`libxcb-xinerama0` 就是这种情形：22.04 的 `ubuntu-desktop-minimal` 不带它，最初把它
写进 `Depends` 后，`dpkg -i` 在干净容器里直接拒装（CI run 36842846563）。现在它列在
`deb.py` 的 `BUNDLED_LIBS`：构建机与 `RUNTIME_DEPENDS` 一起装上，由 PyInstaller 收进
运行时层，不再声明为依赖。24.04 交叉验证容器里系统并没有这个库，selftest 在那里跑通
即证明打包的那份可用。

**桌面集成归应用层。** `.desktop` 引用可执行文件，而可执行文件按白名单属应用层，两者
必须同层，否则会出现「应用已更新但快捷方式指向旧路径」。app deb 安装
`/usr/share/applications/lm-labeling-tool.desktop`、图标至
`/usr/share/icons/hicolor/`，并建立 `/usr/bin/lm-labeling-tool` 软链；`postinst` 中
刷新 desktop 数据库与图标缓存。

### 8.3 压缩

1.4 GB 的 runtime 包压缩是 Linux job 的时间大头。`dpkg-deb -Zxz` 默认单线程，通过
`XZ_OPT=-T4` 启用四线程——与 `installer.iss` 中 `LZMANumBlockThreads=4` 是同一件事、
同样的理由。验证构建（非 tag）用 `-Zgzip -z1` 跳过压缩开销，对应 Windows 的
`/DMyFast=1`。

## 9. 测试策略

### 9.1 pytest 层

| 文件 | 覆盖 |
|---|---|
| `test_deb.py`（新） | control 生成：包名、架构、`Installed-Size`；app 包 `Depends` 逐字等于 `lm-labeling-tool-runtime (= 0~<runtime-id>)` |
| `test_lock_parity.py`（新） | 两份 lock 除白名单外版本逐字相同；白名单每项均有理由注释 |
| `test_layers.py`（扩展） | 入口名平台化后两个平台的分层结果；既有不变式继续覆盖两侧 |
| `test_update_checker`（扩展） | 平台化资产名；**Windows 侧资产列表长度恒为 1** |
| `test_app_paths.py`（新） | `user_data_home()` 在源码运行 / Windows frozen / Linux frozen / `XDG_DATA_HOME` 已设 四种情形；重点断言 **Windows frozen 返回值与改造前完全一致** |
| `test_installer`（扩展） | Linux 分支构造的 `pkexec dpkg -i` 命令行（full 传两个包、app 传一个）；7.4 的三种失败分辨：126 为取消、stderr 含 `dependency problems` 为缺系统库、其余为一般失败 |

### 9.2 CI 层

- 以 `sudo dpkg -i <runtime.deb> <app.deb>` 安装后，在 `xvfb-run` 下跑 selftest，与
  Windows 的安装后自检对等。此步可捕获 8.2 所述 Qt 插件依赖缺失——该类问题只在真实安装
  后的环境暴露，在构建目录中永远为绿。
- **`dpkg -i` 须在不借助 `apt-get install -f` 的前提下一次成功。** 这是 7.4 第二种失败
  的防线：若测试需要 `-f` 才能装上，说明 runtime 包声明了目标发行版桌面安装默认不具备
  的系统库，使用者手动安装时也会撞上。此时应调整依赖或在 PyInstaller 侧收入该库，而不是
  在文档里要求使用者多跑一条命令。
- **故意单独安装运行时不匹配的 app deb，断言 dpkg 拒绝。** 对应 Windows 那段 Pascal
  guard 的验证。dpkg 的依赖机制本身自然是对的，但我们的 `control` 写错（例如 runtime id
  拼接漏掉前缀）同样会使 guard 形同虚设，而这种错误在正常路径上完全看不出来。
- **在 24.04 容器中再装一遍并跑 selftest。** 否则「22.04 构建覆盖 24.04」只是假设：
  glibc 向上兼容属实，但 Qt 与图形栈在新发行版上未必没有意外。两个发行版都要验证上面那条
  「`dpkg -i` 一次成功」。
- 发布资产完整性门禁（见 6.1）。

## 10. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 两份 lock 清单漂移 | 两平台功能悄然不一致 | `test_lock_parity.py` 强制版本一致（6.2） |
| Qt xcb 系统库依赖漏声明 | 装得上但启动即崩 | runtime 包显式声明；CI 安装后 xvfb selftest（8.2、9.2） |
| runtime 包版本非单调 | `apt upgrade` 无法发现运行时更新 | 更新器显式 `dpkg -i` 两个 deb（`dpkg` 默认允许降级）；不架 apt 仓库（4.1） |
| `dpkg -i` 不解析依赖 | 目标机缺系统库时安装中断 | 依赖限于目标发行版桌面默认集合，CI 验证「无需 `-f` 一次装成」；更新器识别该失败并提示 `apt-get install -f`（7.4、9.2） |
| 一侧构建失败仍发布 | 该平台客户端静默不更新 | `publish` 需两侧产物齐备（6.1） |
| release 漏挂 runtime deb | 需全量安装者无任何可下载物，且静默 | 每个 release 必挂，运行时未变时复用上一个 release 的文件；资产完整性门禁覆盖（7.2.1、6.1） |
| `user_data_home()` 改动波及 Windows | 已安装用户数据搬迁丢失 | `test_app_paths.py` 断言 Windows 行为逐字节不变（5） |
| 22.04 构建在 24.04 上有意外 | 半数目标用户无法使用 | CI 在 24.04 容器中独立验证（9.2） |
