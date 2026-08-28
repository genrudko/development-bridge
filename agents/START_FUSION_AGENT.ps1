$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Agent = Join-Path $Root "windows_fusion_agent.py"

Write-Host ""
Write-Host "=== ChatGPT -> Development Bridge -> Fusion MCP relay v2 ==="
Write-Host ""

try {
    py -3.12 --version | Out-Host
} catch {
    Write-Host "Python 3.12 not found. Install Python 3.12 for Windows, then run this script again."
    Read-Host "Press Enter to exit"
    exit 1
}

if (-not (Test-Path $Python)) {
    Write-Host "Creating Python venv..."
    py -3.12 -m venv $Venv
}

$NeedMcp = $true
try {
    $Installed = & $Python -c "import importlib.metadata; print(importlib.metadata.version('mcp'))"
    if ($LASTEXITCODE -eq 0 -and $Installed.Trim() -eq "2.0.0") {
        $NeedMcp = $false
        Write-Host "MCP Python SDK 2.0.0 is already installed."
    }
} catch {}

if ($NeedMcp) {
    Write-Host "Installing MCP Python SDK 2.0.0..."
    & $Python -m pip install --disable-pip-version-check "mcp==2.0.0"
    if ($LASTEXITCODE -ne 0) { throw "Could not install mcp==2.0.0" }
}

$tcp = Test-NetConnection -ComputerName 127.0.0.1 -Port 27182 -WarningAction SilentlyContinue
if (-not $tcp.TcpTestSucceeded) {
    Write-Warning "Fusion MCP is not listening on 127.0.0.1:27182 yet."
    Write-Host "That is OK: the relay will keep retrying. Start Fusion and enable Preferences -> General -> API -> Fusion MCP Server."
}

$Token = $env:DEVELOPMENT_BRIDGE_DESKTOP_NODE_TOKEN
if ([string]::IsNullOrWhiteSpace($Token)) {
    $SecureToken = Read-Host "Paste the Development Bridge desktop-node token" -AsSecureString
    $Bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureToken)
    try {
        $Token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr)
    }
}
if ([string]::IsNullOrWhiteSpace($Token)) { throw "Token is required." }

$env:DEVELOPMENT_BRIDGE_URL = "https://mcp.vigilante.website"
$env:DEVELOPMENT_BRIDGE_NODE_ID = "fusion-workstation"
$env:DEVELOPMENT_BRIDGE_DESKTOP_NODE_TOKEN = $Token
$env:FUSION_MCP_URL = "http://127.0.0.1:27182/mcp"
$env:PYTHONUNBUFFERED = "1"

$LogDir = Join-Path $env:LOCALAPPDATA "DevelopmentBridgeFusion"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogPath = Join-Path $LogDir "relay.log"

Write-Host ""
Write-Host "Starting resilient Fusion relay."
Write-Host "Normal connected message: Connected: Fusion MCP tools discovered: 4"
Write-Host "Temporary Bridge/Fusion/network failures are retried automatically."
Write-Host "Log: $LogPath"
Write-Host ""

Start-Transcript -Path $LogPath -Append | Out-Null
try {
    & $Python $Agent
} finally {
    Stop-Transcript | Out-Null
    Remove-Item Env:DEVELOPMENT_BRIDGE_DESKTOP_NODE_TOKEN -ErrorAction SilentlyContinue
}
