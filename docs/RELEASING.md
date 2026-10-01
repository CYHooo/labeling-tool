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

`build-linux` job 在构建完两个 deb 之后，会做三件 Windows 侧没有的事（Linux 没有
`local-build.ps1` 那样的本地验证脚本，所以这些检查目前都放在 CI 里）：

1. `sudo dpkg -i` 装上两个真实的 deb，然后无头（`xvfb-run`）跑一次 `--selftest`。
2. 手工拼一个 runtime id 对不上的「错配」应用 deb，断言 `dpkg -i` 会拒绝安装。
3. 在一个全新的 `ubuntu:24.04` 容器里重复第 1 步，证明「在 22.04 上构建、同时跑在两个版本上」
   不只是一个假设。

这三步里的 `dpkg -i` 都**不允许**跟 `apt-get install -f`：需要它就说明 `RUNTIME_DEPENDS`
声明的库，用户的机器上大概率也没有。

## CI 的手动运行

在 Actions 页面手动运行 `release`，两个平台都会用快速压缩构建，并且只上传构建产物、不发布。
可以在不打 tag 的情况下演练一次发布构建。
