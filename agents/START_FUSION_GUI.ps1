$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$PythonW = Join-Path $Venv "Scripts\pythonw.exe"
$Gui = Join-Path $Root "fusion_relay_gui.pyw"

Add-Type -AssemblyName System.Windows.Forms
try {
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
    Start-Process -FilePath $PythonW -ArgumentList ('"' + $Gui + '"') -WorkingDirectory $Root
} catch {
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, "Fusion Bridge", 'OK', 'Error') | Out-Null
    exit 1
}
