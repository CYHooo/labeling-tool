# 精简分发与精确增量更新 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让只改 Python 代码的更新从 75 MB 降到个位数 MB，并去掉 runtime id 的误触发。

**Architecture:** runtime id 改为直接测量运行时层（每个文件的相对路径 + 字节数），不再推断哪些配置影响运行时；`noarchive=True` 让第三方字节码从 exe 里散落到各自包目录，从而归入运行时层；ONNX 模型移入运行时层；排除两个确定不用的 CUDA 库。

**Tech Stack:** Python 3.12、PyInstaller 6.22.3（onedir）、Inno Setup 6、GitHub Actions（windows-latest）

**Spec:** `docs/superpowers/specs/2026-09-30-lean-incremental-updates-design.md`

## Global Constraints

- 只发布 `full` 一个变体；软件名 `LM_LabelingTool`。
- 代码注释用英文；日志与异常文本保持英文。
- 用户可见文案先改 `docs/i18n-glossary.md` 再改 `labeling_tool/core/i18n/strings_{ko,zh,en}.py`，三份键必须一致。
- 测试命令固定为 `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`，基线 449 通过，全程保持绿。
- offscreen Qt 下模态 `QMessageBox` 会挂起测试进程，新增失败路径一律走内嵌显示。
- Windows 构建里每一处等待都必须经 `packaging/ci/bounded.ps1`，不得出现裸 `Start-Process -Wait`。
- `AppId` 保持 `{{9E1E0C6B-6E0F-4E8E-9E2F-0F7B5C1A0F02}`；标签必须是纯数字格式（`v1.4.0`）。
- 本次改动必然改变 runtime id，发布后需要一次全量重装；这是算法切换的一次性成本。
- 提交信息用 conventional commits，结尾附 `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` 与 `Claude-Session: https://claude.ai/code/session_01Xc4ugrgTVC5n4YsSJVW2qq` 两行真实 trailer。

## Review Focus

- **同名同大小但内容不同的运行时文件不会改变 runtime id** — 这是清单法用精度换稳定性的有意取舍（内容哈希已被证明不可用）。必须有一条显式测试把它钉成设计，否则后人会当成缺陷去"修"，并因此退回不可重现的内容哈希。测试归 Task 1。
- **`noarchive` 后 sam2 的 hydra 配置解析** — hydra 在运行时按路径查找 yaml；字节码从 PYZ 散落到文件系统后，配置文件的定位方式若受影响，few-shot 工具将无法启动。CI 的 `--selftest=full` 会组合 hydra 配置，是唯一能发现它的地方；Task 3 本地无法验证。测试归 Task 4。
- **ONNX 移入运行时层后，应用包不再携带模型** — 全新机器若只拿到应用包，将缺少 MobileSAM 模型。安装器的 runtime 守卫必须先于此拒绝安装；这条路径已在 v1.3.0 的 CI 中验证过，本期不得回退。测试归 Task 4。
- **排除 `nvidia.nccl` / `nvidia.cuda_cupti` 后 `import torch` 仍须成功** — torch 的 Windows 构建可能在导入期链接这些 DLL。CI 的自检覆盖导入，但覆盖不了真实推理。测试归 Task 4。
- **上万个 `.pyc` 对 Inno 编译与安装耗时的影响** — `noarchive` 把单个 PYZ 拆成数万个小文件，可能显著拖慢打包或安装。若构建时长翻倍，需要在合并前知道并决定是否退回 A 档。基线：健康构建约 22 分钟，其中 Inno 压缩约 12 分钟。测试归 Task 4 Step 3。

---

## File Structure

| 文件 | 职责 | 动作 |
|---|---|---|
| `packaging/layers.py` | 分层规则 + runtime id（改为清单法，新增排除规则） | 修改 |
| `packaging/labeling_tool.spec` | `noarchive=True`，排除两个 CUDA 库 | 修改 |
| `.github/workflows/build-windows.yml` | runtime-id 调用简化，新增稳定性与体积记录 | 修改 |
| `labeling_tool/tests/test_layers.py` | 清单法与排除规则的测试 | 修改 |
| `docs/superpowers/specs/2026-09-30-lean-incremental-updates-design.md` | 回写实测数值 | 修改 |

**本地可测范围**：Task 1、2 是纯 Python，本地全量覆盖。Task 3 只能做静态校验，Task 4 必须靠 CI。Task 3、4 的提交不得宣称"已验证"，只能说"已实现，待 CI 验证"。

