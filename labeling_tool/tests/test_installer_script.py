"""Static checks on packaging/installer.iss.

Inno Setup only runs on Windows, so these are the only automated guard we
have over the installer script. Both checks come from real failures:
CI run 36518723697 hung for 96 minutes because a [Code] MsgBox blocked a
silent install, and the registry key it read was misspelled so the guard
never found the install it was meant to protect.
"""

import re
import sys
from pathlib import Path

import pytest

ISS = Path(__file__).resolve().parents[2] / "packaging" / "installer.iss"


@pytest.fixture(scope="module")
def iss() -> str:
    return ISS.read_text(encoding="utf-8")


def _section(text: str, name: str) -> str:
    """The body of a section, located by a line that IS the header -- the
    file's own comments mention [Files] and [Code] in prose."""
    lines = text.splitlines(keepends=True)
    starts = [i for i, l in enumerate(lines) if l.strip() == name]
    assert starts, f"no {name} section header"
    i = starts[0] + 1
    out = []
    while i < len(lines) and not (lines[i].startswith("[") and lines[i].strip().endswith("]")):
        out.append(lines[i])
        i += 1
    return "".join(out)


def _code_section(text: str) -> str:
    return _section(text, "[Code]")


def test_code_section_never_calls_blocking_msgbox(iss):
    """/SUPPRESSMSGBOXES does NOT suppress a MsgBox called from [Code]. A
    silent install -- which is what the in-app updater runs -- would wait
    forever for a click nobody makes. SuppressibleMsgBox returns the
    default instead."""
    calls = re.findall(r"(?<![A-Za-z])MsgBox\s*\(", _code_section(iss))
    assert not calls, (
        f"{len(calls)} blocking MsgBox call(s) in [Code]; use "
        "SuppressibleMsgBox so /SUPPRESSMSGBOXES cannot hang the install")


def test_production_appid_is_unchanged(iss):
    """Every existing install upgrades in place through this AppId."""
    declared = re.findall(r"^AppId=\{\{([0-9A-Fa-f-]+)\}", iss, re.M)
    assert len(declared) == 2, f"expected production + test AppId, got {declared}"
    assert declared[0] == "9E1E0C6B-6E0F-4E8E-9E2F-0F7B5C1A0F02", (
        "the production AppId changed: every existing install would stop "
        "upgrading in place")


def test_test_install_can_never_touch_the_real_install(iss):
    """A local smoke test installs and UNINSTALLS. Under the production
    AppId or Start menu name that takes the workstation's real copy with it."""
    setup = _section(iss, "[Setup]")
    prod = setup[setup.index("#ifndef MyTestInstall"):setup.index("#else")]
    test = setup[setup.index("#else"):setup.index("#endif")]
    assert "9E1E0C6B" in prod and "9E1E0C6B" not in test
    name = re.search(r'#define MyAppName "([^"]+)"', test).group(1)
    assert name != "LM_LabelingTool"
    assert "DefaultGroupName={#MyAppName}" in setup


def test_the_installer_has_no_app_layer_mode(iss):
    assert "MyLayer" not in iss and "MyRuntime" not in iss
    assert "OutputBaseFilename=LM_LabelingTool-Setup-v{#MyVersion}" in iss


def test_install_replaces_internal_wholesale(iss):
    assert 'Name: "{app}\\_internal"' in _section(iss, "[InstallDelete]")


def test_uninstall_removes_update_leftovers(iss):
    for name in (".update-backup", ".update-staging", ".update-journal"):
        assert f'{{app}}\\{name}' in iss
        assert f'{{app}}\\{name}' in _section(iss, "[UninstallDelete]")


def test_uninstall_removes_files_a_zip_update_added(iss):
    """Inno only uninstalls the files it installed; a zip update adds new
    modules under _internal\\, which holds no user data (see [InstallDelete])."""
    assert 'Type: filesandordirs; Name: "{app}\\_internal"' in _section(iss, "[UninstallDelete]")


# ------------------------------------------------------------- CI workflow
# Every wait in the Windows build must be bounded. Two runs were lost to
# unbounded waits: one hung 96 minutes on a modal dialog, one left a tag
# build with nothing after 47 minutes. Both surfaced only as "the hosted
# runner lost communication with the server".

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "release.yml"


