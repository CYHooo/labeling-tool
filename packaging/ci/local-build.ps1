# Run the Windows CI build locally, step for step, before spending a CI run.
#
# CI takes ~18 minutes a round and only reports at the end; a local Windows
# machine (or VM) gets the same answers faster and can be re-run piecemeal.
# The steps mirror .github/workflows/build-windows.yml -- keep them in step
# when that file changes.
#
# One-time setup (Python 3.12 and Inno Setup 6 installed):
#   py -3.12 -m venv C:\lt\venv
#   $env:SAM2_BUILD_CUDA = "0"
#   C:\lt\venv\Scripts\pip install -c packaging/build-constraints.txt -r requirements-dev.txt "pyinstaller==6.22.3"
#   C:\lt\venv\Scripts\pip install -c packaging/build-constraints.txt "torch==2.5.1" "torchvision==0.20.1" --index-url https://download.pytorch.org/whl/cu124
#   C:\lt\venv\Scripts\pip install -c packaging/build-constraints.txt --no-build-isolation "git+https://github.com/facebookresearch/sam2.git@2b90b9f5ceec907a1c18123530e92e794ad901a4"
#
# Build on a local disk: a 4 GB onedir tree over a network share is slow.
#
# Usage, from the repository root:
#   powershell -File packaging\ci\local-build.ps1 -Venv C:\lt\venv
#   ... -Steps build,layers              # only some steps
#   ... -Steps layers -Tag run2          # keep a second manifest to diff

param(
    [Parameter(Mandatory = $true)][string] $Venv,
    [string[]] $Steps = @("tests", "build", "selftest", "layers", "installer", "smoke"),
    # Suffix for diag\runtime-manifest-<Tag>.txt, so repeated builds can be
    # compared with Compare-Object / diff.
    [string] $Tag = "local",
    [string] $Version = "dev-local"
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\bounded.ps1"

# `powershell -File` hands "-Steps build,layers" over as ONE string; without
# this split no step matches and the script silently does nothing.
$Steps = @($Steps | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$known = @("tests", "build", "selftest", "layers", "installer", "smoke")
$unknown = @($Steps | Where-Object { $known -notcontains $_ })
if ($unknown.Count) { throw "unknown step(s): $($unknown -join ', '); known: $($known -join ', ')" }

$py = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $py)) { throw "no python at $py" }
$env:QT_QPA_PLATFORM = "offscreen"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$dist = "dist\LM_LabelingTool"
$timings = [ordered]@{}

function Step([string] $name, [scriptblock] $body) {
    if ($Steps -notcontains $name) { return }
    Write-Host "==> $name" -ForegroundColor Cyan
    $t = [Diagnostics.Stopwatch]::StartNew()
    & $body
    $timings[$name] = [math]::Round($t.Elapsed.TotalSeconds)
}

Step "tests" {
    & $py -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw "tests failed" }
}

Step "build" {
    Remove-Item -Recurse -Force build, $dist -ErrorAction SilentlyContinue
    & (Join-Path $Venv "Scripts\pyinstaller.exe") --noconfirm --log-level WARN packaging/labeling_tool.spec
    if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed" }
}

Step "selftest" {
    $code = Invoke-Bounded -Path "$dist\LM_LabelingTool.exe" -CallArgs @("--selftest=full") -TimeoutSec 300 -What "selftest on the build output"
    if (Test-Path "$dist\selftest.log") { Get-Content "$dist\selftest.log"; Remove-Item "$dist\selftest.log" }
    if ($code -ne 0) { throw "selftest failed ($code)" }
    $p = Start-Process -FilePath "$dist\LM_LabelingTool.exe" -PassThru
    Start-Sleep -Seconds 20
    if ($p.HasExited) { throw "LM_LabelingTool.exe exited early with code $($p.ExitCode)" }
    Stop-Process -Id $p.Id -Force
    Start-Sleep -Seconds 2
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "$dist\data", "$dist\config.json"
}

Step "layers" {
    $rt = & $py packaging/layers.py runtime-id $dist
    if (-not ($rt -match '^r[0-9a-f]{8}$')) { throw "bad runtime id: $rt" }
    $script:runtimeId = $rt
    Write-Host "runtime id: $rt"
    New-Item -ItemType Directory -Force diag | Out-Null
    & $py packaging/layers.py manifest $dist | Set-Content -Path "diag\runtime-manifest-$Tag.txt" -Encoding utf8
    Write-Host "manifest: diag\runtime-manifest-$Tag.txt"
    $info = @{ version = $Version; variant = 'full'; runtime = $rt; commit = 'local' }
    $info | ConvertTo-Json -Compress | Set-Content -Path "$dist\build-info.json" -Encoding utf8
    Remove-Item -Recurse -Force dist\app-layer -ErrorAction SilentlyContinue
    & $py packaging/layers.py stage $dist dist/app-layer
    if ($LASTEXITCODE -ne 0) { throw "staging the app layer failed" }
    $app = Get-ChildItem dist/app-layer -Recurse -File | Measure-Object -Property Length -Sum
    Write-Host ("app layer: {0:N1} MB in {1} files" -f ($app.Sum / 1MB), $app.Count)
    if ($app.Sum -gt 20MB) { throw "app layer unexpectedly large" }
}

