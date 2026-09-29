# Bounded process helpers for the Windows build.
#
# Every Start-Process the workflow waits on goes through these. A hung
# installer or a hung exe must fail in minutes with a name attached, not
# sit until the job's budget runs out: one such hang cost 96 minutes
# (run 36518723697) and another left a tag build with nothing to show
# for 47 minutes (run 36547963747), both reported only as "the hosted
# runner lost communication with the server".
#
# Dot-source from a step:  . packaging/ci/bounded.ps1

Set-StrictMode -Version Latest

function Invoke-Bounded {
    param(
        [Parameter(Mandatory = $true)][string] $Path,
        [string[]] $CallArgs = @(),
        [Parameter(Mandatory = $true)][int] $TimeoutSec,
        [Parameter(Mandatory = $true)][string] $What
    )
    $proc = Start-Process -FilePath $Path -ArgumentList $CallArgs -PassThru
    # Touch Handle first: without it PowerShell leaves ExitCode null, and a
    # failing process would read as success.
    $null = $proc.Handle
    if (-not $proc.WaitForExit($TimeoutSec * 1000)) {
        try { $proc.Kill() } catch { }
        throw "$What timed out after ${TimeoutSec}s"
    }
    return $proc.ExitCode
}

function Invoke-Installer {
    param(
        [Parameter(Mandatory = $true)][string] $Path,
        [string[]] $InstallerArgs = @(),
        [Parameter(Mandatory = $true)][int] $TimeoutSec
    )
    $all = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") + $InstallerArgs
    return Invoke-Bounded -Path $Path -CallArgs $all -TimeoutSec $TimeoutSec `
        -What "installer $(Split-Path $Path -Leaf)"
}

function Write-DiskSpace {
    # A full disk surfaces as "lost communication" too, which is
    # indistinguishable from a hang unless the free space is on record.
    Get-PSDrive -PSProvider FileSystem |
        Where-Object { $null -ne $_.Used } |
        ForEach-Object { "{0}: {1:N1} GB free of {2:N1} GB" -f $_.Name, ($_.Free / 1GB), (($_.Used + $_.Free) / 1GB) }
}