@pytest.fixture(scope="module")
def workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_no_unbounded_process_wait_in_the_workflow(workflow):
    """`Start-Process -Wait` has no timeout: a hung child holds the job
    until GitHub kills it, and the log is usually lost with it."""
    assert "-Wait -PassThru" not in workflow
    assert re.search(r"Start-Process[^\n]*\s-Wait(\s|$)", workflow) is None


LOCAL_BUILD = WORKFLOW.parent.parent.parent / "packaging" / "ci" / "local-build.ps1"


@pytest.fixture(scope="module", params=["workflow", "local-build"])
def powershell_source(request) -> str:
    """Both places that drive PowerShell against ISCC, pip and the exe."""
    path = WORKFLOW if request.param == "workflow" else LOCAL_BUILD
    return path.read_text(encoding="utf-8")


def test_waits_go_through_the_shared_helper(workflow):
    helper = WORKFLOW.parent.parent.parent / "packaging" / "ci" / "bounded.ps1"
    assert helper.is_file(), "packaging/ci/bounded.ps1 is missing"
    assert ". packaging/ci/bounded.ps1" in workflow
    assert "bounded.ps1" in LOCAL_BUILD.read_text(encoding="utf-8")


def test_ci_only_releases(workflow):
    """Verification runs locally (packaging/ci/local-build.ps1); a CI round
    is too slow to iterate on. CI runs for a tag, or by hand as a dry run."""
    on = workflow[workflow.index("\non:"):workflow.index("\npermissions:")]
    assert "pull_request" not in on
    assert "tags:" in on
    assert "pytest" not in workflow


def test_ci_builds_in_a_clean_pinned_environment(workflow):
    """The runner's own Python carries preinstalled packages that follow the
    runner image; bundled, they move the runtime id between identical
    builds. CI builds in a fresh venv, with everything pinned by the lock."""
    assert "python -m venv" in workflow
    assert "packaging/build-lock.txt" in workflow
    lock = (WORKFLOW.parent.parent.parent / "packaging" / "build-lock.txt").read_text(encoding="utf-8")
    pins = [l for l in lock.splitlines() if l and not l.startswith("#")]
    assert pins and all("==" in l for l in pins), "every lock line must pin an exact version"
    for must in ("torch==", "numpy==", "filelock==", "PyQt5=="):
        assert any(l.startswith(must) for l in pins), f"{must} is not pinned"


def test_a_reused_full_installer_is_verified_before_it_is_republished(workflow):
    """A code-only release ships the previous full installer again under a
    fresh checksum line; it has to match the checksum it was first published
    with, or a corrupted download would be blessed."""
    step = workflow[workflow.index("Reuse the previous full installer"):workflow.index("- name: Build the installer")]
    assert "reuse_full.py plan" in step
    assert "reuse_full.py verify" in step
    assert step.index("reuse_full.py verify") < step.index("LT_REUSE_FULL=")
    build = workflow[workflow.index("- name: Build the installer"):workflow.index("- name: Assert the asset names")]
    assert 'Copy-Item $env:LT_REUSE_FULL "out\\LM_LabelingTool-Setup-v$ver.exe"' in build


def test_no_string_interpolation_runs_into_a_colon(powershell_source):
    """"$prevTag: x" parses as a scope-qualified variable, like $env:X, and
    fails. Use ${name}: instead. Only $env: is a real scope here."""
    for line in powershell_source.splitlines():
        if line.strip().startswith("#"):
            continue
        for m in re.finditer(r"\$([A-Za-z_]\w*):", line):
            assert m.group(1).lower() in ("env", "script", "global", "using"), (
                f"${m.group(1)}: reads as a scope-qualified name: {line.strip()}")


def test_ci_resolves_git_symlinks_when_installing_sam2(workflow):
    """sam2's repo holds symlinked yaml files. A git with core.symlinks=false
    writes placeholders instead, and local and CI runtime ids part ways
    (run 36682820480: r1970c21b locally vs r88c8d3f0)."""
    assert "GIT_CONFIG_KEY_0: core.symlinks" in workflow
    assert 'GIT_CONFIG_VALUE_0: "true"' in workflow


def test_helper_caches_the_handle_before_waiting():
    """Without touching .Handle first, PowerShell leaves ExitCode null and
    a failed process reads as success."""
    text = (WORKFLOW.parent.parent.parent / "packaging" / "ci" / "bounded.ps1").read_text(encoding="utf-8")
    handle = text.index("$proc.Handle")
    wait = text.index("WaitForExit")
    assert handle < wait, "$proc.Handle must be read before WaitForExit"


