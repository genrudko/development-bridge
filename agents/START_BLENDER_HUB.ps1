param(
    [string]$BridgeUrl = $env:DEVELOPMENT_BRIDGE_URL,
    [string]$NodeId = "blender-workstation",
    [string]$Providers = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $BridgeUrl) {
    throw "Set DEVELOPMENT_BRIDGE_URL or pass -BridgeUrl."
}
if (-not $env:DEVELOPMENT_BRIDGE_DESKTOP_TOKEN) {
    throw "Set DEVELOPMENT_BRIDGE_DESKTOP_TOKEN in the environment."
}
if (-not $Providers) {
    $Providers = Join-Path $ScriptDir "blender_hub_providers.json"
}

$Python = $env:DEVELOPMENT_BRIDGE_PYTHON
if (-not $Python) {
    $VenvPython = Join-Path (Split-Path -Parent $ScriptDir) ".venv\Scripts\python.exe"
    if (Test-Path $VenvPython) {
        $Python = $VenvPython
    } else {
        $Python = "python"
    }
}

$GuiPython = $Python
if ([System.IO.Path]::GetFileName($Python) -ieq "python.exe") {
    $Candidate = Join-Path (Split-Path -Parent $Python) "pythonw.exe"
    if (Test-Path $Candidate) {
        $GuiPython = $Candidate
    }
} elseif ($Python -eq "python") {
    $Pythonw = Get-Command pythonw -ErrorAction SilentlyContinue
    if ($Pythonw) {
        $GuiPython = $Pythonw.Source
    }
}

$Gui = Join-Path $ScriptDir "blender_hub_gui.pyw"
$Arguments = @(
    $Gui,
    "--bridge-url", $BridgeUrl,
    "--node-id", $NodeId,
    "--providers", $Providers
)
Start-Process -FilePath $GuiPython -ArgumentList $Arguments -WorkingDirectory (Split-Path -Parent $ScriptDir)