Step "installer" {
    if (-not $script:runtimeId) {
        $script:runtimeId = (Get-Content "$dist\build-info.json" | ConvertFrom-Json).runtime
    }
    # A per-user install (winget without admin) lands under LOCALAPPDATA.
    $iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
              "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) { throw "ISCC.exe not found; install Inno Setup 6" }
    Remove-Item -Recurse -Force out, out-bad -ErrorAction SilentlyContinue
    $common = @("/DMyVersion=$Version", "/DMyVersionInfo=0.0.0", "/DMySourceRoot=$PWD", "/DMyFast=1", "/Q")
    $isccArgs = @("/DMyLayer=full", "/DMySource=$PWD\$dist", "/DMyOutDir=$PWD\out",
                  "/DMyRuntime=$script:runtimeId") + $common + @("packaging\installer.iss")
    & $iscc @isccArgs
    if ($LASTEXITCODE -ne 0) { throw "full installer failed" }
    $isccArgs = @("/DMyLayer=app", "/DMySource=$PWD\dist\app-layer", "/DMyOutDir=$PWD\out",
                  "/DMyRuntime=$script:runtimeId") + $common + @("packaging\installer.iss")
    & $iscc @isccArgs
    if ($LASTEXITCODE -ne 0) { throw "app installer failed" }
    $isccArgs = @("/DMyLayer=app", "/DMySource=$PWD\dist\app-layer", "/DMyOutDir=$PWD\out-bad",
                  "/DMyRuntime=rbadbad00") + $common + @("packaging\installer.iss")
    & $iscc @isccArgs
    if ($LASTEXITCODE -ne 0) { throw "could not build the mismatched app package" }
    Get-ChildItem out\*.exe, out-bad\*.exe | ForEach-Object { "{0}  {1:N1} MB" -f $_.Name, ($_.Length / 1MB) }
}

Step "smoke" {
    # The test installs, upgrades and UNINSTALLS under the real AppId. On a
    # machine that also has the app installed for use, that rewrites its
    # uninstall entry and can take its data with it. CI runners are clean;
    # a workstation usually is not.
    $key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{9E1E0C6B-6E0F-4E8E-9E2F-0F7B5C1A0F02}_is1"
    if (Test-Path $key) {
        $where = (Get-ItemProperty $key).InstallLocation
        throw "LM_LabelingTool is installed here ($where); the smoke step would disturb it. Run it on a clean VM, or leave it to CI."
    }
    $full =Get-ChildItem out\LM_LabelingTool-Setup-*.exe | Select-Object -First 1
    $app = Get-ChildItem out\LM_LabelingTool-App-*.exe | Select-Object -First 1
    $bad = Get-ChildItem out-bad\LM_LabelingTool-App-*.exe | Select-Object -First 1
    $target = Join-Path $env:TEMP "lt-install"
    $code = Invoke-Installer -Path $full.FullName -InstallerArgs @("/DIR=$target", "/LOG=$env:TEMP\lt-install.log") -TimeoutSec 900
    if ($code -ne 0) { throw "install failed ($code)" }
    $code = Invoke-Bounded -Path "$target\LM_LabelingTool.exe" -CallArgs @("--selftest=full") -TimeoutSec 300 -What "selftest after the full install"
    if ($code -ne 0) { Get-Content "$target\selftest.log"; throw "selftest after the full install failed" }
    Write-Host "full install: selftest PASS"
    $sentinels = @("$target\_internal\torch\version.py", "$target\_internal\sam2\build_sam.py",
                   "$target\_internal\PyQt5\QtWidgets.pyd") | Where-Object { Test-Path $_ }
    $code = Invoke-Installer -Path $app.FullName -InstallerArgs @("/DIR=$target") -TimeoutSec 300
    if ($code -ne 0) { throw "app install failed ($code)" }
    foreach ($f in $sentinels) { if (-not (Test-Path $f)) { throw "the app package deleted $f" } }
    $code = Invoke-Bounded -Path "$target\LM_LabelingTool.exe" -CallArgs @("--selftest=full") -TimeoutSec 300 -What "selftest after the app-layer install"
    if ($code -ne 0) { Get-Content "$target\selftest.log"; throw "selftest after the app-layer install failed" }
    Write-Host "app-layer install: selftest PASS"
    $stamp = (Get-Item "$target\LM_LabelingTool.exe").LastWriteTimeUtc
    $code = Invoke-Installer -Path $bad.FullName -TimeoutSec 300
    if ($code -eq 0) { throw "the mismatched app package installed anyway" }
    if ((Get-Item "$target\LM_LabelingTool.exe").LastWriteTimeUtc -ne $stamp) { throw "the refused package still wrote to the install" }
    Write-Host "mismatched app package refused ($code)"
    $u = Get-ChildItem "$target\unins*.exe" | Select-Object -First 1
    $null = Invoke-Installer -Path $u.FullName -TimeoutSec 600
    Start-Sleep -Seconds 10
    foreach ($f in $sentinels) { if (Test-Path $f) { throw "uninstall left $f behind" } }
    Write-Host "uninstall removed the runtime layer"
}

Write-Host ""
$timings.GetEnumerator() | ForEach-Object { "{0,-10} {1,5} s" -f $_.Key, $_.Value }