---

### Task 1: runtime id 改为测量运行时层

**Files:**
- Modify: `packaging/layers.py`
- Test: `labeling_tool/tests/test_layers.py`

**Interfaces:**
- Consumes: 既有的 `is_app_layer(relpath)`、`iter_runtime_files(dist_dir)`
- Produces: `compute_runtime_id(dist_dir: Path) -> str` — 签名由 `(repo_root, freeze_text)` 改为单参数；`RUNTIME_SPEC_FILES` 常量删除

- [ ] **Step 1: 改写测试**

`labeling_tool/tests/test_layers.py` 中，从 `SPEC = b'coll = COLLECT(...)'` 起到
`# ---- build-info.json` 注释之前的整段（即 `_make_repo`、`FREEZE` 与所有 runtime id 用例）
替换为：

```python
def test_runtime_id_is_stable_for_the_same_tree(tmp_path):
    """Two PyInstaller runs of the same commit write different BYTES --
    timestamps go into the files -- so contents cannot be hashed (proved on
    CI runs 36421966949 / 36424404832). Paths and sizes are stable, and they
    are what this measures."""
    files = {"_internal/torch/a.dll": b"x" * 100, "LM_LabelingTool.exe": b"app"}
    one = _make_dist(tmp_path / "one", files)
    two = _make_dist(tmp_path / "two", files)
    assert layers.compute_runtime_id(one) == layers.compute_runtime_id(two)


def test_runtime_id_ignores_app_layer_changes(tmp_path):
    """The whole point: changing our own code must not force a reinstall."""
    base = {"_internal/torch/a.dll": b"x" * 100}
    one = _make_dist(tmp_path / "one", {**base, "_internal/labeling_tool/app.pyc": b"v1"})
    two = _make_dist(tmp_path / "two", {**base, "_internal/labeling_tool/app.pyc": b"v2-longer"})
    assert layers.compute_runtime_id(one) == layers.compute_runtime_id(two)


def test_runtime_id_changes_when_a_runtime_file_changes_size(tmp_path):
    app = {"LM_LabelingTool.exe": b"app"}
    one = _make_dist(tmp_path / "one", {**app, "_internal/torch/a.dll": b"x" * 100})
    two = _make_dist(tmp_path / "two", {**app, "_internal/torch/a.dll": b"x" * 101})
    assert layers.compute_runtime_id(one) != layers.compute_runtime_id(two)


def test_runtime_id_changes_when_a_runtime_file_is_added(tmp_path):
    app = {"LM_LabelingTool.exe": b"app", "_internal/torch/a.dll": b"x" * 100}
    one = _make_dist(tmp_path / "one", app)
    two = _make_dist(tmp_path / "two", {**app, "_internal/nvidia/b.dll": b"y" * 50})
    assert layers.compute_runtime_id(one) != layers.compute_runtime_id(two)


def test_runtime_id_changes_when_a_runtime_file_is_removed(tmp_path):
    app = {"LM_LabelingTool.exe": b"app", "_internal/torch/a.dll": b"x" * 100}
    one = _make_dist(tmp_path / "one", {**app, "_internal/nvidia/nccl/n.dll": b"z" * 70})
    two = _make_dist(tmp_path / "two", app)
    assert layers.compute_runtime_id(one) != layers.compute_runtime_id(two)


def test_runtime_id_changes_when_a_runtime_file_is_renamed(tmp_path):
    """Path is hashed too: a rename that keeps every byte still moves it."""
    app = {"LM_LabelingTool.exe": b"app"}
    one = _make_dist(tmp_path / "one", {**app, "_internal/torch/a.dll": b"x" * 100})
    two = _make_dist(tmp_path / "two", {**app, "_internal/torch/b.dll": b"x" * 100})
    assert layers.compute_runtime_id(one) != layers.compute_runtime_id(two)


def test_runtime_id_does_not_see_content_changes_at_equal_size(tmp_path):
    """A DELIBERATE trade-off, not a defect: hashing contents was tried and
    abandoned because PyInstaller's output is not reproducible. A dependency
    that changes content without changing any file's size or path -- a
    republished wheel under the same version -- will not move the id.
    Do not "fix" this by hashing contents; that breaks the mechanism."""
    app = {"LM_LabelingTool.exe": b"app"}
    one = _make_dist(tmp_path / "one", {**app, "_internal/torch/a.dll": b"aaaa"})
    two = _make_dist(tmp_path / "two", {**app, "_internal/torch/a.dll": b"bbbb"})
    assert layers.compute_runtime_id(one) == layers.compute_runtime_id(two)


def test_runtime_id_rejects_a_missing_dist(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        layers.compute_runtime_id(tmp_path / "nope")


def test_runtime_id_rejects_an_empty_runtime_layer(tmp_path):
    """No runtime files means the caller pointed at the wrong directory;
    hashing nothing would produce a confident-looking wrong id."""
    import pytest
    d = _make_dist(tmp_path / "d", {"LM_LabelingTool.exe": b"app"})
    with pytest.raises(ValueError):
        layers.compute_runtime_id(d)


def test_runtime_id_format(tmp_path):
    import re
    d = _make_dist(tmp_path / "d", {"_internal/torch/a.dll": b"x" * 10})
    assert re.fullmatch(r"r[0-9a-f]{8}", layers.compute_runtime_id(d))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_layers.py -q -p no:cacheprovider`
