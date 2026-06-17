# 本地标注工具 `labeling_tool`(V API 闭环版)设计

- 日期:2026-06-12
- 状态:已批准,待实现计划
- 依据文档:`api-reference_v1.0.7.md` 第「로컬 포토뷰어 API」节(V1~V4)

## 背景与目标

`api-reference_v1.0.7` 新增了「本地 Photo Viewer API」(V1~V4),用于在**本地电脑**(非 AI 服务器)对 AI 产出的拼接图/掩膜进行人工标注:编辑均裂掩膜、生成保修区 OBB、计算计测值,并回传 EC2。

现有标注核心位于 `algorithms/05_detect/src/tools/labeling/`(约 3000 行、模块化良好),已实现笔刷掩膜编辑、OBB、ArUco 标尺(px/cm)、rebuild、crack metrics、Result 导出。其本地工作流与 V API 字段几乎一一对应。

**目标**:新建一个**自包含、可移植**的 `labeling_tool/` 文件夹,在现有标注能力外包一层「会话连接 + 数据获取(V1) + 上传(V2→V3→V4)」,使其能拷到本地 PC 独立运行,完成 `V1(下载) → 标注 → V2/V3/V4(上传)` 的完整闭环。

**核心约束**:最终交付物是一个可独立运行于本地 PC 的文件夹,不得依赖 `algorithms/05_detect` 整棵树。

## 已确认的设计决策

1. 范围:**完整闭环**(V1 + V2/V3/V4),而非仅获取。
2. 与现有代码关系:**整体复制成自包含包**(`core/`),非 import 旧包。旧工具为服务器端调试用,新工具为本地交付物。
3. 数据获取入口:**启动时弹出连接向导对话框**。
4. 上传触发:**手动批量「同步上传」按钮**(利用 V API 批量 + `editBatchId` 幂等)。
5. 工作区默认位置:`~/labeling_tool_data/session_{id}/`。
6. HTTP 库:`requests`。
7. V4 可选字段(`bboxAreaMm2`/`bboxCount`/`pxPerMm`/`defectType`):**全部填充**。

## 总体架构

仓库根目录新建 `labeling_tool/`,三层结构:

```
labeling_tool/
├── core/              # 从现有 labeling 包整体复制(笔刷/OBB/ArUco/rebuild/metrics/result/canvas/i18n/…)
├── api/               # 新增:V API 客户端
│   ├── client.py      # V1/V2/V3/V4 HTTP 封装 + 错误码处理
│   ├── downloader.py  # 并发下载 stitchedUrl/maskUrl,带进度回调
│   └── uploader.py    # V2→V3→V4 批量编排 + editBatchId 幂等
├── session/
│   ├── manifest.py    # 本地会话清单:filename↔timestamp↔元数据 持久化
│   └── workspace.py   # 本地目录布局管理
├── ui/
│   ├── connect_dialog.py   # 新增:启动连接向导
│   └── main_window.py      # 扩展现有 MainWindow,加「上传」按钮
├── config.json        # 记住 BASE / API Key(不记 sessionId)
├── app.py             # 入口:先弹连接向导 → 再进主界面
├── requirements.txt   # PyQt5, qfluentwidgets, opencv-python, numpy, scikit-image, requests, pycocotools
└── README.md          # 本地 PC 部署/运行说明
```

`core/` 使用包名 `labeling_tool.core`;现有 `from labeling.xxx` 导入机械替换为 `from labeling_tool.core.xxx`。整个文件夹拷到本地 PC 即可独立运行。

## 组件设计

### api/client.py — V API 客户端

- 统一持有 `base_url` + `X-Viewer-Api-Key`,封装 `requests.Session`,带超时与重试。
- 方法:
  - `list_photos(session_id, *, from_num=None, to_num=None, offset=0, limit=100)` → 解析 V1 响应(`total`、`photos[]`)。调用方负责按 `total` 分页(每页 ≤100)。
  - `request_presigned(session_id, files)` → V2,`files` ≤100。
  - `put_mask(presigned_url, png_bytes, content_type, cache_control)` → V3(直传 S3)。
  - `register_annotations(edit_batch_id, session_id, items)` → V4,`items` ≤100。
- 错误处理:解析公共错误体 `{error, code, details}`,抛出携带 `code` 的异常,UI 层据此给中文提示。重点码:`UNAUTHORIZED`、`JOB_NOT_READY`、`PHOTO_NOT_FOUND`、`BATCH_LIMIT_EXCEEDED`、`S3_OBJECT_NOT_FOUND`、`IDEMPOTENCY_CONFLICT`、`S3_ERROR`。

### api/downloader.py

- 输入 V1 的 `photos[]`,并发下载 `stitchedUrl`→`Origin/stitched_{ts}.jpg`、`maskUrl`→`Detected/mask_{ts}.png`。
- 进度回调(已完成/总数);单张失败重试,最终汇总失败列表。

### api/uploader.py

- 输入:本次会话**已编辑**照片列表 + manifest + 各张本地掩膜/OBB/metrics。
- 生成单个 `editBatchId`(UUID),按 100 分页:V2(取 presigned)→ V3(逐张 PUT 掩膜)→ V4(批量注册)。
- 幂等:失败整批用同一 `editBatchId` 重试(服务器返回 200,无副作用)。
- 进度回调,逐张成功/失败;成功后回写 manifest `synced` 标记。

