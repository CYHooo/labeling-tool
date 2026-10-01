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

## 发布步骤

1. **本地完整验证**（约 15 分钟）：

   ```powershell
   powershell -File packaging\ci\local-build.ps1 -Venv C:\lt\venv
   ```

   依次运行：测试套件 → PyInstaller 构建 → 自检与启动冒烟测试 → 分层并计算 runtime id → 编译安装包
   → 安装冒烟测试（完整包、再叠加应用包、错配包必须被拒绝、卸载）。

   安装冒烟测试使用独立的测试 AppId（`/DMyTestInstall=1`），不会影响本机正式安装的程序。

   只修改了部分内容时，可以只跑相关步骤，例如 `-Steps tests` 或 `-Steps build,selftest,layers`。

2. **记下输出的 `runtime id`。** 与上一个版本的 release 资产名 `LM_LabelingTool-App-v<版本>-r<id>.exe`
   对比：
   - **相同**：用户会收到约 1 MB 的增量更新。
   - **不同**：用户需要下载完整安装包。只有升级依赖（修改了 `build-lock.txt`）、更换 Python 或调整 spec
     中的运行时配置时，才应该出现这种情况。如果你没有做这些改动 id 却变了，**先别发布**，用
     `diag\runtime-manifest-*.txt` 对比找出原因。

3. **打 tag。** 版本号只来自 tag（写入 `build-info.json`），代码里不需要改：

   ```bash
   git tag v1.4.0
   git push origin v1.4.0
   ```

   CI 流程：安装依赖（有 pip 缓存）→ 构建 → 自检 → 编译安装包 → 发布到 GitHub Release。

   - **只改了代码**（runtime id 与上一个 release 相同）：不重新压缩完整包，而是复用上一个 release 的
     完整包，先按它原来的校验和验证，再以本版本的文件名重新发布。新用户装上的是上一版的代码，
     第一次启动时会自动收到约 2 MB 的更新。这是耗时最短的情况。
   - **运行时变了**：照常用最高压缩（4 线程）重新构建完整包，压缩约需 3–4 分钟。

   是否复用由 CI 自动判断，日志里会出现 `reusing ...` 或 `full build`。

4. **核对 CI 日志中的 `runtime id` 与第 2 步是否一致。** 本地与 CI 使用同一份锁文件和同一个 Python，
   结果应当完全相同。

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

Windows 和 Linux 由**同一个 tag** 从同一个工作流（`release.yml`）构建发布，产物共四个：
两个 Windows 安装包（见上）和两个 Debian 包：

| 文件 | 内容 | 大小 | 用途 |
|---|---|---|---|
| `lm-labeling-tool-runtime_<版本>_amd64.deb` | 运行时层（Python、PyQt5、torch、CUDA） | 约 1.4 GB | **第一次安装**时需要 |
| `lm-labeling-tool_<版本>-r<runtime id>_amd64.deb` | 应用层（我们自己的代码） | 约 20 MB | 日常更新 |

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
  两个全新的旁路容器（sibling container，借宿主机自己的 dockerd，不是嵌套 docker-in-docker）分别验证
  「声明的依赖是否足够」和「在 24.04 上装、能不能跑」。这两个旁路容器的 `-v` 挂载源必须是宿主机上的
  真实路径，而不是这个容器自己看到的 `/repo`——dockerd 跑在宿主机上，会按宿主机的文件系统解析挂载
  源，`HOST_REPO_ROOT` 就是用来传这个真实路径的。
- `--tmpfs /repo/.venv`：如果你自己的开发目录下已经有 `.venv`（常见），直接整个仓库挂载进容器会把
  它带进去。`run.sh` 的启动脚本会优先用 `.venv/bin/python`，但那个符号链接通常指向宿主机的绝对路径
  （如 `/usr/bin/python3`），在容器里会解析成一个完全不同、没装任何依赖的解释器。用 `--tmpfs` 盖住它
  即可，不需要也不应该在容器里直接修改宿主机的 `.venv`。

依赖安装顺序（含 `SAM2_BUILD_CUDA=0`、`GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_0`/`GIT_CONFIG_VALUE_0`
三个 sam2 符号链接变量）逐字照抄 `release.yml` 的 `build-linux` job，这样本地验证的环境和 CI 一致。

六个步骤，和 `local-build.ps1` 一一对应，可以用 `--steps` 只跑一部分（例如 `--steps build,layers`）：

| 步骤 | 内容 |
|---|---|
| `tests` | 仓库权威测试命令：`pytest tests labeling_tool/tests annotation_tool/tests` |
| `build` | `pyinstaller packaging/labeling_tool.spec` |
| `selftest` | 对刚构建的二进制跑 `--selftest=full`（`xvfb-run`） |
| `layers` | 打印 runtime id，校验应用层体积护栏（>20 MB 即失败） |
| `deb` | `packaging/deb.py build`，默认快速压缩 |
| `smoke` | 两个全新旁路容器：充分性+错配守卫（裸容器）、24.04 可用性交叉验证（桌面容器） |

`layers` 步骤打印出的 runtime id，和 Windows 的 runtime id 一样，发布前要记下来和上一个 release 的
资产名核对（见下面「核对 CI 日志中的 Linux runtime id」）——**但这是两个平台各自独立的 runtime id**，
Windows 和 Linux 的运行时层文件列表本来就不同，两者之间不需要也不可能相等，只需要分别对比同一
平台前后两次构建。

