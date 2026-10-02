# 单安装包发布与 zip 增量更新 — 设计

日期：2026-10-02
状态：设计已逐段确认，待审阅

## 1. 背景与目标

v2.0.0 的发布结构是“每个平台两个安装包”：Windows 有 `Setup`（完整）和 `App`（应用层）两个 exe，
Linux 有 runtime 和 app 两个 deb。用户在 Release 页面上无法判断该下载哪个；Linux 用户还必须
同时安装两个 deb 才能装上。软件尚未分发，可以推倒重来。

**目标**

1. 用户手动下载时，Windows 只有**一个 exe**，Linux 只有**一个 deb**（仅 x86-64）。
2. 日常更新（模型、torch/CUDA 等运行时没变）只更新程序代码，约 1～2 MB，不重装完整版。
3. Release 页面仿照 RustDesk：顶部是下载表格，下面是更新内容，最下面是 GitHub 自动列出的全部文件。
4. Release 说明一律使用韩语。
5. 更新通知增加“运行中定时检查”和“增量更新后台预下载”。
6. 版本号重排：旧 1.x → 0.0.x，2.0.0 → 0.1.0；按新结构发布的第一个版本为 **v0.2.0**；
   正式分发时再使用 1.x。

**成功标准**

- Windows 用户：打开 Release 页面 → 点表格里的 EXE → 安装完成，不会遇到第二个安装包。
- Linux 管理员：一个 deb，`sudo dpkg -i` 一次装好。
- 只改代码的版本，已安装的程序下载约 1～2 MB 即完成更新；运行时变化时才下载完整包。
- 更新失败时程序仍可使用旧版本，不会留下半新半旧的安装。

**不做**：强制更新（最低支持版本）、分批推送、ARM 等其他架构、增量 patch 的逐文件 diff
（更新 zip 携带完整的应用层，体积已足够小）。

## 2. 发布产物

每个 Release 包含：

| 文件 | 用途 |
|---|---|
| `LM_LabelingTool-Setup-v<版本>.exe` | Windows 手动下载；运行时变化时的完整更新 |
| `lm-labeling-tool_<版本>_amd64.deb` | Linux 手动下载；运行时变化时的完整更新 |
| `update-v<版本>-r<runtime id>-windows.zip` | Windows 增量更新（自动） |
| `update-v<版本>-r<runtime id>-linux.zip` | Linux 增量更新（自动） |
| `SHA256SUMS.txt` | 以上 4 个文件的校验码 |
| Source code (zip / tar.gz) | GitHub 自动生成，无法关闭 |

- **runtime id** 沿用 `packaging/layers.py` 现有的计算方式，是“运行时是否改变”的唯一判据。
  已安装的程序只采用 runtime id 与自己相同的 zip，否则改走完整更新。
- **Windows Setup 复用**：运行时未变时沿用上一版的 Setup（`reuse_full.py` 现有逻辑）。
  已安装用户走 zip 更新；新用户安装后若代码较旧，首次启动会收到 zip 更新。
- **Linux 单 deb 不再复用**：完整 deb 同时包含运行时与代码，每次发布都要重新做 xz -9 压缩
  （CI 约 16 分钟，Linux job 约 30 分钟）。这是“只有一个 deb”的直接代价，只影响 CI 时长。
- 发布前门槛：上述 4 个文件与 `SHA256SUMS.txt` 齐全且校验码对应，否则不发布；
  资产大小上限检查保持不变（发布级压缩时才执行）。

**删除**：Windows `App-*.exe` 及 `installer.iss` 的 app 层模式与不匹配守卫、Linux runtime/app
双包结构与 `reuse_runtime.py`、`deb.py` 的 `--app-only` / `--runtime-id` 模式、
无效的 `bundle_filters.py`（顶层的 NCCL 实为指向 `nvidia/nccl/lib` 的符号链接，并无重复数据；
CI run 36974793419 的 runtime id 未变即为证据）。

### 2.1 Release 说明（韩语，自动生成）

```
| Architecture | Windows | Ubuntu |
|---|---|---|
| x86-64 (64-bit) | [EXE](<Setup 下载地址>) | [Download](<deb 下载地址>) |

<!-- notes:start -->
<tag 注释正文：本次更新内容，韩语>
<!-- notes:end -->

### 어떤 파일을 받아야 하나요?
- Windows: 위 표의 EXE 하나만 받으면 됩니다.
- Ubuntu 22.04 / 24.04: 위 표의 .deb 하나만 받으면 됩니다.
- 아래 Assets 의 update-*.zip, SHA256SUMS.txt, Source code 는 자동 업데이트용이므로 받지 않아도 됩니다.
```

- 更新内容来自 tag 的注释（annotated tag message），**必须用韩语书写**。
- 更新弹窗只显示 `notes:start` 与 `notes:end` 之间的内容（替代现在的“前 8 行”），
  因此表格与下载指南不会出现在弹窗里。

## 3. 更新 zip 与应用流程

### 3.1 zip 内容

- 应用层文件（`layers.stage_app_layer` 的输出），保持安装目录内的相对路径；
- `manifest.json`：`version`、`runtime`（运行时 id）、`platform`、`files`（应用层**完整**文件清单，
  每项含相对路径与 SHA256）。`build-info.json` 属于应用层，随 zip 一起更新版本号。

### 3.2 应用流程（两个平台共用同一个 Python 模块）

1. 校验 zip 的 SHA256（来自 `SHA256SUMS.txt`）；读取 manifest，确认 `runtime` 与 `platform`
   与本机 `build-info.json` 一致，否则拒绝并改走完整更新。
