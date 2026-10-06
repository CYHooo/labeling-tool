# 发布流程

**所有检测都在本地完成，CI 只负责构建和发布。**

以前每一轮 CI 需要 18–25 分钟，检测失败就要修复后再跑一轮，一个小版本常常要花几个小时。
现在 CI 只在推送版本 tag 时运行，也就是只做发布这一件事。

## 一次性准备（Windows）

需要 Python **3.12.10** 和 Inno Setup 6。构建目录请放在本地磁盘上：4 GB 的构建产物放在网络盘上会很慢。

```powershell
& "C:\Program Files\Python312\python.exe" -m venv C:\lt\venv   # 必须是全新 venv
$env:SAM2_BUILD_CUDA = "0"
# sam2 的仓库里有符号链接，不开启的话 git 只会写出 30 字节的占位文件
$env:GIT_CONFIG_COUNT = "1"; $env:GIT_CONFIG_KEY_0 = "core.symlinks"; $env:GIT_CONFIG_VALUE_0 = "true"
$pip = "C:\lt\venv\Scripts\pip.exe"
& $pip install -c packaging/build-constraints.txt -c packaging/build-lock.txt -r requirements-dev.txt "pyinstaller==6.22.3"
& $pip install -c packaging/build-constraints.txt -c packaging/build-lock.txt "torch==2.5.1" "torchvision==0.20.1" --index-url https://download.pytorch.org/whl/cu124
& $pip install -c packaging/build-constraints.txt -c packaging/build-lock.txt --no-build-isolation "git+https://github.com/facebookresearch/sam2.git@2b90b9f5ceec907a1c18123530e92e794ad901a4"
```

venv 里不能有多余的包：PyInstaller 会把它们一起打包进去，runtime id 就会变。

## 发布产物

每个 Release 只有这些文件（用户手动下载时每个平台只需要一个）：

| 文件 | 大小 | 用途 |
|---|---|---|
| `LM_LabelingTool-Setup-v<版本>.exe` | 约 1.5 GB | Windows 手动下载；运行时变化时的完整更新 |
| `lm-labeling-tool_<版本>_amd64.deb` | 约 1.8 GB（`xz -9`） | Linux 手动下载；运行时变化时的完整更新 |
| `update-v<版本>-<runtime id>-windows.zip` | 约 1–2 MB | Windows 增量更新（仅应用层，程序自动下载） |
| `update-v<版本>-<runtime id>-linux.zip` | 约 1–2 MB | Linux 增量更新（仅应用层，程序自动下载） |
| `SHA256SUMS.txt` | 很小 | 以上四个文件的校验码 |
| Source code (zip / tar.gz) | — | GitHub 自动生成，无法关闭 |

发布前门槛：四个文件与 `SHA256SUMS.txt` 必须齐全且校验码对应，否则不发布。

## 发布步骤

1. **本地完整验证**（Windows 约 15 分钟）：

   ```powershell
   powershell -File packaging\ci\local-build.ps1 -Venv C:\lt\venv
   ```

   依次运行：测试套件 → PyInstaller 构建 → 自检与启动冒烟测试 → 分层并计算 runtime id → 编译 Setup
   → 安装冒烟测试（安装刚构建的 Setup，再用同一次构建的 update zip 执行真实的应用内更新，确认版本
   已更新、自检通过，然后卸载）。

   安装冒烟测试使用独立的测试 AppId（`/DMyTestInstall=1`），不会影响本机正式安装的程序。
   只修改了部分内容时，可以只跑相关步骤，例如 `-Steps tests` 或 `-Steps build,selftest,layers`。
   Linux 侧见下面「本地完整验证（Linux）」。

2. **记下输出的 `runtime id`。** 与上一个版本的 `update-v<版本>-<runtime id>-windows.zip` 资产名对比：
   - **相同**：已安装的用户只下载约 1–2 MB 的 zip，由程序自己完成替换。
   - **不同**：用户需要下载完整安装包。只有升级依赖（修改了 `build-lock.txt`）、更换 Python 或调整 spec
     中的运行时配置时，才应该出现这种情况。如果你没有做这些改动 id 却变了，**先别发布**，用
     `diag\runtime-manifest-*.txt` 对比找出原因。

