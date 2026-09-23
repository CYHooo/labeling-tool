# Windows 安装程序 + 软件内自动更新

日期：2026-09-23
状态：设计待确认
分支：`feat/installer-update`（基于 `main` c3fa50e）

## 背景 / 目标

v1.0.0 分发的是压缩包（lite `.zip` / full `.7z`），用户要自己解压、自己去 GitHub 看有没有新版本。目标是做成"正常软件"的样子：

1. **安装程序**：下载 `LabelingTool-lite-Setup-v1.0.0.exe` 双击安装 → 开始菜单快捷方式 → 控制面板可卸载。
2. **软件内更新**：启动时后台检查新版本，有新版本弹窗询问，确认后自动下载、校验、安装、重启。

用户选择（2026-09-23）：安装程序（不再发布压缩包）；弹窗提示 + 一键更新；**lite 与 full 都支持自动更新**。

非目标：代码签名（SmartScreen 提示仍会出现）、增量/差分更新、静默强制更新、自动回滚、macOS/Linux 安装包。

## 1. 安装程序（Inno Setup）

- `packaging/installer.iss`（Inno Setup 6 脚本），由 CI 在 PyInstaller 产物 `dist/LabelingTool/` 之上生成。
- 关键设置：
  - `PrivilegesRequired=lowest`、`DefaultDirName={autopf}\LabelingTool`（无管理员权限时落到 `%LOCALAPPDATA%\Programs\LabelingTool`）→ **更新不需要管理员权限**。
  - `AppId` 固定（两个变体用**不同** AppId，允许同一台机器同时装 lite 和 full，互不覆盖）。
  - `AppVersion` 由 CI 传入（`/DMyAppVersion=1.0.1`）。
  - `ArchitecturesInstallIn64BitMode=x64compatible`、`ArchitecturesAllowed=x64compatible`。
  - `Compression=lzma2/max`、`SolidCompression=yes`。
  - 开始菜单快捷方式；桌面快捷方式为可选项（默认不勾）。
  - `[Run]` 项：安装结束后可选启动程序（静默更新时由更新器自己重启，见 §2）。
  - `UninstallDisplayIcon`、卸载时**保留**用户数据（`config.json`、`data\`、`checkpoint\`、`classes.json` 不在 `[Files]` 内，Inno 不会删除它们）。
- 安装后的目录（`{app}`）与现在的解压目录一致：`LabelingTool.exe` + `_internal\`，用户数据仍写在 exe 同目录。因为安装到用户目录，该目录可写。
- 产物命名：`LabelingTool-<variant>-Setup-v<version>.exe`。

## 2. 更新器

### 2.1 版本信息

CI 在 `dist/LabelingTool/` 写入 `build-info.json`（取代现在的 `VERSION.txt`）：

```json
{"version": "1.0.0", "variant": "lite", "commit": "c3fa50e"}
```

`labeling_tool/update/version.py` 读取它（frozen 时在 `app_home()`，源码运行时返回 `{"version": "0.0.0-dev", "variant": null}`，并使更新检查直接返回"无更新"）。

### 2.2 检查更新

`labeling_tool/update/checker.py`（纯逻辑，无 Qt）：

- `fetch_latest_release(repo, timeout) -> dict`：GET `https://api.github.com/repos/<repo>/releases/latest`（无需鉴权）。
- `pick_asset(release, variant) -> (name, url, size)`：按 `LabelingTool-<variant>-Setup-v*.exe` 匹配。
- `is_newer(latest, current) -> bool`：按 `packaging.version` 风格的数字元组比较（`1.0.10 > 1.0.9`）；解析失败视为"不更新"。
- `find_update(current, repo, timeout) -> UpdateInfo | None`：组合上述逻辑，返回版本号、资产 URL、大小、SHA256（见 §2.4）、发布说明。
- **所有网络/解析异常都向上抛出；调用方静默吞掉**（更新检查失败绝不打扰用户）。

### 2.3 触发时机与节流

- 启动时（`app.py` 创建 `LoginDialog` 之前）在 `QThread` 中检查，不阻塞界面。
- 节流：`update-state.json`（在 `app_home()`）记录 `last_check`（24 小时内不重复检查）与 `skipped_version`（用户点"跳过此版本"后不再提示该版本）。
- 菜单项「업데이트 확인」（主窗口 Help 菜单）可手动强制检查，忽略节流与跳过记录。

### 2.4 下载与校验

- Release 中附带 `SHA256SUMS.txt`（CI 生成，内容为每个安装程序的 `<sha256>  <filename>`）。
- `labeling_tool/update/downloader.py` 复用 `annotation_tool/segmenter/weights.py` 的模式：下载到 `%TEMP%\LabelingTool-update\<name>.part` → 校验 SHA256 → 重命名。进度回调、可取消。
- 校验失败 / 下载失败：删除临时文件，弹窗说明，不安装。