每一处会调用被测程序、`dpkg` 或拉起容器的地方都包了超时（`bounded`，对应 Windows 侧
`bounded.ps1` 的 `Invoke-Bounded`）——这个项目被挂起坑过（`installer.iss` 里一个 `MsgBox` 曾让
CI 挂了 96 分钟），超时会清楚报出是哪一步、等了多久，而不是无限挂起。

`smoke` 步骤为什么要两个全新的旁路容器而不是复用跑 `build`/`tests` 的外层容器：外层容器要能跑
起 Qt 的 xcb 平台（`tests`/`build`/`selftest` 都需要），这就必须提前装上和 `RUNTIME_DEPENDS`
等价的那批库，而这样一来外层容器就不再是「裸机」，拿它去验证「`RUNTIME_DEPENDS` 声明的库是否
足够」就是同义反复（先装上声明的依赖，再验证依赖被满足）。所以这两个问题被拆到两个全新、只装了
`dpkg-dev`/`xvfb`/`build-essential`（充分性）或桌面元包（可用性）的旁路容器里单独验证，和
`release.yml` 现在的写法保持一致。

**已知未解决问题**：`smoke` 步骤的充分性检查（裸容器里 `xvfb-run` 跑已安装的二进制）在排查过程
中复现过一次挂起而非正常报错，超时后被 `bounded` 杀掉。已确认 `QT_QPA_PLATFORM=offscreen`
不受影响；已确认不是「某个 .so 找不到」（那会立刻报错退出，不会挂起）；已确认在外层构建容器里
补装 `RUNTIME_DEPENDS` 等价的库能让 xcb 立刻跑通，但把这批库也装进充分性容器会让检查失去意义。
尚未确认的是：`apt-get install dpkg-dev xvfb build-essential` 自身拉进来的传递依赖，是否已经足够
让 xcb 不挂起——这正是该检查本来要回答的问题。脚本里对应位置留了详细注释。如果你跑到这一步
超时，这是一个待查的真实问题，不是脚本的缺陷；可以对照 CI 的 `build-linux` job（跑在真实的
GH 托管 ubuntu-22.04 runner 上，不是裸 docker 镜像，环境可能更「富」）看是否复现。

### 手动安装

```bash
sudo dpkg -i lm-labeling-tool-runtime_<版本>_amd64.deb lm-labeling-tool_<版本>-r<id>_amd64.deb
```

两个包的顺序不重要，`dpkg` 会按 `Depends` 自行处理。**正常情况下这条命令应当一次成功**——
CI 的安装冒烟测试就是在验证这一点（见下）。如果提示缺少系统库（比如某个 `libxcb-*` 或
`libglib2.0-*`），再补一次：

```bash
sudo apt-get install -f
```

这只应该在手动安装、且系统本身缺少常见桌面库时发生；CI 不允许这一步，出现这种情况说明
`packaging/deb.py` 里 `RUNTIME_DEPENDS` 遗漏了某个依赖，应该作为 bug 报告。

应用包的 `Depends` 锁定了精确的 runtime id（`lm-labeling-tool-runtime (= 0~<id>)`），这就是
Linux 版本的「错配 installer 守卫」：对着不匹配的 runtime 装应用包，`dpkg -i` 会直接拒绝，不需要
`installer.iss` 那种手写 Pascal 逻辑。

### 核对 CI 日志中的 Linux runtime id

`build-linux` job 的「Compute the runtime id and write build info」步骤会打印
`runtime id: r<8位hex>`。它与 Windows 侧的 runtime id 相互独立（两个平台的运行时层文件列表本来
就不同），不需要跨平台一致，只需要**同一平台**前后两次构建在运行时未变时保持一致。

### 运行时变化时，两个平台都是全量

`packaging/build-lock.txt`（Windows）和 `packaging/build-lock-linux.txt`（Linux）各自独立锁定依赖。
升级任意一份锁都只影响对应平台的 runtime id，但发布节奏是绑在一起的——两个平台共用一个 tag。
也就是说：

- 只有 Windows 的锁变了：这次发布里，Windows 用户收到完整安装包，Linux 用户仍然只需要下载
  app 包（约 20 MB）。
- 只有 Linux 的锁变了：反过来，Linux 用户收到两个 deb（完整安装），Windows 用户仍然只需要
  app 安装包。
- 两份锁都没变（纯代码改动）：两个平台都只需要各自的小更新包。

`build-linux` job 同样会在运行时未变时复用上一个 release 的 runtime deb（见
`packaging/reuse_runtime.py`），跳过重新压缩 ~1.4 GB 的 xz，逻辑与 Windows 侧的
`reuse_full.py` 对称。

### CI 里的安装冒烟测试

`build-linux` job 在构建完两个 deb 之后，会做三件 Windows 侧没有的事。这三步和上面
`packaging/ci/local-build.sh` 的 `smoke` 步骤是同一套检查——本地先跑绿，CI 再按同样的逻辑复核：

1. `sudo dpkg -i` 装上两个真实的 deb，然后无头（`xvfb-run`）跑一次 `--selftest`。
2. 手工拼一个 runtime id 对不上的「错配」应用 deb，断言 `dpkg -i` 会拒绝安装。
3. 在一个全新的 `ubuntu:24.04` 容器里重复第 1 步，证明「在 22.04 上构建、同时跑在两个版本上」
   不只是一个假设。

这三步里的 `dpkg -i` 都**不允许**跟 `apt-get install -f`：需要它就说明 `RUNTIME_DEPENDS`
声明的库，用户的机器上大概率也没有。

## CI 的手动运行

在 Actions 页面手动运行 `release`，两个平台都会用快速压缩构建，并且只上传构建产物、不发布。
可以在不打 tag 的情况下演练一次发布构建。
