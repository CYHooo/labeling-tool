# 启动流程拆分:登录页 + 数据拉取页

日期:2026-06-17
状态:已确认设计,待实现

## 背景

当前 `labeling_tool/ui/connect_dialog.py` 的 `ConnectDialog` 把所有启动配置塞在一个对话框里:`BASE URL`、`X-Viewer-Api-Key`、`sessionId`、`fromNum`、`toNum`,以及「가져오기(在线拉取)」「이미 받은 세션 열기(离线打开)」两个动作。

需求是把它拆成"类登录"的两段式流程:
1. **前置登录页**:只填 URL/KEY,类似登录。
2. **数据拉取页**:`sessionId` 从手输改为**下拉菜单**(数据来自一个尚未申请的"获取 session_id 列表"API),图片数量(`fromNum/toNum`)仍手输。

## 已确认的决策

| 决策点 | 选择 |
|--------|------|
| 界面结构 | **两个独立窗口**:登录页验证后关闭,再弹拉取页 |
| 登录验证 | **仅保存不验证**,登录只把 URL/KEY 存进 `config.json`,真正的网络错误留到拉取页发生 |
| 离线入口 | 放在**登录页**(离线打开本地数据不需要联网/登录) |
| 本次范围 | **两页都做**,获取 ID 的 API 先档位预留(隔离在一个 `list_sessions()` 方法里) |
| 离线选会话 | **扫描本地目录**(`data/session_*`)出下拉,不再手输 sessionId |
| 登录按钮文案 | 「다음」 |
| 返回登录 | 不需要 |

## 架构

把 `connect_dialog.py` 拆为两个 `QDialog`,由 `app.py` 编排。

### 组件

**`LoginDialog`(前置登录页,首先弹出)**
- 字段:`BASE URL`、`X-Viewer-Api-Key`(密码框),从 `config.json` 预填。
- 离线区:下拉菜单(扫描 `data/session_*` 中含 `manifest.json` 的目录)+「이미 받은 세션 열기」按钮 → 直接打开选中的本地会话。
- 主按钮「다음」:校验 URL/KEY 非空 → 存入 `config.json` → `accept()`,放行到拉取页。**不联网、不验证**。
- 输出供 `app.py` 判别走哪条路:
  - 离线分支:`self.workspace` / `self.manifest` 已就绪(直接进主窗口)。
  - 在线分支:`self.base` / `self.key` 已就绪,`workspace` 为 `None`(进拉取页)。

**`FetchDialog`(数据拉取页,登录后弹出)**
- 构造时接收 `base`、`key`,内部建 `ViewerApiClient`。
- `showEvent`/打开时调用 `client.list_sessions()` 填充 `sessionId` 下拉:
  - 成功 → 下拉填入会话项,显示文案 `session {id}`(有 `createdAt/photoCount` 则附带)。
  - 失败(接口未上线/网络错)→ 弹一次提示,**降级**为可编辑下拉(editable combo),用户可手输 id,工具仍可用。
- 字段:`sessionId`(下拉)、`fromNum`/`toNum`(spinbox,沿用)。
- 「가져오기」按钮:沿用现有 V1 → 下载 → prebuild Rebuilt → 保存 manifest 流程,sessionId 取自下拉。
- 进度条 + 状态栏沿用。

**`app.py` 编排**
```
login = LoginDialog()
if not login.exec_(): return 0          # 取消 → 退出
if login.workspace is not None:         # 离线分支
    ws, manifest = login.workspace, login.manifest
else:                                   # 在线分支
    fetch = FetchDialog(base=login.base, key=login.key)
    if not fetch.exec_(): return 0
    ws, manifest = fetch.workspace, fetch.manifest
# 用 client(若有 base/key)打开主窗口,与现状一致
```

### API 客户端:新增 `list_sessions()`

在 `ViewerApiClient` 加一个隔离方法,带"接口待上线"注释,按**假定契约**实现 + 容错解析:

```
GET {base}/api/viewer/sessions/      header: X-Viewer-Api-Key
假定响应:
{ "sessions": [ {"sessionId": 18, "createdAt": "...", "photoCount": 42}, ... ] }
```

- 归一化返回 `list[dict]`,每项至少含 `sessionId`(int)。
- 兼容裸数组形态 `{"sessions": [18, 19, 20]}` → 归一化为 `[{"sessionId": 18}, ...]`。
- 走与其它 V-API 调用一致的 `self._s.get(...)` + `_raise_for_error` + `vlog()` 计时日志。
- 接口真上线后若路径/字段不同,仅改此方法。

## 数据流

```
LoginDialog ──(在线: base, key)──> FetchDialog ──list_sessions()──> 下拉
     │                                  │
     │(离线: 扫描 data/session_*)         │(가져오기: V1→下载→prebuild→manifest)
     ▼                                  ▼
  Workspace+Manifest ───────────────> app.py ──> 主窗口
```

## 错误处理

- 登录页:URL/KEY 任一为空 → `QMessageBox.warning`,不放行。
- 离线下拉为空(本地无任何已下载会话)→「이미 받은 세션 열기」按钮禁用 + 提示文案。
- 拉取页 `list_sessions()` 失败 → 提示一次并降级为可手输下拉(不阻断)。
- 拉取页 V1/下载失败 → 沿用现有 `QMessageBox` 提示逻辑。

## 可测性与测试

GUI 对话框本身沿用现状不写测试,但把可测逻辑抽成纯函数并补单测:
- `list_sessions()` 容错解析:对象数组 / 裸数组 / 缺字段三种输入(用 mock 的 `requests` 响应,参照现有 `tests/test_client.py`)。
- 本地会话扫描函数:`data/session_*` 中含 manifest 的列出 + 排序(用临时目录)。

`_load_config` / `_save_config` 逻辑保留(可复用现有的)。

## 不做(YAGNI)

- 不做登录态/token 持久化(仅存 URL/KEY,与现状一致)。
- 不做"返回登录"导航。
- 不做在线会话的本地缓存比对/增量,沿用现有整会话下载。
- 不动主窗口、画布、上传等其它部分。

## 受影响文件

- 新增 `labeling_tool/ui/login_dialog.py`(`LoginDialog` + 本地会话扫描函数)。
- 新增 `labeling_tool/ui/fetch_dialog.py`(`FetchDialog`,承接现 `ConnectDialog` 的在线拉取逻辑)。
- 删除 `labeling_tool/ui/connect_dialog.py`(逻辑迁移到上面两个文件;`_load_config`/`_save_config`/`_run_prebuild` 等共用辅助移到合适位置)。
- 修改 `labeling_tool/app.py`(编排:LoginDialog → 离线进主窗口 / 在线进 FetchDialog)。
- 修改 `labeling_tool/api/client.py`(新增 `list_sessions()`)。
- 新增测试 `labeling_tool/tests/test_list_sessions.py`(`list_sessions()` 容错解析 + 本地会话扫描)。

> 决策:**拆为两个文件**而非单文件多类——保持每个对话框文件聚焦、便于独立理解与测试,符合现有 `ui/` 下按职责分文件的风格。