### 2.5 安装与重启

- 运行 `installer.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG=<temp>\update.log`，以 `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` 启动，随后应用**立即退出**（安装程序无法覆盖正在运行的 exe）。
- 安装脚本 `[Run]` 中加入 `Filename: "{app}\LabelingTool.exe"; Flags: nowait postinstall skipifsilent` 无法覆盖静默场景，因此改为：更新器传 `/RESTARTAPP` 自定义参数 → `.iss` 的 `[Run]` 用 `Check: WantsRestart` 在静默安装后也启动程序。
- 失败（安装程序返回非 0）时旧版本仍在，用户下次启动会再次收到提示。

### 2.6 界面

- 发现新版本：模态对话框（韩文）显示"현재 v1.0.0 → 최신 v1.0.1"、更新包大小、发布说明前若干行，按钮：**지금 업데이트** / **나중에** / **이 버전 건너뛰기**。
- full 变体在对话框中额外用醒目文字标明下载量（约 1.5 GB）。
- 下载进度：`QProgressDialog`（可取消），与 SAM2.1 权重下载一致的实现方式。

## 3. CI 改动（`.github/workflows/build-windows.yml`）

- build job 追加：写 `build-info.json` → 安装 Inno Setup（runner 预装；缺失时 `choco install innosetup -y`）→ `iscc /DMyAppVersion=... /DMyVariant=... packaging/installer.iss` → 产出 `LabelingTool-<variant>-Setup-v<ver>.exe`。
- 冒烟测试：`Setup.exe /VERYSILENT /DIR=<temp>\install /LOG=...` 静默安装到临时目录 → 运行安装后的 `LabelingTool.exe --selftest=<variant>` → 断言退出码 0 → 静默卸载。这验证安装程序本身可用，而不只是能生成。
- artifact 与 Release 资产：两个安装程序 + `SHA256SUMS.txt`（不再发布 zip/7z；zip 仍作为 artifact 保留，便于排查）。
- release job 生成 `SHA256SUMS.txt` 后与安装程序一并上传。

## 4. 目录结构

```
labeling_tool/update/
├── __init__.py
├── version.py      build-info.json 读取
├── checker.py      GitHub Releases 查询 + 版本比较（纯逻辑）
├── downloader.py   下载 + SHA256 校验（纯逻辑）
├── installer.py    静默安装命令构造与启动（纯逻辑 + subprocess）
└── ui.py           Qt：检查线程、提示对话框、进度对话框
packaging/installer.iss
```

## 5. 风险与应对

| 风险 | 应对 |
|---|---|
| 无代码签名 → SmartScreen 每个新版本都提示 | README 说明；后续可购买证书（每年约 100–400 美元）后在 CI 中签名 |
| full 安装程序接近 Release 单文件 2 GiB 上限（当前 7z 1.5 GB） | CI 中断言安装程序 < 1.9 GiB，超出则失败并提示改用分卷或精简依赖 |
| 更新中断导致程序损坏 | 先完整下载并校验，再启动安装程序；安装程序为原子替换，失败保留旧版本 |
| GitHub API 限流（未鉴权 60 次/小时/IP） | 24 小时节流；403/429 静默失败 |
| 公司网络 / 离线环境 | 所有网络错误静默；手动菜单项给出明确错误信息 |
| 用户把程序装到 `Program Files`（需管理员） | `PrivilegesRequired=lowest` 默认装到用户目录；若用户手动选了系统目录，更新时安装程序会自行请求提权 |
| 静默安装时程序仍在运行 | 更新器先退出应用再启动安装程序；`.iss` 设 `CloseApplications=force` 兜底 |

## 6. 测试

- 纯逻辑单测：版本比较（含 `1.0.10 > 1.0.9`、非法版本）、资产选择（按变体、缺失资产）、SHA256SUMS 解析、节流与跳过版本的状态读写、安装命令构造（参数、DETACHED 标志）。
- 下载：本地 HTTP 服务测试成功 / 校验失败 / 取消（复用 weights 测试的模式）。
- Qt：提示对话框三个按钮的行为（更新 / 稍后 / 跳过）、检查线程失败时不弹窗。
- CI：安装程序静默安装 → `--selftest` → 卸载。
- 人工（Windows）：装 v1.0.0 → 发布 v1.0.1 → 启动应用确认收到提示 → 一键更新 → 确认版本号变化且 `config.json`、`data\`、`checkpoint\` 全部保留。

## 7. 交付物

- `labeling_tool/update/`（5 个模块 + 测试）
- `packaging/installer.iss`
- `.github/workflows/build-windows.yml` 改动
- 主窗口 Help 菜单的「업데이트 확인」
- README：安装程序下载 / 安装 / 更新 / SmartScreen 说明；`docs/README.md` 索引追加本设计