Expected: FAIL，报 `TypeError: compute_runtime_id() missing 1 required positional argument: 'freeze_text'`

- [ ] **Step 3: 改写 compute_runtime_id**

`packaging/layers.py` 中，删除 `RUNTIME_SPEC_FILES` 常量，并把 `compute_runtime_id` 整个替换为：

```python
def compute_runtime_id(dist_dir: Path) -> str:
    """A short identity for the runtime layer, measured from the build.

    Hashes each runtime file's relative path and SIZE -- never its contents.
    Two PyInstaller runs of the same commit emit different bytes (timestamps
    go into the files; CI runs 36421966949 and 36424404832 produced
    ra9adeaed and r138b837f), so hashing contents would move the id on every
    release and the app package would never match anything. Paths and sizes
    survive that.

    Measuring the build directly also means nobody has to judge which config
    affects the runtime layer: adding a dependency, upgrading torch or
    excluding a CUDA library all change the listing, while editing an icon
    path in the spec does not.

    The trade-off is on record in
    test_runtime_id_does_not_see_content_changes_at_equal_size: a dependency
    whose contents change without any file changing name or size will not
    move the id.

    Raises FileNotFoundError if dist_dir does not exist, and ValueError if it
    holds no runtime-layer files at all -- both mean the caller pointed at
    the wrong directory, and a hash of nothing would look authoritative.
    """
    root = Path(dist_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"no such build directory: {root}")
    digest = hashlib.sha256()
    count = 0
    for rel, path in iter_runtime_files(root):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(path.stat().st_size).encode("ascii"))
        digest.update(b"\0")
        count += 1
    if count == 0:
        raise ValueError(f"no runtime-layer files under {root}")
    return "r" + digest.hexdigest()[:8]
```

- [ ] **Step 4: 改 CLI**

同文件的 `main()` 中，把 runtime-id 分支改为单参数：

```python
    if len(args) == 2 and args[0] == "runtime-id":
        print(compute_runtime_id(Path(args[1])))
        return 0
```

并把用法提示改回 `"usage: layers.py runtime-id <dist>\n"`。

- [ ] **Step 5: 修 CLI 测试**

`test_layers.py` 中的 `test_cli_runtime_id` 与 `test_cli_runtime_id_on_this_repo` 替换为：

```python
def test_cli_runtime_id(tmp_path, capsys):
    d = _make_dist(tmp_path / "d", {"_internal/torch/a.dll": b"x" * 10})
    assert layers.main(["runtime-id", str(d)]) == 0
    assert capsys.readouterr().out.strip() == layers.compute_runtime_id(d)


def test_cli_runtime_id_reports_a_bad_path(tmp_path, capsys):
    import pytest
    with pytest.raises(FileNotFoundError):
        layers.main(["runtime-id", str(tmp_path / "missing")])
```

- [ ] **Step 6: 运行全量测试**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`
Expected: PASS，451 passed（基线 449，删除 8 条 freeze 相关用例，新增 10 条清单用例）

- [ ] **Step 7: 提交**

```bash
git add packaging/layers.py labeling_tool/tests/test_layers.py
git commit -m "$(cat <<'EOF'
feat(update): identify the runtime layer by measuring it

Hashing pip freeze plus the spec file asked every user to re-download
1536 MB because v1.3.1 touched an icon path in datas. The id now hashes
each runtime file's path and size, so adding a dependency or upgrading
torch moves it while editing the spec's icon path does not.