3. **写韩语的 annotated tag 注释。** Release 页面的“更新内容”直接取自 tag 注释，
   而且是韩语用户看的，所以**注释必须是韩语**。CI 的 `build-linux` job 里的 Version 步骤会检查：
   注释里含汉字，或没有任何韩文字母，都会直接失败。

   ```bash
   git tag -a v0.2.0   # 编辑器里写韩语说明；或 git tag -a v0.2.0 -m "<韩语说明>"
   ```

   不要用 `git tag v0.2.0`（轻量 tag 没有注释）。

   **写法**：按韩语更新日志的通用写法，条目用名词形结尾，不用 `~습니다`：
   `- 릴리스 페이지 간소화`、`- ~ 기능 추가`、`- ~ 오류 수정`。标题自己写（如 `## 주요 변경 사항`）。
   注释里的 `#` 开头的行会被 git 默认删掉，打 tag 时用 `git tag -a v0.2.0 --cleanup=whitespace -F notes.txt`。

4. **先演练一次。** 手动运行工作流，用发布级压缩和资产大小上限检查把整条流水线跑一遍，但不发布：

   ```bash
   gh workflow run release.yml -f release_compression=true
   ```

   演练只上传构建产物，不创建 Release（见下面「CI 的手动运行」）。绿了再进入下一步。

5. **推送 tag。** 版本号只来自 tag（写入 `build-info.json`），代码里不需要改：

   ```bash
   git push origin v0.2.0
   ```

   CI 流程：安装依赖（有 pip 缓存）→ 构建 → 自检 → 编译 Setup / 打 deb → 生成 update zip 与
   `SHA256SUMS.txt` → 校验产物齐全 → 发布到 GitHub Release。

   - **Windows**：上一个 Release 的 `update-...-windows.zip` 带有相同的 runtime id 时，直接复用上一版的
     Setup（`packaging/reuse_full.py`，先按它原来的校验和验证，再以本版本的文件名重新发布），省去重新压缩。
     新用户装上的是上一版的代码，第一次启动时会自动收到约 1–2 MB 的 zip 更新。运行时变了则重新构建完整包。
   - **Linux**：runtime id 相同时同样复用上一版的 deb（`packaging/reuse_deb.py`）：按原校验和验证后，
     只改写 control 里的 Version，约 1.7 GB 的数据成员原样复制（不到 1 秒），省去 `xz -9` 的约 16 分钟。
     当前代码写出的 control（Depends、维护脚本、`.desktop`/图标指纹 `X-LT-Extras-SHA256`）与旧包除
     Version 外不完全一致时（例如改了依赖或图标），自动改为完整构建。复用时跳过桌面容器依赖检查和
     24.04 交叉验证（旧包已通过），保留 runner 上的安装 + selftest 与 zip 往返（验证旧程序升级到新版本）。
     完整构建时 Linux job 约 28 分钟，复用时约 10–12 分钟。v0.2.1 及以前的 deb 没有指纹字段，
     所以引入复用后的第一个版本仍会完整构建一次。

6. **核对 CI 日志中的 `runtime id` 与第 2 步是否一致。** 本地与 CI 使用同一份锁文件和同一个 Python，
   结果应当完全相同。

### Release 页面

页面正文由 `packaging/release_notes.py` 自动生成，全部为韩语：

1. 顶部是下载表格（Windows 的 EXE、Ubuntu 的 deb 直链）；
2. 下面是 tag 注释正文，位于 `<!-- notes:start -->` 与 `<!-- notes:end -->` 之间
   （标题由注释自己写，例如 `## 주요 변경 사항`；生成器不再另加标题，也不再附文件说明）；
3. 最下面是 GitHub 自动列出的 Assets。

应用内的更新弹窗只显示 `notes:start` 与 `notes:end` 之间的内容，所以表格不会出现在弹窗里。

## 更新是怎么到达用户手里的

- **检查时机**：启动时一次，运行中每 4 小时一次；失败静默，被用户跳过的版本不再提示。
- **只改了代码**（runtime id 与本机相同）：程序在后台下载 update zip 并校验 SHA256，重启时由程序自己
  应用——Windows 的安装目录用户可写，无需提权；Linux 通过 `pkexec` 弹一次密码框。替换过程有日志与
  备份，替换失败会立即还原，旧版本继续可用。
- **中途断电或崩溃**：Windows 在**下次启动**时按日志自动还原。Linux 上程序以普通用户启动，
  动不了 root 所有的 `/opt`，所以**启动时不会还原**；还原发生在**下一次应用更新**（以 root 运行）时，
  或者重新 `sudo dpkg -i` 安装 deb。
- **旧版本的备份**（`.update-backup/`）：Windows 在下次启动时删除；Linux 在下一次应用更新时删除。
- **运行时变了**（torch / CUDA / 模型）：弹窗提示完整包的大小，**不经用户同意不会下载**。