### session/manifest.py + workspace.py

- `workspace.py`:解析/创建 `~/labeling_tool_data/session_{id}/` 下 `Origin/ Detected/ Labeling/ Result/ manifest.json` 布局。
- `manifest.json` 结构:

```json
{
  "sessionId": 43,
  "base": "https://...",
  "fetchedAt": "<由调用方填入>",
  "photos": {
    "stitched_1717572612000.jpg": {
      "timestamp": 1717572612000,
      "photoId": 101,
      "reportPhotoNum": 1,
      "pxPerCm": 45.2,
      "scaleSource": "aruco",
      "synced": false,
      "uploadedBatchId": null
    }
  }
}
```

- 文件名采用 `stitched_{ts}.jpg`,可从中反解 `timestamp`;掩膜上传映射为 `mask_{ts}.png`,S3 key = `results/{sessionId}/masks/mask_{ts}.png`。manifest 是「GUI 文件名世界 ↔ V API timestamp 世界」的桥梁,支撑断点续传与区域分担。

### ui/connect_dialog.py — 启动连接向导

- 字段:`BASE`、`X-Viewer-Api-Key`(从 `config.json` 预填)、`sessionId`、可选 `fromNum`/`toNum`。
- 「获取」流程:V1(自动分页)→ 展示照片数与 `reportPhotoNum` 范围 → 后台 `downloader` 下载(进度条)→ 写 manifest → 关闭向导进入主界面。
- 「打开已下载会话」按钮:跳过网络,直接读本地 workspace(断网续标)。

### ui/main_window.py

- 子类化/扩展现有 `MainWindow`,工作目录指向 workspace 的 `Origin/ Detected/ Labeling/ Result/`。
- 侧栏新增「上传到 EC2」按钮 → 调 `uploader`,弹进度对话框。
- 标注逻辑(笔刷/OBB/ArUco/rebuild/保存)原样复用;`pxPerCm` 优先用 V1 下发值,本地 ArUco 重算到则以本地为准(`scaleSource=aruco`)。

## 数据映射(V4)

| V4 字段 | 来源 | 备注 |
|---|---|---|
| `repairAreas[].{cx,cy,w,h,angleDeg}` | `OrientedBox` | 仅 `angle_deg`→`angleDeg` 改名 |
| `crackMetrics.lengthMm` | `CrackMetrics.length_mm` | 已有 |
| `crackMetrics.avgWidthMm` | `mean_width_mm` | 已有 |
| `crackMetrics.maxWidthMm` | `max_width_mm` | 已有 |
| `crackMetrics.minWidthMm` | **需新增** | 在 `compute_crack_metrics` 加 `min(widths_px)`(改动极小) |
| `crackMetrics.spallingMm2` | `compute_spalling_area_mm2` | 已有 |
| `crackMetrics.bboxAreaMm2` | 全部 OBB 面积之和(mm²) | 由 `area_px2` × (mm/px)² 计算 |
| `crackMetrics.bboxCount` | OBB 数量 | |
| `crackMetrics.defectType` | crack/spalling 掩膜有无推导 | 0 均裂 / 1 박리 / 2 混合 |
| `crackMetrics.pxPerMm` | `pxPerCm / 10` | |
| `pxPerCm` / `scaleSource` | `current_scale` / `current_scale_source` | 已有 |

## 调用时序

```
启动 → ConnectDialog
  └ V1 list_photos(分页) → downloader(Origin/Detected) → manifest 写入 → 进入主界面
标注(复用 core:笔刷/OBB/ArUco/rebuild/本地保存)
点击「上传到 EC2」
  └ 收集已编辑 → editBatchId=UUID → 按100分页 [ V2 presigned → V3 PUT 掩膜 → V4 register ] → manifest 标 synced
```

同图并发编辑遵循 V API「最后写入者胜」;区域分担时每作业员只取自己 `fromNum~toNum`,各用独立 `editBatchId`。

## 配置与错误处理

- `config.json` 仅存 `BASE`、`apiKey`(本地文件,README 提示勿提交版本库,纳入 `.gitignore`);`sessionId` 每次输入。
- API 错误码按文档表给中文提示;`BATCH_LIMIT_EXCEEDED` 通过自动 100 分页规避。
- 下载/上传带超时与重试;网络中断不影响已下载数据的本地标注。

## 测试策略

- 单元测试(`responses`/`requests-mock`):`api/client.py`(分页、错误码解析)、`uploader.py`(100 分页、幂等重试)、`manifest.py`(timestamp↔filename 映射、synced 状态)。
- TDD:`compute_crack_metrics` 新增 `minWidthMm`,用合成掩膜验证 `min ≤ mean ≤ max`;`bboxAreaMm2`/`defectType` 推导用合成数据验证。
- GUI 层手动验证;端到端连真实服务器由用户验收(本地交付物)。

## 非目标(YAGNI)

- 不实现 Web 仪表盘(W1)相关功能。
- 不在本工具内重算服务器侧逻辑(服务器信任客户端计测值)。
- 不做多人实时协同冲突解决(依赖 V API last-write-wins + 区域分担)。