2. 解压到安装目录内的 `.update-staging/`，逐个核对文件 SHA256。
3. 写入日志文件 `.update-journal`（标记“进行中”及待替换清单）。每次写入都先写同目录的临时文件、
   fsync，再原子替换，断电只会留下前一版或新一版日志，不会留下半截文件。
4. 逐个替换：旧文件先**移动**到 `.update-backup/`，再把新文件移入。旧应用层中存在、
   新 manifest 中不存在的文件同样移入备份（避免残留旧模块被加载）。可执行文件**最后**替换，
   中途断电也不会留下没有 exe 的安装（还原需要它启动）。Windows 上被杀毒软件短暂锁定的移动会退避重试。
5. 任一步失败：按日志从备份还原，删除 staging，保留旧版本并告知用户原因。
6. 成功：删除日志与 staging，重启程序；备份在 Windows 下次启动时、Linux 下一次应用更新时删除。

### 3.3 Windows

- 安装目录 `%LOCALAPPDATA%\Programs\LM_LabelingTool` 普通用户可写，**由程序自身完成替换**，
  无需管理员权限，也无需额外安装程序。
- 运行中的 `LM_LabelingTool.exe` 无法覆盖，但可以**重命名**；第 4 步的“移动到备份”对它同样有效。
  替换完成后启动新 exe，当前进程退出。

### 3.4 Linux

- `/opt/lm-labeling-tool` 归 root 所有：以 `pkexec /opt/lm-labeling-tool/LM_LabelingTool
  --apply-update <zip>` 执行 3.2 的同一流程。以 root 运行时**重新校验 zip**（防止下载与安装之间
  文件被替换）。
- 这些改动绕过 dpkg，因此 deb 的 `postrm`（remove/purge）删除整个 `/opt/lm-labeling-tool`，
  `preinst` 在完整安装前清理应用层目录，避免残留文件。

### 3.5 完整更新（运行时变化）

- Windows：下载 Setup，静默安装并自动重启（现有做法）。
- Linux：下载单个 deb，`pkexec dpkg -i`，提示重启（现有做法，单包化）。

## 4. 更新通知流程

- **检查时机**：启动时一次；运行中每 4 小时一次。失败静默；被跳过的版本不再提示。
- **增量更新**：发现后在后台下载并校验，完成后：
  - 登录界面（无作业进行中）：立即弹窗；
  - 标注中：不打断，状态栏显示「새 버전 v<版本> 준비됨」，关闭作业窗口时弹窗（沿用现有机制）。
- **完整更新**：不自动下载（1.5～1.9 GB），按现有方式提示大小并由用户决定。
- 弹窗按钮：「지금 재시작하여 업데이트 / 나중에 / 이 버전 건너뛰기」。
- 「나중에」：已下载的 zip 保留在缓存中，下次启动直接提示；过时的缓存自动清理。

## 5. 出错处理

| 情况 | 处理 |
|---|---|
| 后台下载失败、校验不符 | 丢弃，下次检查重试；只写更新日志，不弹窗 |
| 用户主动的完整更新下载失败 | 弹窗说明原因并附 Release 链接（现有） |
| 替换失败（多开、杀毒软件锁定） | 按备份还原，继续运行旧版本，提示关闭所有窗口后重试 |
| 替换中途断电或崩溃 | Windows：启动时首先检查 `.update-journal`，未完成则自动还原后再启动。Linux：普通用户启动动不了 `/opt`，在下一次应用更新（root）时还原，或重装 deb。日志无法解析时把 `.update-backup/` 里的全部文件放回原处，绝不连同备份一起删除 |
| zip 的 runtime id 或平台不符 | 拒绝，改走完整更新 |
| Linux 取消密码框 / 不允许提权 | pkexec 126 静默返回；127 报告原因（现有分类） |

## 6. 测试

1. **单元测试**：zip/manifest 生成与校验；替换与还原（逐步注入失败）；旧文件清理；中断恢复；
   zip 与完整包的选择；`notes` 段提取；韩语 Release 说明生成；定时检查与后台下载的状态机。
2. **发布前自动验证**：安装刚构建的完整包，用同一次构建的 zip 执行真实的 `--apply-update`，
   确认版本已更新、selftest 通过。Linux 在 CI 与 `local-build.sh` 中执行，Windows 在
   `local-build.ps1` 中执行。
3. **真机端到端**：v0.2.0 是第一个带新机制的版本；在 WinBoat 虚拟机安装 v0.2.0 后发布 v0.2.1，
   实际走一遍自动更新。

## 7. 版本号重排与收尾

- tag 改名（指向原提交，注释改为韩语说明）：v1.1.0→v0.0.1、v1.2.0→v0.0.2、v1.3.0→v0.0.3、
  v1.4.0→v0.0.4、v1.4.1→v0.0.5、v2.0.0→v0.1.0；删除全部现有 GitHub Release。
- 已装测试机（WinBoat 中的 1.4.1）需手动卸载重装：0.x 低于 1.4.1，不会自动更新。
- 更新 README、RELEASING.md；Linux deb 设计文档标注被本设计取代的部分。
- 使用说明 PPT：v0.2.0 发布后重拍下载步骤（页面结构与文件名改变）。
- 修复 `local-build.sh` 在构建容器中失败的两个测试：图标测试对 Pillow 版本过于敏感
  （锁定 12.3.0 与开发环境 12.2.0 渲染差一个像素值）；`test_frozen_module_constants_*`
  的原因待查（已排除 numpy 1.26）。
- 更新项目记忆。
