$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ManagedRoot = Join-Path $env:LOCALAPPDATA "DevelopmentBridgeFusion\launcher"
$ManagedScript = Join-Path $ManagedRoot "START_FUSION_GUI.ps1"
$LauncherFiles = @(
    "START_FUSION_GUI.cmd", "START_FUSION_GUI.ps1", "START_FUSION_AGENT.ps1", "fusion_relay_gui.pyw",
    "fusion_hands_runtime.py", "fusion_eyes_runtime.py", "windows_fusion_agent.py",
    "FUSION_GUI_README.txt", "INSTALL_FUSION_EYES.ps1", "INSTALL_FUSION_HANDS.ps1", "periscope-lost-event.patch"
)
$OverlayFiles = @(
    "README.md", "install.py", "manifest.json", "addin_bridge_cad.py", "server_bridge_cad.py"
)

function Get-NormalizedPath([string] $Path) {
    return [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
}

function Copy-LauncherFile([string] $Source, [string] $Destination) {
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
        throw "Missing launcher package asset: $Source"
    }
    $Parent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Force -Path $Parent | Out-Null
    $Temporary = Join-Path $Parent ((Split-Path -Leaf $Destination) + ".new-" + [Guid]::NewGuid().ToString("N"))
    try {
        Copy-Item -LiteralPath $Source -Destination $Temporary
        if (Test-Path -LiteralPath $Destination) {
            Copy-Item -LiteralPath $Temporary -Destination $Destination -Force
        } else {
            Move-Item -LiteralPath $Temporary -Destination $Destination
        }
    } finally {
        Remove-Item -LiteralPath $Temporary -Force -ErrorAction SilentlyContinue
    }
}

function Copy-LauncherPackage {
    foreach ($Name in $LauncherFiles) {
        Copy-LauncherFile (Join-Path $PackageRoot $Name) (Join-Path $ManagedRoot $Name)
    }
    $PackageOverlay = Join-Path $PackageRoot "fusion_shimmer_overlay"
    if (-not (Test-Path -LiteralPath (Join-Path $PackageOverlay "install.py"))) {
        $PackageOverlay = Join-Path (Split-Path -Parent $PackageRoot) "ops\fusion_shimmer_overlay"
    }
    foreach ($Name in $OverlayFiles) {
        Copy-LauncherFile (Join-Path $PackageOverlay $Name) (Join-Path $ManagedRoot "fusion_shimmer_overlay\$Name")
    }
}

Add-Type -AssemblyName System.Windows.Forms
try {
    if ((Get-NormalizedPath $PackageRoot) -ne (Get-NormalizedPath $ManagedRoot)) {
        Copy-LauncherPackage
        & $ManagedScript
        exit $LASTEXITCODE
    }

    $Venv = Join-Path $ManagedRoot ".venv"
    $Python = Join-Path $Venv "Scripts\python.exe"
    $PythonW = Join-Path $Venv "Scripts\pythonw.exe"
    $Gui = Join-Path $ManagedRoot "fusion_relay_gui.pyw"
    if (-not (Test-Path (Join-Path $ManagedRoot "fusion_hands_runtime.py"))) { throw "Missing fusion_hands_runtime.py" }
    if (-not (Test-Path (Join-Path $ManagedRoot "fusion_shimmer_overlay\install.py"))) { throw "Missing fusion_shimmer_overlay assets" }
    & py -3.12 --version *> $null
    if ($LASTEXITCODE -ne 0) { throw "Python 3.12 not found" }
    if (-not (Test-Path $Python)) {
        & py -3.12 -m venv $Venv
        if ($LASTEXITCODE -ne 0) { throw "Could not create Python venv" }
    }
    $NeedMcp = $true
    try {
        $Installed = & $Python -c "import importlib.metadata; print(importlib.metadata.version('mcp'))" 2>$null
        if ($LASTEXITCODE -eq 0 -and $Installed.Trim() -eq "2.0.0") { $NeedMcp = $false }
    } catch {}
    if ($NeedMcp) {
        & $Python -m pip install --disable-pip-version-check "mcp==2.0.0" *> $null
        if ($LASTEXITCODE -ne 0) { throw "Could not install mcp==2.0.0" }
    }

    $BootstrapLog = Join-Path $ManagedRoot "bootstrap-install.log"
    function Invoke-OptionalProviderInstaller([string] $Name, [string] $Installer, [string] $Runtime) {
        if (Test-Path -LiteralPath $Runtime -PathType Leaf) { return }
        try {
            ("[{0}] installing missing {1} runtime" -f (Get-Date -Format s), $Name) | Add-Content -LiteralPath $BootstrapLog -Encoding UTF8
            & $Installer *>> $BootstrapLog
            if (-not (Test-Path -LiteralPath $Runtime -PathType Leaf)) {
                throw "$Name installer completed without creating its qualified runtime"
            }
        } catch {
            ("[{0}] {1} install degraded: {2}" -f (Get-Date -Format s), $Name, $_.Exception.Message) | Add-Content -LiteralPath $BootstrapLog -Encoding UTF8
        }
    }
    $EyesInstaller = Join-Path $ManagedRoot "INSTALL_FUSION_EYES.ps1"
    $EyesRuntime = Join-Path $env:LOCALAPPDATA "DevelopmentBridgeFusion\periscope\server\.venv\Scripts\python.exe"
    $HandsInstaller = Join-Path $ManagedRoot "INSTALL_FUSION_HANDS.ps1"
    $HandsRuntime = Join-Path $env:LOCALAPPDATA "DevelopmentBridgeFusion\shimmer-sidecar\venv\Scripts\fusion-mcp.exe"
    Invoke-OptionalProviderInstaller "Eyes" $EyesInstaller $EyesRuntime
    Invoke-OptionalProviderInstaller "Hands" $HandsInstaller $HandsRuntime

    Start-Process -FilePath $PythonW -ArgumentList ('"' + $Gui + '"') -WorkingDirectory $ManagedRoot
} catch {
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, "Fusion Bridge", 'OK', 'Error') | Out-Null
    exit 1
}