def test_release_builds_keep_maximum_compression(iss):
    """Fast compression is a CI-time shortcut: it cuts ~10 minutes off a
    verification run. What users download must still be squeezed as hard as
    possible, so the fast path has to be opt-in via MyFast and the default
    must remain lzma2/max."""
    block = iss[iss.index("#ifdef MyFast"):iss.index("[Languages]")]
    fast, full = block.index("lzma2/fast"), block.index("lzma2/max")
    assert block.index("#else") < full, "lzma2/max must be the #else default"
    assert fast < block.index("#else"), "lzma2/fast must sit under #ifdef MyFast"


def test_release_compression_is_multithreaded(iss):
    """Single-threaded lzma2/max was ~11 of ~18 minutes of a release; four
    block threads cut it to about a third for 1% more size."""
    block = iss[iss.index("#ifdef MyFast"):iss.index("[Languages]")]
    release = block[block.index("#else"):block.index("#endif")]
    assert "LZMANumBlockThreads=4" in release


def test_the_size_ceiling_only_binds_on_published_builds(workflow):
    """A fast-compressed verification build is legitimately larger than a
    release one; the 2 GiB release ceiling must not fail it."""
    assert "$env:LT_RELEASE_COMPRESSION -eq 'true' -and $full.Length -ge 1.9GB" in workflow


def test_a_manual_run_can_rehearse_release_compression(workflow):
    """Dry runs compress fast and skip the size ceilings, so v2.0.0's real
    runtime deb size was first measured by the tag itself (CI run
    36965987450). A manual run must be able to opt into the release
    compression -- and with it the ceilings -- on both platforms."""
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load(workflow)
    on = data.get("on", data.get(True))
    inp = on["workflow_dispatch"]["inputs"]["release_compression"]
    assert inp["type"] == "boolean" and inp["default"] is False
    assert "inputs.release_compression" in data["env"]["LT_RELEASE_COMPRESSION"]
    assert "github.ref_type == 'tag'" in data["env"]["LT_RELEASE_COMPRESSION"]
    # every compression switch and size ceiling keys off that one variable
    assert "GITHUB_REF_TYPE -ne 'tag'" not in workflow
    assert '"$GITHUB_REF_TYPE" != "tag"' not in workflow
    assert '[ "$GITHUB_REF_TYPE" = "tag" ] && [ "$size"' not in workflow
    assert '[ "$LT_RELEASE_COMPRESSION" = "true" ] && [ "$size" -ge 2040109465 ]' in workflow


def test_every_iscc_invocation_honours_the_compression_mode(workflow):
    """CI compiles one package, the Setup exe, from a common argument list
    that carries /DMyFast=1 on a dry run."""
    assert workflow.count("/DMyFast=1") == 1, "only via the common list"
    assert workflow.count("& $iscc @") == 1, "the invocation splats a full array"


def test_local_installers_never_carry_the_production_appid():
    """The local smoke test installs and uninstalls on a workstation that may
    have the app installed for real."""
    text = LOCAL_BUILD.read_text(encoding="utf-8")
    assert '"/DMyTestInstall=1"' in text
    assert text.count("& $iscc @") == 1
    assert "9E1E0C6B" not in text, "the local script must not name the production AppId"


def test_scripts_never_assign_powershell_automatic_variables(powershell_source):
    """$args is the function-arguments automatic variable; assigning to it
    is undefined behaviour and has already dropped arguments here once --
    including /VERYSILENT, which turned a silent install into a wizard that
    hung for 96 minutes."""
    reserved = ("args", "input", "error", "host", "home", "pwd", "matches")
    for name in reserved:
        assert re.search(rf"^\s*\${name}\s*=", powershell_source, re.M | re.I) is None, (
            f"${name} is a PowerShell automatic variable; pick another name")


def test_splats_are_always_the_whole_argument_list(powershell_source):
    """`& $iscc /A @extra script.iss` does NOT expand @extra -- splatting
    only works as the entire rest of the command. The literal "@extra" then
    reaches ISCC as a second script filename (run 36672426334), or pip as a
    requirement. A splat must be the last thing on its line."""
    for line in powershell_source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue  # comments show the broken form on purpose
        for m in re.finditer(r"(?<=\s)@[A-Za-z_]\w*", stripped):
            assert not stripped[m.end():].strip(), (
                f"splat {m.group()} is not the whole argument list: {stripped}")