## 为什么本地和 CI 的结果会一致

runtime id 是对运行时层每个文件的「路径 + 大小」做哈希。以下三项保证它只在运行时真正变化时才改变：

- **`packaging/build-lock.txt`** 固定了全部依赖的版本，包括传递依赖。上游发布新版本不会影响构建。
- **全新的 venv**：CI 不使用 runner 自带的 Python，因为那里预装的 `filelock`、`packaging` 等包的版本
  会随 runner 镜像变化。
- **git 展开符号链接**（`core.symlinks=true`）：sam2 的仓库里有几个 yaml 是符号链接。
  没开启时 git 只写出占位文件，构建能通过，但 runtime id 会和 CI 不一样。`local-build.ps1` 会检查这一点。
- **排除构建机的系统 DLL**：PyInstaller 从构建机的 Windows 或 SDK 里收集的 `api-ms-win-*`、
  `ucrtbase`、`vcruntime140*`、`msvcp140*` 不计入 id（文件本身照常发布）。GitHub 每周更新 runner 镜像，
  这些 DLL 的大小会随之改变。

## 升级依赖

修改 `build-lock.txt` 就是修改运行时层，下一个版本一定是完整安装。按以下步骤重新生成：

1. 新建一个全新的 venv，用 `build-constraints.txt` 安装依赖（这次**不要**带 `build-lock.txt`）。
2. 运行 `pip freeze`，去掉 `SAM-2 @ git+...` 这一行后写回 `build-lock.txt`，保留文件开头的注释。
3. 本地完整验证一遍。

## Linux（.deb）发布

Windows 和 Linux 由**同一个 tag** 从同一个工作流（`release.yml`）构建发布，产物见上面的表格：
Linux 只有一个 deb 和一个 update zip。

### 本地完整验证（Linux）

和 Windows 侧的 `local-build.ps1` 对等：`packaging/ci/local-build.sh` 把本应在 CI 里才能发现的
问题提前到本地，跑一轮约十几分钟并下载数 GB，而不是推 tag 等 18–25 分钟的 CI。**必须在容器里跑**
——开发机是 Ubuntu 24.04（glibc 2.39），发布目标是 22.04（glibc 2.35），glibc 只能向前兼容，宿主机
上直接构建的产物不能代表发布物。脚本检测到不在容器里会直接报错退出，不会误跑。

```bash
docker run --rm -v "$PWD:/repo" -v /var/run/docker.sock:/var/run/docker.sock \
  -e HOST_REPO_ROOT="$PWD" --tmpfs /repo/.venv -w /repo \
  ubuntu:22.04 bash packaging/ci/local-build.sh
```

- `-v /var/run/docker.sock:/var/run/docker.sock` + `-e HOST_REPO_ROOT="$PWD"`：`smoke` 步骤会再拉起
  全新的旁路容器（sibling container，借宿主机自己的 dockerd，不是嵌套 docker-in-docker）去验证 22.04
  和 24.04 的桌面环境。旁路容器的 `-v` 挂载源必须是宿主机上的真实路径，而不是这个容器自己看到的
  `/repo`——dockerd 跑在宿主机上，会按宿主机的文件系统解析挂载源，`HOST_REPO_ROOT` 就是用来传这个
  真实路径的。
- `--tmpfs /repo/.venv`：如果你自己的开发目录下已经有 `.venv`（常见），直接整个仓库挂载进容器会把
  它带进去。`run.sh` 的启动脚本会优先用 `.venv/bin/python`，但那个符号链接通常指向宿主机的绝对路径
  （如 `/usr/bin/python3`），在容器里会解析成一个完全不同、没装任何依赖的解释器。用 `--tmpfs` 盖住它
  即可，不需要也不应该在容器里直接修改宿主机的 `.venv`。

依赖安装顺序（含 `SAM2_BUILD_CUDA=0`、`GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_0`/`GIT_CONFIG_VALUE_0`
三个 sam2 符号链接变量）逐字照抄 `release.yml` 的 `build-linux` job，这样本地验证的环境和 CI 一致。

六个步骤，和 `local-build.ps1` 对应，可以用 `--steps` 只跑一部分（例如 `--steps build,layers`）：

