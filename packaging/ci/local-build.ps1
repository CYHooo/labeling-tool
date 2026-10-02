# Verify a Windows release locally. This is the ONLY place the checks run:
# CI (.github/workflows/release.yml) just builds and publishes a tag,
# because a CI round took 18-25 minutes and every failure cost another.
# Run all steps and get a green result before tagging; see docs/RELEASING.md.
#
# The build steps match CI's (same Python, same lock, same spec), so the
# runtime id printed here is the one the release will carry. That is the
# answer to "will this release be a small update or a full install?".
#
# The smoke step proves both halves of a release: the Setup exe installs
# and runs, and the installed app applies this build's update zip to
# itself -- the path every routine update takes.
#
# One-time setup (Python 3.12.10 and Inno Setup 6 installed). The venv must
# be FRESH -- stray packages in it get bundled and move the runtime id:
#   & "C:\Program Files\Python312\python.exe" -m venv C:\lt\venv
#   $env:SAM2_BUILD_CUDA = "0"
#   # sam2's repo has symlinks; without this git writes placeholders (see CI)
#   $env:GIT_CONFIG_COUNT = "1"; $env:GIT_CONFIG_KEY_0 = "core.symlinks"; $env:GIT_CONFIG_VALUE_0 = "true"
#   $pip = "C:\lt\venv\Scripts\pip.exe"
#   & $pip install -c packaging/build-constraints.txt -c packaging/build-lock.txt -r requirements-dev.txt "pyinstaller==6.22.3"
#   & $pip install -c packaging/build-constraints.txt -c packaging/build-lock.txt "torch==2.5.1" "torchvision==0.20.1" --index-url https://download.pytorch.org/whl/cu124
#   & $pip install -c packaging/build-constraints.txt -c packaging/build-lock.txt --no-build-isolation "git+https://github.com/facebookresearch/sam2.git@2b90b9f5ceec907a1c18123530e92e794ad901a4"
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
    & $py -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider --color=no
    if ($LASTEXITCODE -ne 0) { throw "tests failed" }
}

Step "build" {
    # sam2 installed with core.symlinks=false carries 30-byte placeholders
    # where CI has the real yaml; the build would work but its runtime id
    # would never match the release's.
    $probe = Join-Path $Venv "Lib\site-packages\sam2\sam2_hiera_l.yaml"
    if ((Test-Path $probe) -and (Get-Item $probe).Length -lt 1000) {
        throw "sam2 was installed without git symlinks ($probe is a placeholder); reinstall it as in the setup notes at the top of this script"
    }
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
    # MyTestInstall: a separate AppId and Start menu name, so the smoke step
    # can install and uninstall next to a real install. Local installers are
    # never published -- releases are built by CI from the tag.
    # Splatting only expands when it IS the whole argument list, so build
    # the array first.
    $isccArgs = @("/DMyVersion=$Version", "/DMyVersionInfo=0.0.0", "/DMySourceRoot=$PWD",
                  "/DMyFast=1", "/DMyTestInstall=1", "/Q",
                  "/DMySource=$PWD\$dist", "/DMyOutDir=$PWD\out", "packaging\installer.iss")
    & $iscc @isccArgs
    if ($LASTEXITCODE -ne 0) { throw "full installer failed" }
    # The app-layer update zip, named for the runtime id it was built
    # against -- what the smoke step applies to the installed app.
    & $py packaging/update_zip.py dist/app-layer out $Version $script:runtimeId win32
    if ($LASTEXITCODE -ne 0) { throw "update zip failed" }
    Get-ChildItem out\*.exe, out\*.zip | ForEach-Object { "{0}  {1:N1} MB" -f $_.Name, ($_.Length / 1MB) }
}