Sizes rather than contents: PyInstaller's output is not reproducible,
which is why hashing contents was abandoned in the first place.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xc4ugrgTVC5n4YsSJVW2qq
EOF
)"
```

---

### Task 2: ONNX 模型移入运行时层

**Files:**
- Modify: `packaging/layers.py`
- Test: `labeling_tool/tests/test_layers.py`

**Interfaces:**
- Consumes: Task 1 的 `compute_runtime_id(dist_dir)`
- Produces: `APP_LAYER_EXCLUSIONS` — `tuple[str, ...]`，在前缀命中后再排除的路径前缀

- [ ] **Step 1: 写失败的测试**

在 `test_layers.py` 的分层用例之后追加：

```python
def test_onnx_models_are_runtime_layer(tmp_path):
    """42.4 MB of fixed pretrained weights. They sit under
    _internal/labeling_tool/ so the prefix catches them, but they never
    change -- shipping them in every update doubled its size."""
    assert not layers.is_app_layer("_internal/labeling_tool/models/sam/mobile_sam_encoder.onnx")
    assert not layers.is_app_layer("_internal/labeling_tool/models/sam/mobile_sam_decoder.onnx")


def test_our_code_under_the_same_package_is_still_app_layer():
    """The exclusion is narrow: only models/, not the package around it."""
    assert layers.is_app_layer("_internal/labeling_tool/app.pyc")
    assert layers.is_app_layer("_internal/labeling_tool/core/i18n/__init__.pyc")
    assert layers.is_app_layer("_internal/labeling_tool/ui/login_dialog.pyc")


def test_exclusion_respects_directory_boundaries():
    """A sibling named models_helper is ours, not an excluded model."""
    assert layers.is_app_layer("_internal/labeling_tool/models_helper.pyc")


def test_changing_a_model_moves_the_runtime_id(tmp_path):
    """Replacing MobileSAM is a full reinstall, consistent with the rule
    that swapping a big file means everyone re-downloads."""
    base = {"LM_LabelingTool.exe": b"app", "_internal/torch/a.dll": b"x" * 10}
    one = _make_dist(tmp_path / "one",
                     {**base, "_internal/labeling_tool/models/sam/m.onnx": b"m" * 100})
    two = _make_dist(tmp_path / "two",
                     {**base, "_internal/labeling_tool/models/sam/m.onnx": b"m" * 200})
    assert layers.compute_runtime_id(one) != layers.compute_runtime_id(two)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_layers.py -q -p no:cacheprovider -k onnx or exclusion or model`
Expected: FAIL，`test_onnx_models_are_runtime_layer` 断言失败（当前 ONNX 被判为应用层）

- [ ] **Step 3: 实现排除规则**

`packaging/layers.py` 中，在 `APP_LAYER_PREFIXES` 之后加入：

```python
# Carved back out of the prefixes above. The MobileSAM ONNX models live
# inside labeling_tool/ but are fixed pretrained weights -- 42.4 MB that
# never changes, which was over half of every app-layer update. Swapping a
# model is a full reinstall, same as swapping torch.
APP_LAYER_EXCLUSIONS = (
    "_internal/labeling_tool/models/",
)
```

并把 `is_app_layer` 改为：

```python
def is_app_layer(relpath: str) -> bool:
    """True when this file ships in the small app-only package."""
    rel = relpath.replace("\\", "/")
    if any(rel.startswith(x) for x in APP_LAYER_EXCLUSIONS):
        return False
    for prefix in APP_LAYER_PREFIXES:
        if prefix.endswith("/"):
            if rel.startswith(prefix):
                return True
        elif rel == prefix:
            return True
    return False
```

- [ ] **Step 4: 运行全量测试**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`
Expected: PASS，455 passed（451 + 本任务 4）

- [ ] **Step 5: 提交**

```bash
git add packaging/layers.py labeling_tool/tests/test_layers.py
git commit -m "$(cat <<'EOF'
feat(update): move the ONNX models into the runtime layer

42.4 MB of fixed pretrained weights was over half of every 75 MB app
update. They never change; swapping a model is a full reinstall now,
the same rule as swapping torch.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xc4ugrgTVC5n4YsSJVW2qq
EOF
)"
```

---

### Task 3: noarchive 与 CUDA 裁剪

**Files:**
- Modify: `packaging/labeling_tool.spec`

