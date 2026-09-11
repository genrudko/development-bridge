$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ManagedRoot = Join-Path $env:LOCALAPPDATA "DevelopmentBridgeFusion"
$Sidecar = Join-Path $ManagedRoot "shimmer-sidecar"
$Pin = "97a06e76c289420a721590ddcab334f5f3dc3178"
$ExtractRoot = Join-Path $Sidecar "extract-$Pin"
$Source = Join-Path $ExtractRoot "self-host-fusion360-MCP-$Pin"
$Archive = Join-Path $Sidecar ("shimmer-" + $Pin + ".zip")
$Venv = Join-Path $Sidecar "venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$FusionExe = Join-Path $Venv "Scripts\fusion-mcp.exe"
$OverlayRoot = Join-Path $Root "fusion_shimmer_overlay"
$ManifestPath = Join-Path $OverlayRoot "manifest.json"
$AddinSource = Join-Path $Source "addin\Fusion360MCP"
$AddinTarget = Join-Path $env:APPDATA "Autodesk\Autodesk Fusion 360\API\AddIns\Fusion360MCP"
$ArchiveUrl = "https://github.com/shimmerjordan/self-host-fusion360-MCP/archive/$Pin.zip"

function Get-Sha256([string] $Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required file is missing: $Path" }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Verify-PinnedInputs {
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) { throw "Bundled Hands overlay manifest is missing: $ManifestPath" }
    $Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Manifest.upstream_sha -ne $Pin) { throw "Bundled Hands manifest pin does not match the qualified Shimmer pin." }
    foreach ($Property in $Manifest.targets.PSObject.Properties) {
        $Target = $Property.Value
        $Path = Join-Path $Source $Target.path
        if ((Get-Sha256 $Path) -ne ([string]$Target.sha256_before).ToLowerInvariant()) {
            throw "Pinned Shimmer source preimage hash mismatch: $($Property.Name)"
        }
    }
    foreach ($Property in $Manifest.overlay_sha256.PSObject.Properties) {
        $Path = Join-Path $OverlayRoot $Property.Name
        if ((Get-Sha256 $Path) -ne ([string]$Property.Value).ToLowerInvariant()) {
            throw "Bundled Hands overlay source hash mismatch: $($Property.Name)"
        }
    }
    return $Manifest
}

function Ensure-PinnedSource {
    if (Test-Path -LiteralPath $Source -PathType Container) { return }
    New-Item -ItemType Directory -Force -Path $Sidecar | Out-Null
    New-Item -ItemType Directory -Force -Path $ExtractRoot | Out-Null
    $TemporaryArchive = $Archive + ".new-" + [Guid]::NewGuid().ToString("N")
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $ArchiveUrl -OutFile $TemporaryArchive
        if (Test-Path -LiteralPath $Archive) { Remove-Item -LiteralPath $Archive -Force }
        Move-Item -LiteralPath $TemporaryArchive -Destination $Archive
        Expand-Archive -LiteralPath $Archive -DestinationPath $ExtractRoot -Force
    } finally {
        Remove-Item -LiteralPath $TemporaryArchive -Force -ErrorAction SilentlyContinue
    }
    if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
        throw "Pinned Shimmer archive did not contain the expected SHA-qualified source directory."
    }
}

function Ensure-QualifiedAddin([object] $Manifest) {
    $OpsRelative = [string]$Manifest.targets.addin_ops_init.path
    $SourceOps = Join-Path $Source $OpsRelative
    $RelativeInsideAddin = $OpsRelative.Substring("addin/Fusion360MCP/".Length).Replace('/', '\')
    $TargetOps = Join-Path $AddinTarget $RelativeInsideAddin
    if (Test-Path -LiteralPath $AddinTarget -PathType Container) {
        if (-not (Test-Path -LiteralPath $TargetOps -PathType Leaf) -or
            (Get-Sha256 $TargetOps) -ne ([string]$Manifest.targets.addin_ops_init.sha256_before).ToLowerInvariant()) {
            throw "refusing to overwrite an existing unqualified Fusion360MCP add-in"
        }
        return
    }
    $Parent = Split-Path -Parent $AddinTarget
    New-Item -ItemType Directory -Force -Path $Parent | Out-Null
    Copy-Item -LiteralPath $AddinSource -Destination $AddinTarget -Recurse
    if ((Get-Sha256 $TargetOps) -ne ([string]$Manifest.targets.addin_ops_init.sha256_before).ToLowerInvariant()) {
        throw "Installed Fusion360MCP add-in preimage verification failed."
    }
}

Ensure-PinnedSource
$Manifest = Verify-PinnedInputs

& py -3.12 --version *> $null
if ($LASTEXITCODE -ne 0) { throw "Python 3.12 not found" }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    & py -3.12 -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Shimmer sidecar venv." }
}
$InstallTarget = $Source + "[http]"
& $Python -m pip install --disable-pip-version-check --upgrade $InstallTarget *> $null
if ($LASTEXITCODE -ne 0) { throw "Could not install the pinned Shimmer sidecar." }
if (-not (Test-Path -LiteralPath $FusionExe -PathType Leaf)) { throw "Pinned Shimmer fusion-mcp.exe is missing after install." }

$ServerTarget = Join-Path $Venv "Lib\site-packages\fusion_mcp\tools\__init__.py"
if ((Get-Sha256 $ServerTarget) -ne ([string]$Manifest.targets.server_tools_init.sha256_before).ToLowerInvariant()) {
    throw "Installed Shimmer server preimage hash mismatch."
}
Ensure-QualifiedAddin $Manifest

# Reuse upstream token generation but do not modify any external MCP-client configuration.
& $Python (Join-Path $Source "install\gen_token.py") *> $null
if ($LASTEXITCODE -ne 0) { throw "Could not initialize the local Shimmer add-in token." }
$SettingsDir = Join-Path $HOME ".fusion-mcp"
$SettingsPath = Join-Path $SettingsDir "addin.json"
if (-not (Test-Path -LiteralPath $SettingsPath -PathType Leaf)) {
    New-Item -ItemType Directory -Force -Path $SettingsDir | Out-Null
    [ordered]@{ port = 9000; bind = "127.0.0.1"; allow_arbitrary_code = $false; request_timeout = 30 } |
        ConvertTo-Json | Set-Content -LiteralPath $SettingsPath -Encoding UTF8
}

Write-Host "Pinned Shimmer Hands runtime installed and preimage-verified."
Write-Host "Shimmer pin: $Pin"
Write-Host "The Fusion Bridge GUI will apply and verify the guarded overlay before starting fusion-hands."
