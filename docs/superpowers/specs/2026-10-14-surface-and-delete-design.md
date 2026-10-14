# 拍摄面修改与照片删除 — 设计

日期：2026-10-14
状态：设计已确认；接口细节按 §7 决定（后端消息为准，v1.0.16 文档由我们整理）
来源：用户反馈（后端负责人，2026-10-13 21:18），原文要点见 §1

## 1. 背景与目标

后端已经（或即将）调整 API，请标注工具增加两个功能：

1. **拍摄面（촬영면）修改**
   - 照片列表接口给每张照片加 3 个字段：`surface`（`floor` / `wall` / `ceiling` / `null`，服务器判定）、
     `tiltDeg`（拍摄角度，参考用，可能为 `null`）、`tiltSource`（`sensor` 手机传感器 / `manual` 有人改过）。
   - 界面显示 `surface`（`null` 显示「모름」），`tiltDeg` 作参考显示在旁边。
   - **工具里不做判定**，直接用服务器的 `surface`（判定基准由服务器管理）。
   - 每张照片可用「바닥 / 벽 / 천장」按钮修改，不需要输入数字。
   - 上传时只把改过的照片放进 `surfaceUpdates`，不重新上传掩码等图片。
2. **照片删除**
   - 按删除只标记「삭제 예정」，上传时放进 `deletes`，由服务器删除。
   - 不可恢复，计测值、보수 구역、评论一起删除，必须有确认框。
   - 删除后后面照片的报告编号依次前移；按编号范围分工的情况存在，所以上传后要重新取列表。

**上传格式**：都放进现有 V4（register-annotations）：

```json
{
  "editBatchId": "...",
  "sessionId": 76,
  "items": [ ...与现在相同... ],
  "surfaceUpdates": [ {"timestamp": 1789000000000, "surface": "wall"} ],
  "deletes":        [ {"timestamp": 1789000000000} ]
}
```

- `items` 可以为空；三个列表有一个即可。
- 响应新增 `deleted`、`skipped`（已被删除或不存在的照片）；别人先删掉的照片不报错，出现在 `skipped`。
- 同一个 `editBatchId` 可重试；上传中断时用同一 ID 重试。

**成功标准**

- 打开作业，列表每行显示拍摄面；侧边栏能看到当前照片的拍摄面和角度。
- 改了拍摄面的照片显示 ●，上传后服务器得到 `surfaceUpdates`，不重新上传它的图片（若掩码没改）。
- 标记删除 → 列表显示删除线和「삭제 예정」→ 上传时确认 → 服务器删除 → 本地移除，其余照片编号更新。
- 别人先删掉的照片出现在 `skipped`，本地同样移除，不报错。
- 上传中断后再上传，结果正确（不重复删除、不漏）。

**不做**：工具内判定拍摄面；编辑 `tiltDeg`；删除前的本地「回收站」；批量选择多张照片一次标记（逐行按钮即可）。

## 2. 已确认的决定

| 问题 | 决定 |
|---|---|
| 拍摄面显示位置 | 图片列表加一列「면」；修改按钮在「표시 · 축척」组新的一行 |
| 删除按钮位置 | 图片列表**每行最右边**一个删除按钮（点一下标记，再点取消） |
| 确认框时机 | 标记时不问；**上传时**有删除就弹一次确认框 |
| 上传后 | 服务器确认删除的照片从本地移除；再取一次该作业的照片列表（只取数据不下载图片），更新编号与拍摄面；范围视图按照片（timestamp）保留 |

## 3. 数据（manifest）

`PhotoEntry` 新增（都有默认值，旧 manifest 照常读取）：

| 字段 | 含义 |
|---|---|
| `surface: str \| None` | 服务器值（`floor` / `wall` / `ceiling` / `None`） |
| `tilt_deg: float \| None` | 服务器值 |
| `tilt_source: str \| None` | 服务器值（`sensor` / `manual`） |
| `surface_edit: str \| None` | 本地修改后的值；`None` = 没改。改回服务器值时清为 `None` |
| `delete_pending: bool` | 本地标记删除 |