# ---------------------------------------------------- release.yml (Linux)
# Task 10 expanded the single-platform build-windows.yml into release.yml,
# which publishes both a Windows and a Linux build from one tag. These
# checks guard the properties that would otherwise fail silently: a
# runner-image bump that drops 22.04 users, a release missing one
# platform's assets, and an install smoke test that papers over a missing
# dependency instead of catching it.

def test_the_linux_job_pins_2204_not_latest():
    # glibc only works forwards: a 24.04 build cannot run on 22.04. A casual
    # bump to ubuntu-latest would silently drop half the supported users.
    # Read the job's own runs-on: a text search for the line can never tell
    # which job a `runs-on:` belongs to (the old filter on "build-linux" in
    # the same line matched nothing, so ubuntu-latest slipped through).
    yaml = pytest.importorskip("yaml")
    job = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["build-linux"]
    assert job["runs-on"] == "ubuntu-22.04"


def test_release_needs_both_builds():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "needs: [build-windows, build-linux]" in text


def test_release_asserts_all_four_assets_are_present():
    # A build that fails on one platform must not produce a release carrying
    # only the other: clients look for one name and find nothing, silently.
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "LM_LabelingTool-Setup-v" in text
    release = text[text.index("\n  release:"):]
    assert release.count("checker.full_asset_name(") == 2
    assert release.count("checker.update_asset_name(") == 2


def test_each_platform_publishes_one_package_and_one_zip(workflow):
    assert "LM_LabelingTool-App-" not in workflow
    assert "lm-labeling-tool-runtime" not in workflow
    assert "reuse_runtime.py" not in workflow
    assert workflow.count("packaging/update_zip.py") == 2


def test_the_release_page_is_generated_and_korean(workflow):
    assert "packaging/release_notes.py body" in workflow
    assert "body_path:" in workflow
    # checked before the 30-minute builds, not after them
    yaml = pytest.importorskip("yaml")
    steps = yaml.safe_load(workflow)["jobs"]["build-linux"]["steps"]
    version = next(s for s in steps if s.get("name") == "Version")["run"]
    assert "release_notes.py check" in version


def _release_steps(workflow):
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(workflow)["jobs"]["release"]["steps"]


def test_only_the_tag_message_reaches_the_release_notes(workflow):
    """%(contents) of a signed tag carries its PGP signature too."""
    yaml = pytest.importorskip("yaml")
    linux = yaml.safe_load(workflow)["jobs"]["build-linux"]["steps"]
    runs = [next(s for s in linux if s.get("name") == "Version")["run"],
            next(s for s in _release_steps(workflow) if s.get("name") == "Release page")["run"]]
    for run in runs:
        assert "%(contents)'" not in run
        assert "git tag -l --format='%(contents:subject)%0a%0a%(contents:body)'" in run
    assert "%(contents)'" not in workflow


def test_the_merged_checksums_are_verified_before_publishing(workflow):
    steps = _release_steps(workflow)
    names = [s.get("name") for s in steps]
    verify = next(i for i, s in enumerate(steps)
                  if "(cd out && sha256sum -c SHA256SUMS.txt)" in s.get("run", ""))
    assert names.index("Merge the two platforms' assets and checksums into one release") < verify
    publish = next(i for i, s in enumerate(steps)
                   if "softprops/action-gh-release" in s.get("uses", ""))
    assert verify < publish