**Interfaces:**
- Consumes: Task 2 的分层规则（`.pyc` 按包落盘后自然归层）
- Produces: 构建产物形态改变——纯 Python 模块以 `.pyc` 散落于 `_internal/<pkg>/`，exe 仅余引导程序

**本任务本地无法验证**，PyInstaller 的完整构建需要 Windows 与 sam2。静态校验之外，真正的验证在 Task 4 的 CI。提交信息不得宣称已验证。

- [ ] **Step 1: 开启 noarchive 并排除两个 CUDA 库**

`packaging/labeling_tool.spec` 中，把 `excludes` 一行改为：

```python
# nccl is multi-GPU collective communication and cupti is the CUDA
# profiler: neither is reachable from single-card inference, and together
# they are 283 MB unpacked. Everything else under nvidia/ stays -- cudnn and
# cublas are required, and the rest cannot be verified without a GPU, which
# CI does not have.
excludes = ["sam3", "triton", "timm", "nvidia.nccl", "nvidia.cuda_cupti"]
```

把 `Analysis(...)` 的 `noarchive=False` 改为：

```python
    # noarchive=True writes pure-Python modules as .pyc files under
    # _internal/<package>/ instead of packing them into the exe's PYZ. That
    # is what puts torch/PyQt5/numpy bytecode in the RUNTIME layer: with the
    # PYZ, all of it rode inside the exe and every code change shipped ~38 MB
    # of unchanged third-party bytecode.
    noarchive=True,
```

- [ ] **Step 2: 静态校验 spec**

```bash
.venv/bin/python -c "
import ast, pathlib
src = pathlib.Path('packaging/labeling_tool.spec').read_text()
ast.parse(src)
assert 'noarchive=True' in src
assert 'nvidia.nccl' in src and 'nvidia.cuda_cupti' in src
assert 'LM_LabelingTool' in src
print('spec ok')
"
```
Expected: `spec ok`

- [ ] **Step 3: 运行全量测试**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider`
Expected: PASS，455 passed（spec 不被测试导入，数量不变）

- [ ] **Step 4: 提交**

```bash
git add packaging/labeling_tool.spec
git commit -m "$(cat <<'EOF'
feat(packaging): scatter bytecode into the runtime layer, drop nccl/cupti

noarchive writes pure-Python modules as .pyc under _internal/<package>/
instead of packing them into the exe. torch, PyQt5 and numpy bytecode
therefore lands in the runtime layer; before this it rode inside the exe
and every code change shipped ~38 MB of unchanged third-party code.

nccl is multi-GPU collective communication and cupti is the CUDA
profiler, 283 MB unpacked between them and neither reachable from
single-card inference.

Not verified locally: the build needs Windows and sam2. CI is the gate.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xc4ugrgTVC5n4YsSJVW2qq
EOF
)"
```

---

### Task 4: CI 接入、稳定性验证与实测回写

**Files:**
- Modify: `.github/workflows/build-windows.yml`
- Modify: `docs/superpowers/specs/2026-09-30-lean-incremental-updates-design.md`

**Interfaces:**
- Consumes: Task 1 的 `layers.py runtime-id <dist>`、Task 3 的构建产物形态
- Produces: release 资产 `LM_LabelingTool-Setup-v<版本>.exe`、`LM_LabelingTool-App-v<版本>-r<id>.exe`、`SHA256SUMS.txt`

- [ ] **Step 1: 简化 runtime-id 调用**

`.github/workflows/build-windows.yml` 中「Compute the runtime id and write build info」步骤的前几行替换为：

```yaml
          # The runtime id measures the runtime layer itself -- each file's
          # path and size. Contents are not hashed: PyInstaller's output is
          # not reproducible (runs 36421966949 / 36424404832 differed), while
          # paths and sizes are stable. Computed BEFORE build-info.json is
          # written, though that file is app-layer either way.
          $rt = python packaging/layers.py runtime-id dist/LM_LabelingTool
          if (-not ($rt -match '^r[0-9a-f]{8}$')) { throw "bad runtime id: $rt" }
          # Cheap determinism check: the same tree must hash the same twice.
          $rt2 = python packaging/layers.py runtime-id dist/LM_LabelingTool
          if ($rt -ne $rt2) { throw "runtime id is not deterministic: $rt vs $rt2" }