- 显示的拍摄面 = `surface_edit` 若有，否则 `surface`。
- `keep_from`（重新获取作业）保留 `surface_edit` 与 `delete_pending`；服务器字段取新值。
- 获取作业（`fetch_dialog`）写入三个服务器字段。
- `●`（需要上传）条件扩展为：现有的掩码条件（已保存且未同步），或 `surface_edit` 非空，或 `delete_pending`。
  拍摄面和删除用各自的字段判断，不借用 `synced`，0.2.14 的 synced 规则不变。

## 4. 界面

**图片列表行**（`TwoPartItemDelegate`）：

```
│ ●  번호  면    파일 이름                 🗑 │
│ ✓  45-1  바닥  stitched_...jpg           🗑 │
│ ●  45-3  모름  s̶t̶i̶t̶c̶h̶e̶d̶_̶.̶.̶.̶  삭제 예정  🗑 │
```

- 「면」列：바닥 / 벽 / 천장 / 모름；改过的值用琥珀色（与手动比例尺一致的「人改过」颜色）。表头加「면」。
- 删除按钮：行最右边固定宽度的图标（Lucide `trash-2`），点击切换 `delete_pending`，**不改变当前选中的照片**；
  标记后文件名删除线、行文字红色、显示「삭제 예정」，图标高亮。鼠标悬停有提示。
- 侧边栏最小宽度 340 px 不变：文件名继续按剩余宽度省略。

**「표시 · 축척」组新增一行**：

```
촬영면 [바닥][▣벽][천장]   87°
```

- 三个可选中按钮，当前显示值高亮；`None` 时都不亮，前面显示「모름」。
- 角度灰字：`tiltDeg` 取整加「°」，`None` 显示「—」；`tiltSource == manual` 时提示文字说明「수정된 값」。
- 点击服务器原值 = 撤销修改（`surface_edit = None`）。
- 900 px 高窗口、ko / zh / en 下任何工具都不出现滚动条（多一行，必要时缩短文字，不加宽）。

**标记删除的照片**：仍可查看；它的掩码 / 拍摄面修改在上传时被跳过（删除优先）。

## 5. 上传

- 上传按钮条件：有改过的掩码，或有 `surface_edit`，或有 `delete_pending`（离线时照旧不可用）。
- 有删除时先弹确认框（`QMessageBox`，按钮文字走 i18n）：列出编号（最多列 20 个，其余写「외 N장」），
  说明不可恢复、计测值 · 보수 구역 · 댓글一起删除；按钮 [삭제하고 업로드] [취소]。取消 = 整个上传取消。
- 请求组装（`api/uploader.upload_session` 扩展）：
  - `items`：照旧，排除 `delete_pending` 的照片；仍按 33 张一批（每张 3 个文件，V2 上限 100）。
  - `surfaceUpdates`：`surface_edit` 非空且不删除的照片 `{"timestamp", "surface"}`。
  - `deletes`：`delete_pending` 的照片 `{"timestamp"}`。
  - `surfaceUpdates` / `deletes` 按每批上限（暂定 100，等文档）切分，附在前几个 V4 请求里；没有 items 的批次
    只带这两个列表（`items: []`）。每批 `editBatchId` = `<id>-<idx>`（现有规则），重试稳定。
- 响应处理：
  - `items` 的确认规则不变（`updatedPhotoCount`）。
  - `deleted` + `skipped` 里的 timestamp → 本地删除（见 §6）。
  - 批次成功 → 该批 `surfaceUpdates` 的照片：`surface = surface_edit`，`surface_edit = None`，`tilt_source = "manual"`
    （随后刷新列表会以服务器值为准）。
  - 批次失败 → 该批的删除与拍摄面修改保持待上传，可再次上传。
- 上传中再次保存 / 再改拍摄面：沿用「上传中保存的照片保持 ●」规则。

## 6. 上传之后

