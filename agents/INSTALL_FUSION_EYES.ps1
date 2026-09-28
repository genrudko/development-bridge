$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BridgePython = Join-Path $Root ".venv\Scripts\python.exe"
$ManagedRoot = Join-Path $env:LOCALAPPDATA "DevelopmentBridgeFusion"
$Repo = Join-Path $ManagedRoot "periscope"
$Patch = Join-Path $Root "periscope-lost-event.patch"
$PeriscopeHome = Join-Path $env:LOCALAPPDATA "Periscope"
$PeriscopePython = Join-Path $Repo "server\.venv\Scripts\python.exe"
$Upstream = "https://github.com/VXNTedits/fusion360-mcp-periscope.git"
$Pin = "a676b94a9d54ed3cc2b1620df1f08b5ef34774a7"

function Invoke-GitChecked {
    param([Parameter(Mandatory=$true)][string[]]$Arguments)
    & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git failed ($LASTEXITCODE): git $($Arguments -join ' ')"
    }
}

function Git-Output {
    param([Parameter(Mandatory=$true)][string[]]$Arguments)
    $output = & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git failed ($LASTEXITCODE): git $($Arguments -join ' ')"
    }
    return ($output -join "`n").Trim()
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git for Windows is required."
}
if (-not (Test-Path -LiteralPath $BridgePython -PathType Leaf)) {
    throw "Fusion Bridge Python is missing: $BridgePython. Run START_FUSION_GUI.cmd once first."
}
if (-not (Test-Path -LiteralPath $Patch -PathType Leaf)) {
    throw "Bundled PERISCOPE patch is missing: $Patch"
}

New-Item -ItemType Directory -Force -Path $ManagedRoot | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $Repo ".git"))) {
    Invoke-GitChecked @("clone", $Upstream, $Repo)
}

$Origin = Git-Output @("-C", $Repo, "remote", "get-url", "origin")
if ($Origin -ne $Upstream) {
    throw "Managed PERISCOPE origin is unexpected: $Origin"
}

$Head = Git-Output @("-C", $Repo, "rev-parse", "HEAD")
if ($Head -ne $Pin) {
    $DirtyBeforePin = Git-Output @("-C", $Repo, "status", "--porcelain")
    if (-not [string]::IsNullOrWhiteSpace($DirtyBeforePin)) {
        throw "PERISCOPE install is dirty outside the managed patch; refusing to switch revisions."
    }
    Invoke-GitChecked @("-C", $Repo, "fetch", "origin", $Pin)
    Invoke-GitChecked @("-C", $Repo, "checkout", "--detach", $Pin)
}

# Recognize an already-applied managed patch before treating the checkout as dirty.
& git -C $Repo apply --reverse --check $Patch *> $null
$PatchAlreadyApplied = ($LASTEXITCODE -eq 0)
if ($PatchAlreadyApplied) {
    $ManagedPath = "addin/Periscope/periscope_bridge/marshal.py"
    $ChangedPaths = Git-Output @("-C", $Repo, "diff", "--name-only")
    $StagedPaths = Git-Output @("-C", $Repo, "diff", "--cached", "--name-only")
    $UntrackedPaths = Git-Output @("-C", $Repo, "ls-files", "--others", "--exclude-standard")
    if ($ChangedPaths -ne $ManagedPath -or
        -not [string]::IsNullOrWhiteSpace($StagedPaths) -or
        -not [string]::IsNullOrWhiteSpace($UntrackedPaths)) {
        throw "PERISCOPE install is dirty outside the managed patch; refusing to continue."
    }
    $ManagedDiff = Git-Output @("-C", $Repo, "diff", "--", $ManagedPath)
    $ExpectedPatch = (Get-Content -LiteralPath $Patch -Raw -Encoding UTF8).Trim()
    $NormalizePatch = {
        param([string]$Text)
        $lines = (($Text -replace "`r`n", "`n") -split "`n") |
            Where-Object { $_ -notmatch '^index [0-9a-f]+\.\.[0-9a-f]+ ' }
        return (($lines -join "`n").Trim())
    }
    if ((& $NormalizePatch $ManagedDiff) -ne (& $NormalizePatch $ExpectedPatch)) {
        throw "Managed PERISCOPE patch differs from bundled patch; refusing to continue."
    }
} else {
    $DirtyBeforePatch = Git-Output @("-C", $Repo, "status", "--porcelain")
    if (-not [string]::IsNullOrWhiteSpace($DirtyBeforePatch)) {
        throw "PERISCOPE install is dirty outside the managed patch; refusing to apply over local changes."
    }
    & git -C $Repo apply --check $Patch
    if ($LASTEXITCODE -ne 0) {
        throw "Qualified PERISCOPE patch does not apply cleanly to pinned revision $Pin."
    }
    Invoke-GitChecked @("-C", $Repo, "apply", $Patch)
}

# Full install creates config/token/server venv. Existing qualified installs only need code sync.
$Config = Join-Path $PeriscopeHome "config.json"
$Token = Join-Path $PeriscopeHome "token"
$ExistingRuntime = (Test-Path -LiteralPath $Config -PathType Leaf) -and
                   (Test-Path -LiteralPath $Token -PathType Leaf) -and
                   (Test-Path -LiteralPath $PeriscopePython -PathType Leaf)
$Installer = Join-Path $Repo "install\install.py"
if ($ExistingRuntime) {
    & $BridgePython $Installer --sync
} else {
    & $BridgePython $Installer
}
if ($LASTEXITCODE -ne 0) {
    throw "PERISCOPE installer failed with exit code $LASTEXITCODE"
}
if (-not (Test-Path -LiteralPath $PeriscopePython -PathType Leaf)) {
    throw "PERISCOPE server Python was not created: $PeriscopePython"
}

& $PeriscopePython -m pip install --disable-pip-version-check -q "mcp>=1.27,<2" "mcp-proxy==0.12.0"
if ($LASTEXITCODE -ne 0) {
    throw "Could not install the qualified MCP proxy dependencies."
}

& $PeriscopePython -c "import importlib.metadata as m; mv=m.version('mcp'); pv=m.version('mcp-proxy'); assert int(mv.split('.')[0]) < 2 and pv == '0.12.0', (mv,pv); print('mcp='+mv+' mcp-proxy='+pv)"
if ($LASTEXITCODE -ne 0) {
    throw "Qualified MCP dependency verification failed."
}

$FinalHead = Git-Output @("-C", $Repo, "rev-parse", "HEAD")
if ($FinalHead -ne $Pin) {
    throw "PERISCOPE revision drifted during install: $FinalHead"
}
& git -C $Repo apply --reverse --check $Patch *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Lost-event patch is not present after install."
}

Write-Host ""
Write-Host "Fusion Eyes runtime installed and verified."
Write-Host "PERISCOPE pin: $Pin"
Write-Host "Lost-event patch: present"
Write-Host "Normal use: START_FUSION_GUI.cmd -> Start. No manual proxy/Relay PowerShell is required."
Write-Host "If PERISCOPE was already running in Fusion, Stop -> Run it once so the synced add-in code is loaded."