def test_the_release_stays_a_draft_until_every_asset_is_uploaded(workflow):
    """/releases/latest must never show a release with half its assets."""
    steps = _release_steps(workflow)
    publish = next(i for i, s in enumerate(steps)
                   if "softprops/action-gh-release" in s.get("uses", ""))
    assert steps[publish]["with"]["draft"] is True
    final = steps[publish + 1]
    assert 'gh release edit "$GITHUB_REF_NAME" --draft=false' in final["run"]
    assert final["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert len(steps) == publish + 2


def test_ci_proves_a_zip_update_on_the_installed_app(workflow):
    assert "--apply-update" in workflow


def test_the_linux_dev_version_starts_with_a_digit():
    # dpkg-deb refuses a Version field that does not start with a digit
    # ("version number does not start with digit"). Every later step strips
    # a leading "v" off LT_VERSION (`ver="${LT_VERSION#v}"`) before it reaches
    # deb.py's Version field, so a tag like "v1.2.3" is fine (becomes
    # "1.2.3"), but the non-tag ("dev") branch's literal value goes through
    # that same strip UNCHANGED since it never had a leading "v" -- so IT
    # must already be digit-first. Regression: this step once used the
    # Windows-shaped "dev-<sha>" (becomes "dev-<sha>", not digit-first),
    # which makes every non-tag (manual dry-run) Linux build fail at
    # `dpkg-deb --build`. local-build.sh's own "0.0.0-dev-local" default
    # mirrors the fixed shape.
    yaml = pytest.importorskip("yaml")
    text = WORKFLOW.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    job = data["jobs"]["build-linux"]
    version_steps = [s for s in job["steps"] if s.get("name") == "Version"]
    assert version_steps, "expected a 'Version' step in build-linux"
    run = version_steps[0]["run"]
    m = re.search(r'else\s*\n\s*ver="([^"]*)"', run)
    assert m, "expected an else-branch literal ver=\"...\" assignment"
    dev_value = m.group(1)
    stripped = re.sub(r'^v', '', dev_value)  # mirrors `${LT_VERSION#v}` downstream
    assert re.match(r'^[0-9]', stripped), (
        f"build-linux's non-tag Version branch assigns ver={dev_value!r}, which "
        "does not start with a digit after the leading-'v' strip every later "
        "step applies, and would make dpkg-deb reject the app deb's Version field"
    )


def test_the_linux_build_installs_the_bundled_libraries_too():
    # deb.BUNDLED_LIBS are not declared as Depends; the runtime layer only
    # carries them if PyInstaller finds them at build time. Installing
    # RUNTIME_DEPENDS alone would ship an xcb plugin that cannot start on a
    # desktop lacking them (CI run 36841286350's failure, by another route).
    yaml = pytest.importorskip("yaml")
    job = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["build-linux"]
    runs = [s.get("run", "") for s in job["steps"] if "apt-get satisfy" in s.get("run", "")]
    assert runs, "expected the build-linux job to install libraries via apt-get satisfy"
    assert "deb.RUNTIME_DEPENDS" in runs[0]
    assert "deb.BUNDLED_LIBS" in runs[0]


def test_the_runner_installs_the_debs_before_running_the_installed_app():
    # Smoke test 1/2 installs inside a throwaway container, so nothing it
    # installs survives onto the runner. Steps that run the installed app
    # (2/2, the zip update round trip) need their own install on the
    # runner -- without it 2/2 failed with
    # "/opt/lm-labeling-tool/LM_LabelingTool: not found" (CI run
    # 36853951013).
    yaml = pytest.importorskip("yaml")
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["build-linux"]["steps"]
    runs = [s.get("run", "") for s in steps]
    uses_installed = [i for i, r in enumerate(runs)
                      if "/opt/lm-labeling-tool/" in r and "docker run" not in r]
    assert uses_installed, "expected a runner-level step that runs the installed app"
    first = uses_installed[0]
    installs = [i for i, r in enumerate(runs)
                if "sudo dpkg -i" in r and "lm-labeling-tool_" in r]
    assert installs and installs[0] <= first, \
        "the runner must install the deb before running the installed app"


def test_the_2404_cross_validation_overlaps_the_other_install_checks():
    # The 24.04 container needs nothing the 22.04 checks produce, so it
    # starts in the background as soon as the debs exist and the original
    # step only collects its result -- the two desktop installs (~3.5 min
    # each) no longer run back to back.
    yaml = pytest.importorskip("yaml")
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["build-linux"]["steps"]
    names = [s.get("name", "") for s in steps]
    runs = [s.get("run", "") for s in steps]
    start = [i for i, r in enumerate(runs) if "ubuntu:24.04" in r and "docker run" in r]
    assert start, "expected a step that starts the 24.04 container"
    smoke = next(i for i, n in enumerate(names) if n.startswith("Install smoke test 1/2"))
    assert start[0] < smoke, "the 24.04 container must start before the 22.04 checks"
    assert "&" in runs[start[0]], "the 24.04 container must be started in the background"
    collect = runs[names.index("Cross-validate the install on Ubuntu 24.04")]
    assert "docker run" not in collect, "the collecting step must not run the container again"
    assert "timeout" in collect, "waiting for the background container must be bounded"


def test_the_linux_smoke_test_forbids_apt_fix_broken():
    # `dpkg -i` must succeed on its own; needing `apt-get install -f` means
    # the runtime package declares a library users will not have either.
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "dpkg -i" in text
    assert "install -f" not in text, \
        "the smoke test must not paper over a missing dependency"


# -------------------------------------- inline `python -c` in release.yml
# A function renamed on one side of an inline `python -c` string is a
# SyntaxError or AttributeError only CI (or a human) discovers -- exactly
# what happened when checker.full_asset_name() (singular, never existed)
# sat unnoticed in this workflow until a full review caught it: every
# previous test here only did substring assertions on the raw YAML text,
# so a release-breaking typo passed 593 green tests. These two tests
# extract every inline `python -c "..."` string THE WAY THE SHELL WOULD
# RECEIVE IT (via yaml.safe_load, not a regex over the raw file -- the YAML
# block-scalar indentation strip matters) and check it for real.

_PYTHON_C_RE = re.compile(r'python(?:3)?\s+-c\s+"((?:[^"\\]|\\.)*)"', re.DOTALL)


def _iter_run_steps(workflow: dict):
    """(job name, step name, run script) for every step with a `run:` key,
    across every job -- not just build-linux."""
    for job_name, job in (workflow.get("jobs") or {}).items():
        for i, step in enumerate(job.get("steps") or []):
            run = step.get("run")
            if isinstance(run, str):
                yield job_name, step.get("name", f"step #{i}"), run


def _iter_inline_python(yaml_module, workflow_text: str):
    """(job name, step name, python source) for every `python -c "..."`
    invocation anywhere in the workflow. Parsed via yaml.safe_load so the
    source is exactly what the shell sees -- a raw-text regex would still
    carry the YAML block's own leading indentation."""
    data = yaml_module.safe_load(workflow_text)
    for job_name, step_name, run in _iter_run_steps(data):
        for m in _PYTHON_C_RE.finditer(run):
            yield job_name, step_name, m.group(1)


def test_inline_python_in_the_workflow_actually_compiles():
    yaml = pytest.importorskip("yaml")
    text = WORKFLOW.read_text(encoding="utf-8")
    snippets = list(_iter_inline_python(yaml, text))
    assert snippets, "expected at least one inline `python -c` in release.yml"
    problems = []
    for job_name, step_name, snippet in snippets:
        try:
            compile(snippet, f"<{job_name}: {step_name}>", "exec")
        except SyntaxError as exc:
            problems.append(f"{job_name} / {step_name!r}: {exc.__class__.__name__}: {exc}")
    assert not problems, "\n".join(problems)


def test_inline_python_only_references_real_checker_layers_deb_names():
    # compile() alone would NOT have caught checker.full_asset_name()
    # (singular): calling a nonexistent attribute is syntactically valid
    # Python, and only fails at runtime with an AttributeError. This walks
    # every real `checker.X` / `layers.X` / `deb.X` ATTRIBUTE ACCESS (via
    # the AST, not a text regex -- a regex would also match "checker.py"
    # inside an unrelated string literal like a log message) and checks X
    # is a real attribute of the real module.
    import ast

    yaml = pytest.importorskip("yaml")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packaging"))
    import deb as deb_module  # noqa: E402
    import layers as layers_module  # noqa: E402
    from labeling_tool.update import checker as checker_module

    modules = {"checker": checker_module, "layers": layers_module, "deb": deb_module}

    text = WORKFLOW.read_text(encoding="utf-8")
    problems = []
    for job_name, step_name, snippet in _iter_inline_python(yaml, text):
        tree = ast.parse(snippet)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                    and node.value.id in modules
                    and not hasattr(modules[node.value.id], node.attr)):
                problems.append(f"{job_name} / {step_name!r}: "
                                 f"{node.value.id}.{node.attr} does not exist")
    assert not problems, "\n".join(problems)


def test_the_workflow_does_not_pretend_to_tune_dpkg_deb_threads(workflow):
    # dpkg-deb on jammy (1.21.1) ignores XZ_OPT -- measured: byte-identical
    # output in the same time -- and is already multi-threaded by default.
    # Leaving XZ_OPT=-T4 in place suggested a tuning knob that does nothing.
    assert "XZ_OPT=" not in workflow
