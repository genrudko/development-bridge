param(
    [string]$Source = "",
    [string]$Destination = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$KitRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($Destination)) {
    $Destination = Join-Path $KitRoot "stencils"
}
New-Item -ItemType Directory -Force -Path $Destination | Out-Null

$candidates = @()
if (-not [string]::IsNullOrWhiteSpace($Source)) {
    $candidates += $Source
} else {
    foreach ($oneDriveVar in @("OneDrive","OneDriveConsumer","OneDriveCommercial")) {
        $value = [Environment]::GetEnvironmentVariable($oneDriveVar)
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            $documents = Join-Path $value "Documents"
            $myShapes = Join-Path $documents "Мои фигуры"
            $candidates += (Join-Path $myShapes "ГОСТ")
        }
    }
    $homeOneDrive = Join-Path $HOME "OneDrive"
    $homeOneDriveDocuments = Join-Path $homeOneDrive "Documents"
    $homeOneDriveShapes = Join-Path $homeOneDriveDocuments "Мои фигуры"
    $candidates += (Join-Path $homeOneDriveShapes "ГОСТ")

    $homeDocuments = Join-Path $HOME "Documents"
    $homeShapes = Join-Path $homeDocuments "Мои фигуры"
    $candidates += (Join-Path $homeShapes "ГОСТ")
}

$copied = @()
foreach ($candidate in @($candidates | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Container)) { continue }
    Get-ChildItem -LiteralPath $candidate -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Extension -match '^.(vss|vssx|vssm)$' -and
            $_.FullName -notmatch '\ProgramData\' -and
            $_.FullName -notmatch '\VTD\'
        } |
        ForEach-Object {
            $target = Join-Path $Destination $_.Name
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
            $copied += $_.FullName
        }
}

if ($copied.Count -eq 0) {
    Write-Warning "Личные ГОСТ-трафареты не найдены. Папка stencils оставлена пустой."
} else {
    Write-Host ("Скопировано личных трафаретов: " + $copied.Count) -ForegroundColor Green
    $copied | ForEach-Object { Write-Host ("  " + $_) }
}