| 步骤 | 内容 |
|---|---|
| `tests` | 仓库权威测试命令：`pytest tests labeling_tool/tests annotation_tool/tests` |
| `build` | `pyinstaller packaging/labeling_tool.spec` |
| `selftest` | 对刚构建的二进制跑 `--selftest=full`（`xvfb-run`） |
| `layers` | 打印 runtime id，校验应用层体积护栏（>20 MB 即失败），生成 update zip |
| `deb` | `packaging/deb.py build`，默认快速压缩，产出单个 deb |
| `smoke` | 与 CI 一致：22.04 桌面环境可用性、安装 + selftest、更新往返（用同一次构建的 zip 执行真实的 `--apply-update`）、24.04 交叉验证 |

`layers` 步骤打印出的 runtime id，和 Windows 的 runtime id 一样，发布前要记下来和上一个 release 的
资产名核对（见下面「核对 CI 日志中的 Linux runtime id」）——**但这是两个平台各自独立的 runtime id**，
Windows 和 Linux 的运行时层文件列表本来就不同，两者之间不需要也不可能相等，只需要分别对比同一
平台前后两次构建。

每一处会调用被测程序、`dpkg` 或拉起容器的地方都包了超时（`bounded`，对应 Windows 侧
`bounded.ps1` 的 `Invoke-Bounded`）——这个项目被挂起坑过（`installer.iss` 里一个 `MsgBox` 曾让
CI 挂了 96 分钟），超时会清楚报出是哪一步、等了多久，而不是无限挂起。

`smoke` 步骤与 CI 的 `build-linux` 安装检查逐项对应（本地先跑绿，CI 再按同样的逻辑复核）：

1. **22.04 桌面可用性**：全新的 `ubuntu:22.04` + `ubuntu-desktop-minimal`，只做 `dpkg -i`。
   一台普通桌面本来就应该具备 deb 声明的全部依赖；需要 `apt-get install -f` 就说明普通用户也装不上。
2. **安装 + selftest**：在外层容器里 `dpkg -i` 刚构建的 deb，再无头（`xvfb-run`）运行已安装程序的
   `--selftest=full`。
3. **更新往返**：删掉一个已安装的应用层文件，让已安装的程序用**同一次构建**的 update zip 执行真实的
   `--apply-update`，确认文件已恢复、`.update-journal` 已清除，并且 selftest 仍然通过。
4. **24.04 交叉验证**：全新的 `ubuntu:24.04` 桌面容器里安装并跑 selftest，证明“在 22.04 上构建、
   同时跑在两个版本上”不只是一个假设（后台启动，与第 1 步并行）。

这几步里的 `dpkg -i` 都**不允许**跟 `apt-get install -f`：需要它就说明 `packaging/deb.py` 里
`RUNTIME_DEPENDS` 遗漏了某个依赖，应该作为 bug 报告。

### 手动安装与卸载

```bash
sudo dpkg -i lm-labeling-tool_<版本>_amd64.deb
sudo apt purge lm-labeling-tool
```

安装只需这一个包，正常情况下一次成功。

**从旧的两个 deb 迁移**：装过旧版（`lm-labeling-tool` + `lm-labeling-tool-runtime` 两个包）的机器，
先把两个包都卸掉，再安装新的单个 deb：

```bash
sudo apt purge lm-labeling-tool lm-labeling-tool-runtime
sudo dpkg -i lm-labeling-tool_<版本>_amd64.deb
```

卸载（`purge`）会删除整个 `/opt/lm-labeling-tool`
（应用内更新绕过了 dpkg，`postrm` 负责清掉这些文件；`preinst` 在完整安装前清理应用层目录，避免残留）；
用户数据 `~/.local/share/lm-labeling-tool/` 会保留。

### 核对 CI 日志中的 Linux runtime id

`build-linux` job 的「Compute the runtime id and write build info」步骤会打印
`runtime id: r<8位hex>`。它与 Windows 侧的 runtime id 相互独立（两个平台的运行时层文件列表本来
就不同），不需要跨平台一致，只需要**同一平台**前后两次构建在运行时未变时保持一致。

### 两份锁文件

`packaging/build-lock.txt`（Windows）和 `packaging/build-lock-linux.txt`（Linux）各自独立锁定依赖，
只影响对应平台的 runtime id。已安装用户在运行时未变的平台上收到约 1–2 MB 的 zip，运行时变了的平台
则收到完整包的提示。两个平台共用一个 tag，发布节奏是绑在一起的。

## CI 的手动运行

在 Actions 页面（或 `gh workflow run release.yml`）手动运行 `release`，两个平台默认用快速压缩构建，
只上传构建产物、不发布。勾选 `release_compression`（命令行 `-f release_compression=true`）后，会像真正的
发布那样使用发布级压缩并强制检查资产大小上限——仍然不发布。**打 tag 之前先这样演练一次。**