```

并删除该步骤中 `pip freeze | Out-File ...` 那一行。

- [ ] **Step 2: 记录分层实测数值**

「Stage the app layer」步骤之后加入：

```yaml
      - name: Record the layer split
        run: |
          $app = (Get-ChildItem dist/app-layer -Recurse -File | Measure-Object -Property Length -Sum)
          Write-Host ("app layer: {0:N1} MB in {1} files" -f ($app.Sum/1MB), $app.Count)
          # The app package is what every routine update downloads. If it
          # climbs back into the tens of MB something leaked out of the
          # runtime layer.
          if ($app.Sum -gt 20MB) { throw ("app layer unexpectedly large: {0:N1} MB" -f ($app.Sum/1MB)) }
```

`dist/app-layer` 只含应用层文件（预期个位数 MB、数百个文件），递归扫描它是安全的——被禁止的是扫描 4 GB 的安装目录。

- [ ] **Step 3: 推分支触发 CI 并读结果**

```bash
git add .github/workflows/build-windows.yml
git commit -m "$(cat <<'EOF'
ci: measure the runtime layer, and guard the app layer's size

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xc4ugrgTVC5n4YsSJVW2qq
EOF
)"
git push -u origin feat/lean-incremental-updates
gh workflow run build-windows.yml --ref feat/lean-incremental-updates
```

读构建日志中的 `app layer: N MB in M files` 与 `runtime id: r…`，并记录整轮耗时与
「Build installer」步骤的耗时。

Expected:
- 构建成功；应用层为个位数 MB
- `--selftest=full` 两次均 PASS —— 这同时证明 `noarchive` 没有破坏 sam2 的 hydra 配置解析，
  也证明排除 nccl / cupti 后 `import torch` 仍然成功
- 不匹配的应用包被拒绝（`exit code 1, install untouched`）
- 整轮耗时与基线 22 分钟相当（Inno 压缩基线约 12 分钟）。若压缩耗时翻倍，说明上万个小文件
  显著拖慢打包，在 ledger 记录实测值并告知用户，由用户决定是否退回 A 档（放弃 `noarchive`，
  只保留 ONNX 移层）

若 `--selftest=full` 因 hydra 或 torch 导入失败，按 spec 第 8 节处理：先单独回退 `nvidia.*` 的排除再跑一次，以区分是 `noarchive` 还是 CUDA 裁剪造成的。

- [ ] **Step 4: 验证跨构建稳定性**

不改任何代码，再次触发构建：

```bash
gh workflow run build-windows.yml --ref feat/lean-incremental-updates
```

比对两次日志中的 runtime id。
Expected: 两次一致。

若不一致，说明运行时层的路径或大小仍受构建过程影响，按 spec 第 8 节回退：`compute_runtime_id`
改回哈希 `pip freeze` 与 `packaging/labeling_tool.spec`（保留 `noarchive` 与 ONNX 移层的收益），
并在 ledger 记录两次实测值。

- [ ] **Step 5: 回写实测数值**

把 Step 3 读到的应用层体积与文件数写入
`docs/superpowers/specs/2026-09-30-lean-incremental-updates-design.md` 第 5.3 节，替换
「具体数值在实现时由 CI 实测并写回本文档」。同时在第 6 节记录安装包实测体积。

```bash
git add docs/superpowers/specs/2026-09-30-lean-incremental-updates-design.md
git commit -m "$(cat <<'EOF'
docs(design): record the measured app-layer size

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xc4ugrgTVC5n4YsSJVW2qq
EOF
)"
```

---

## 完成标准

- 全量测试 455 通过
- CI 构建成功，三个 release 资产齐备
- 应用层实测为个位数 MB，且 CI 的上限护栏（20 MB）未触发
- 装完整包与装应用包之后，`--selftest=full` 均通过（证明 `noarchive` 未破坏 hydra 与 torch 导入）
- 不匹配的应用包仍被安装器拒绝
- runtime id 在两次独立构建间一致（或已按回退方案处理并记录）
- 应用层实测数值已回写设计文档

## 发布与人工验证

本期完成后发布 v1.4.0。**需要手动安装一次完整包**：本次改动必然改变 runtime id，客户端会走完整包路径。

安装后请确认：

- 程序正常启动，登录界面版本号为 `1.4.0`
- **在 GPU 机器上完整跑一遍 few-shot 标注流程** —— 这是 CUDA 裁剪唯一的真实验证，CI 没有 GPU
- 标注、保存、上传流程无异常

下一个只改 Python 代码的版本才是增量更新的真正验收：届时应收到**个位数 MB** 的更新提示。