1. 本地删除：manifest 移除该照片；作业文件夹里删掉它的 Origin、Detected、Labeling（掩码 + bbox JSON）、
   HighLight、Repair15、Result 文件。当前正在看的照片被删时，跳到相邻照片（无照片则清空画面）。
2. 刷新：后台调用照片列表接口取该作业**全部**照片的数据（分页，与获取作业相同），对本地仍存在的照片更新
   `report_photo_num`、`surface`、`tilt_deg`、`tilt_source`（不下载图片，不改 `surface_edit` 外的本地状态）。
   刷新失败只记日志和状态栏提示，不影响已完成的上传。
3. 列表按新编号重排；范围视图保留同一批照片（按 timestamp）。

## 7. 接口细节的决定（2026-10-14）

后端不另发文档，以其消息为准；v1.0.16 文档由我们整理（见 §9）。2026-10-14 实测服务器的照片列表**还没有**
`surface` / `tiltDeg` / `tiltSource`（后端尚未部署），客户端对缺字段按 `null` 处理。

- 照片列表接口 = v1.0.15 的 **V1** `GET /api/viewer/sessions/{id}/photos/`（消息里的「V2」按 V1 处理）。
- `surfaceUpdates` / `deletes` 每个请求各最多 **100** 条（与现有批量上限一致），写进 v1.0.16。
- 响应 `deleted` / `skipped` 为 timestamp 数组；客户端同时接受 `[{"timestamp": ...}]`。
- `surface` 合法值只有三个；其他值显示「모름」、不可回传。
- 类别提案的 V5 / V6 编号沿用（v1.0.15 里本地 포토뷰어 只有 V0～V4，不冲突）。

字段名和上限集中在 `api/edit_fields.py`，后端实际实现若不同只改一处。

**核对结果（2026-10-14，Task 8）**：v1.0.16 文档按客户端实际实现整理，样例由
`labeling_tool/tests/test_api_doc_examples.py` 验证（照片列表项 → `photo_fields`；`register_annotations`
组装的请求体与文档样例逐字段相同；响应 `deleted` / `skipped` → `timestamps_in`）。后端消息与客户端没有冲突；
后端未说明、由我们在文档里写明或列入「서버 측 확인 요청」的有：`surfaceUpdates` 里的照片已不存在时的处理
（建议跳过，否则整批失败、同批 `deletes` 也不生效）、同一 `editBatchId` 重试（200）是否仍返回 `deleted` / `skipped`、
`updatedPhotoCount` 是否计入 `surfaceUpdates` / `deletes`（客户端只与 `items` 数比较，两种都能工作）、
V1 新字段的部署时间。

## 8. 测试

- TDD；三目录命令全绿（当前 1012）。
- manifest：新字段默认值、旧文件读取、`keep_from` 保留本地标记。
- 获取作业写入服务器字段。
- 列表：「면」列文字、改过的颜色、删除按钮点击切换且不切换当前照片、删除样式。
- 侧边栏：拍摄面按钮、撤销修改、`None` 显示、角度显示；340 px / 900 px / 三语言不滚动。
- 上传：请求组装（只有删除、只有拍摄面、混合、超过一批）、确认框（取消即不上传）、`deleted` / `skipped`
  本地移除文件、失败保持待上传、重试同一 ID。
- 刷新：编号更新、范围视图保留。
- 用假客户端测试，不连真服务器；文档到后补一个按文档样例的请求 / 响应测试。

## 9. v1.0.16 文档

功能完成后整理 `~/Downloads/api-reference_v1.0.16.md`（**不进仓库**：仓库公开，文档含内部地址与密钥名）（韩语，格式与 v1.0.15 相同）：v1.0.15 全文 + 拍摄面（V1 字段、
V4 `surfaceUpdates`）+ 删除（V4 `deletes`、响应 `deleted` / `skipped`、说明）+ 类别（V5 / V6、V4 `classAreas`、
像素值定义，标注「제안 · 서버 구현 전」）。变更履历写在开头。
