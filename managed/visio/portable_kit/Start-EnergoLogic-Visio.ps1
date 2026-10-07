param([string]$Document = "")

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProgId = "EnergoLogic.VisioEditorAddinV364"
$Version = "0.3.64"
$StencilsRoot = Join-Path $env:LOCALAPPDATA "EnergoLogic\Stencils"

function Get-VisioApplication {
    try { return [Runtime.InteropServices.Marshal]::GetActiveObject("Visio.Application") }
    catch {}

    $ProgramFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    $candidates = @()
    try {
        $command = Get-Command VISIO.EXE -ErrorAction Stop
        $candidates += $command.Source
    } catch {}

    foreach ($root in @($env:ProgramFiles, $ProgramFilesX86)) {
        if ([string]::IsNullOrWhiteSpace($root)) { continue }
        foreach ($office in @("Office16","Office15","Office14")) {
            $candidates += (Join-Path $root ("Microsoft Office\root\" + $office + "\VISIO.EXE"))
            $candidates += (Join-Path $root ("Microsoft Office\" + $office + "\VISIO.EXE"))
        }
    }

    $visioExe = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if (-not $visioExe) { throw "Microsoft Visio не найден. Установите Visio 2010 или новее." }

    Start-Process -FilePath $visioExe | Out-Null
    for ($i = 0; $i -lt 80; $i++) {
        Start-Sleep -Milliseconds 250
        try { return [Runtime.InteropServices.Marshal]::GetActiveObject("Visio.Application") }
        catch {}
    }
    throw "Visio запущен, но COM Visio.Application не появился за 20 секунд."
}

$app = Get-VisioApplication
$app.Visible = $true
$app.COMAddIns.Update()
$addin = $app.COMAddIns.Item($ProgId)
if (-not [bool]$addin.Connect) { $addin.Connect = $true }
if (-not [bool]$addin.Connect) { throw "Visio видит $ProgId, но не подключил его." }

# Microsoft Visio: visOpenRO=2 + visOpenDocked=4.
if (Test-Path -LiteralPath $StencilsRoot) {
    foreach ($file in Get-ChildItem -LiteralPath $StencilsRoot -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -match '^\.vss(x|m)?$' }) {
        $alreadyOpen = $false
        for ($i = 1; $i -le [int]$app.Documents.Count; $i++) {
            try {
                $doc = $app.Documents.Item($i)
                if ([string]::Equals([string]$doc.FullName, $file.FullName, [StringComparison]::OrdinalIgnoreCase)) {
                    $alreadyOpen = $true
                    break
                }
            } catch {}
        }
        if (-not $alreadyOpen) { [void]$app.Documents.OpenEx($file.FullName, 6) }
    }
}

if (-not [string]::IsNullOrWhiteSpace($Document)) {
    $full = [IO.Path]::GetFullPath($Document)
    if (-not (Test-Path -LiteralPath $full)) { throw "Файл схемы не найден: $full" }
    [void]$app.Documents.Open($full)
}

Write-Host "EnergoLogic Editor $Version подключён к Visio." -ForegroundColor Green
Write-Host "Трафареты: $StencilsRoot"