Step "smoke" {
    # The installers above carry the TEST AppId (MyTestInstall), so a real
    # install on this machine is never touched. A leftover test install from
    # an aborted run would turn the full install into an upgrade; clear it.
    $key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{73FDC7BA-1CC5-4842-80BD-078ED75FD1A6}_is1"
    if (Test-Path $key) {
        $old = (Get-ItemProperty $key).UninstallString -replace '"', ''
        Write-Host "removing a leftover test install: $old"
        $null = Invoke-Installer -Path $old -TimeoutSec 600
        Start-Sleep -Seconds 5
    }
    $full = Get-ChildItem out\LM_LabelingTool-Setup-*.exe | Select-Object -First 1
    $zip = Get-ChildItem out\update-v*-windows.zip | Select-Object -First 1
    if (-not $full) { throw "no Setup exe in out\; run the installer step first" }
    if (-not $zip) { throw "no update zip in out\; run the installer step first" }
    $target = Join-Path $env:TEMP "lt-install"
    $code = Invoke-Installer -Path $full.FullName -InstallerArgs @("/DIR=$target", "/LOG=$env:TEMP\lt-install.log") -TimeoutSec 900
    if ($code -ne 0) { throw "install failed ($code)" }
    $code = Invoke-Bounded -Path "$target\LM_LabelingTool.exe" -CallArgs @("--selftest=full") -TimeoutSec 300 -What "selftest after the full install"
    if ($code -ne 0) { Get-Content "$target\selftest.log"; throw "selftest after the full install failed" }
    Write-Host "full install: selftest PASS"
    $sentinels = @("$target\_internal\torch\version.py", "$target\_internal\sam2\build_sam.py",
                   "$target\_internal\PyQt5\QtWidgets.pyd") | Where-Object { Test-Path $_ }
    # Damage one installed app-layer file, then let the zip repair it.
    # (build-info.json must stay intact: the update reads its runtime id.)
    $victim = Get-ChildItem "$target\_internal\labeling_tool" -Recurse -File -Filter *.pyc | Select-Object -First 1
    if (-not $victim) { throw "no installed app-layer .pyc to damage" }
    $victimPath = $victim.FullName
    Remove-Item $victimPath
    $sha = (Get-FileHash $zip.FullName -Algorithm SHA256).Hash.ToLower()
    # Start-Process joins -ArgumentList with spaces and quotes nothing; a
    # checkout path with a space in it would split the zip path in two.
    $zipArg = '"' + $zip.FullName + '"'
    $code = Invoke-Bounded -Path "$target\LM_LabelingTool.exe" -CallArgs @("--apply-update", $zipArg, "--sha256", $sha) -TimeoutSec 300 -What "applying the update zip"
    if ($code -ne 0) { throw "applying the update zip failed ($code)" }
    if (-not (Test-Path $victimPath)) { throw "the update zip did not restore $victimPath" }
    if (Test-Path "$target\.update-journal") { throw "the update zip left its journal behind" }
    foreach ($f in $sentinels) { if (-not (Test-Path $f)) { throw "the update zip deleted $f" } }
    $code = Invoke-Bounded -Path "$target\LM_LabelingTool.exe" -CallArgs @("--selftest=full") -TimeoutSec 300 -What "selftest after the zip update"
    if ($code -ne 0) { Get-Content "$target\selftest.log"; throw "selftest after the zip update failed" }
    Write-Host "zip update: applied, selftest PASS"
    $u = Get-ChildItem "$target\unins*.exe" | Select-Object -First 1
    $null = Invoke-Installer -Path $u.FullName -TimeoutSec 600
    Start-Sleep -Seconds 10
    foreach ($f in $sentinels) { if (Test-Path $f) { throw "uninstall left $f behind" } }
    if (Test-Path "$target\.update-backup") { throw "uninstall left $target\.update-backup behind" }
    Write-Host "uninstall removed the runtime layer and the update leftovers"
}

Write-Host ""
$timings.GetEnumerator() | ForEach-Object { "{0,-10} {1,5} s" -f $_.Key, $_.Value }
