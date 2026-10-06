param(
    [switch]$CompileOnly,
    [switch]$NoShortcut
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Version = "0.3.49"
$ProgId = "EnergoLogic.VisioEditorAddinV349"
$Clsid = "{7FA902A8-D36C-4ED0-B299-445A538AF349}"
$ClassName = "EnergoLogicVisioEditor.Connect"
$AssemblyName = "EnergoLogic.VisioEditorAddinV349, Version=0.3.49.0, Culture=neutral, PublicKeyToken=null"
$Category = "{62C8FE65-4EBB-45E7-B440-6E39B2CDBF29}"

$KitRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ManifestPath = Join-Path $KitRoot "MANIFEST.json"

if (Test-Path -LiteralPath $ManifestPath) {
    $Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($entry in @($Manifest.files)) {
        $relative = [string]$entry.path
        $candidate = Join-Path $KitRoot $relative
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            throw "Проверка пакета: отсутствует файл $relative"
        }
        $item = Get-Item -LiteralPath $candidate
        if ([int64]$item.Length -ne [int64]$entry.size) {
            throw "Проверка пакета: размер файла $relative не совпадает с MANIFEST.json"
        }
        $actual = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
        $expected = ([string]$entry.sha256).ToLowerInvariant()
        if ($actual -ne $expected) {
            throw "Проверка пакета: SHA-256 файла $relative не совпадает с MANIFEST.json"
        }
    }
    Write-Host "Проверка целостности пакета: OK" -ForegroundColor Green
}

$PayloadRoot = Join-Path $KitRoot "payload"
$SourcePath = Join-Path $PayloadRoot "EnergoLogicVisioEditorAddin.cs"
$HelperSourcePath = Join-Path $PayloadRoot "EnergoLogicTopologyRestoreHelper.cs"

if (-not (Test-Path -LiteralPath $SourcePath)) { throw "Не найден payload: $SourcePath" }
if (-not (Test-Path -LiteralPath $HelperSourcePath)) { throw "Не найден payload: $HelperSourcePath" }

if (-not $CompileOnly -and (Get-Process VISIO -ErrorAction SilentlyContinue)) {
    throw "Перед установкой полностью закройте Microsoft Visio."
}

$InstallRoot = Join-Path $env:LOCALAPPDATA ("EnergoLogic\VisioEditor\" + $Version)
$BinRoot = Join-Path $InstallRoot "bin"
$InstalledPayload = Join-Path $InstallRoot "payload"
$StencilsRoot = Join-Path $env:LOCALAPPDATA "EnergoLogic\Stencils"

New-Item -ItemType Directory -Force -Path $BinRoot, $InstalledPayload | Out-Null
Copy-Item -LiteralPath $SourcePath -Destination (Join-Path $InstalledPayload "EnergoLogicVisioEditorAddin.cs") -Force
Copy-Item -LiteralPath $HelperSourcePath -Destination (Join-Path $InstalledPayload "EnergoLogicTopologyRestoreHelper.cs") -Force

$DllPath = Join-Path $BinRoot "EnergoLogic.VisioEditorAddinV349.dll"
$HelperExePath = Join-Path $BinRoot "EnergoLogic.TopologyRestoreHelper.exe"

function First-ExistingFile([string[]]$Candidates) {
    foreach ($candidate in $Candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        $items = @(Get-ChildItem -Path $candidate -File -ErrorAction SilentlyContinue)
        if ($items.Count -gt 0) { return $items[0].FullName }
    }
    return $null
}

$FrameworkCandidates = @(
    (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319"),
    (Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319")
)
$Framework = $null
foreach ($candidate in $FrameworkCandidates) {
    if (Test-Path -LiteralPath (Join-Path $candidate "csc.exe")) {
        $Framework = $candidate
        break
    }
}
if (-not $Framework) {
    throw ".NET Framework 4.x csc.exe не найден. На Windows 10/11 включите .NET Framework 4.x."
}

$ProgramFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")

$OfficeCandidates = @(
    (Join-Path $env:WINDIR "Microsoft.NET\assembly\GAC_MSIL\Office\*\Office.dll"),
    (Join-Path $env:WINDIR "assembly\GAC_MSIL\Office\*\Office.dll"),
    (Join-Path $env:ProgramFiles "Microsoft Office\root\Office16\ADDINS\PowerPivot Excel Add-in\OFFICE.dll")
)
if ($ProgramFilesX86) {
    $OfficeCandidates += (Join-Path $ProgramFilesX86 "Microsoft Office\root\Office16\ADDINS\PowerPivot Excel Add-in\OFFICE.dll")
}
$OfficeRef = First-ExistingFile $OfficeCandidates
if (-not $OfficeRef) {
    throw "Не найдена Microsoft Office PIA (Office.dll). Установите компоненты .NET/PIA Microsoft Office/Visio."
}

$ExtensibilityCandidates = @(
    (Join-Path $env:WINDIR "Microsoft.NET\assembly\GAC_MSIL\Extensibility\*\Extensibility.dll"),
    (Join-Path $env:WINDIR "assembly\GAC_MSIL\Extensibility\*\Extensibility.dll"),
    (Join-Path $env:WINDIR "Microsoft.NET\assembly\GAC_MSIL\Microsoft.VisualStudio.Interop\*\Microsoft.VisualStudio.Interop.dll"),
    (Join-Path $env:WINDIR "assembly\GAC_MSIL\Microsoft.VisualStudio.Interop\*\Microsoft.VisualStudio.Interop.dll"),
    (Join-Path $env:ProgramFiles "Microsoft Visual Studio\2022\*\Common7\IDE\PublicAssemblies\Microsoft.VisualStudio.Interop.dll")
)
if ($ProgramFilesX86) {
    $ExtensibilityCandidates += (Join-Path $ProgramFilesX86 "Microsoft Visual Studio\2022\*\Common7\IDE\PublicAssemblies\Microsoft.VisualStudio.Interop.dll")
}
$ExtensibilityRef = First-ExistingFile $ExtensibilityCandidates
if (-not $ExtensibilityRef) {
    throw "Не найдена Extensibility/Visual Studio Interop assembly для IDTExtensibility2."
}

$Csc = Join-Path $Framework "csc.exe"
$EditorSource = Join-Path $InstalledPayload "EnergoLogicVisioEditorAddin.cs"
$HelperSource = Join-Path $InstalledPayload "EnergoLogicTopologyRestoreHelper.cs"

$EditorArgs = @(
    "/nologo", "/target:library", "/platform:anycpu", "/optimize+",
    ("/out:" + $DllPath),
    ("/reference:" + $ExtensibilityRef),
    ("/reference:" + $OfficeRef),
    ("/reference:" + (Join-Path $Framework "System.Windows.Forms.dll")),
    ("/reference:" + (Join-Path $Framework "System.Drawing.dll")),
    ("/reference:" + (Join-Path $Framework "Microsoft.CSharp.dll")),
    $EditorSource
)
& $Csc @EditorArgs
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $DllPath)) {
    throw "Не удалось скомпилировать EnergoLogic Visio Editor."
}

$HelperArgs = @(
    "/nologo", "/target:exe", "/platform:anycpu", "/optimize+",
    ("/out:" + $HelperExePath),
    ("/reference:" + (Join-Path $Framework "Microsoft.CSharp.dll")),
    $HelperSource
)
& $Csc @HelperArgs
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $HelperExePath)) {
    throw "Не удалось скомпилировать EnergoLogic topology helper."
}

Copy-Item -LiteralPath $OfficeRef -Destination (Join-Path $BinRoot ([IO.Path]::GetFileName($OfficeRef))) -Force
Copy-Item -LiteralPath $ExtensibilityRef -Destination (Join-Path $BinRoot ([IO.Path]::GetFileName($ExtensibilityRef))) -Force

Write-Host "Компиляция EnergoLogic Editor: OK" -ForegroundColor Green
Write-Host "Office reference: $OfficeRef"
Write-Host "Extensibility reference: $ExtensibilityRef"

if ($CompileOnly) {
    Write-Host "CompileOnly: регистрация COM и установка трафаретов пропущены." -ForegroundColor Yellow
    exit 0
}

function Registry-Views {
    if ([Environment]::Is64BitOperatingSystem) {
        return @(
            [Microsoft.Win32.RegistryView]::Registry64,
            [Microsoft.Win32.RegistryView]::Registry32
        )
    }
    return @([Microsoft.Win32.RegistryView]::Registry32)
}

function Open-Hkcu([Microsoft.Win32.RegistryView]$View) {
    return [Microsoft.Win32.RegistryKey]::OpenBaseKey(
        [Microsoft.Win32.RegistryHive]::CurrentUser, $View
    )
}

function Set-RegString([Microsoft.Win32.RegistryView]$View, [string]$SubKey, [string]$Name, [string]$Value) {
    $base = Open-Hkcu $View
    try {
        $key = $base.CreateSubKey($SubKey)
        try { $key.SetValue($Name, $Value, [Microsoft.Win32.RegistryValueKind]::String) }
        finally { $key.Dispose() }
    } finally { $base.Dispose() }
}

function Set-RegDword([Microsoft.Win32.RegistryView]$View, [string]$SubKey, [string]$Name, [int]$Value) {
    $base = Open-Hkcu $View
    try {
        $key = $base.CreateSubKey($SubKey)
        try { $key.SetValue($Name, $Value, [Microsoft.Win32.RegistryValueKind]::DWord) }
        finally { $key.Dispose() }
    } finally { $base.Dispose() }
}

function Remove-RegTree([Microsoft.Win32.RegistryView]$View, [string]$SubKey) {
    $base = Open-Hkcu $View
    try { try { $base.DeleteSubKeyTree($SubKey, $false) } catch {} }
    finally { $base.Dispose() }
}

function Read-RegDefault([Microsoft.Win32.RegistryView]$View, [string]$SubKey) {
    $base = Open-Hkcu $View
    try {
        $key = $base.OpenSubKey($SubKey)
        if (-not $key) { return $null }
        try { return [string]$key.GetValue("") }
        finally { $key.Dispose() }
    } finally { $base.Dispose() }
}

foreach ($view in (Registry-Views)) {
    $base = Open-Hkcu $view
    try {
        $addins = $base.OpenSubKey("Software\Microsoft\Visio\Addins")
        if ($addins) {
            try {
                foreach ($legacy in @($addins.GetSubKeyNames())) {
                    if ($legacy.StartsWith("EnergoLogic.VisioEditorAddinV") -and $legacy -ne $ProgId) {
                        $legacyClsid = Read-RegDefault $view ("Software\Classes\" + $legacy + "\CLSID")
                        Remove-RegTree $view ("Software\Microsoft\Visio\Addins\" + $legacy)
                        Remove-RegTree $view ("Software\Classes\" + $legacy)
                        if ($legacyClsid) { Remove-RegTree $view ("Software\Classes\CLSID\" + $legacyClsid) }
                    }
                }
            } finally { $addins.Dispose() }
        }
    } finally { $base.Dispose() }
}

$CodeBase = (New-Object System.Uri($DllPath)).AbsoluteUri

foreach ($view in (Registry-Views)) {
    $Classes = "Software\Classes"
    Set-RegString $view ($Classes + "\" + $ProgId) "" "EnergoLogic Visio Editor"
    Set-RegString $view ($Classes + "\" + $ProgId + "\CLSID") "" $Clsid

    $ClsidKey = $Classes + "\CLSID\" + $Clsid
    Set-RegString $view $ClsidKey "" "EnergoLogic Visio Editor"
    Set-RegString $view ($ClsidKey + "\ProgId") "" $ProgId
    Set-RegString $view ($ClsidKey + "\Implemented Categories\" + $Category) "" ""

    $Inproc = $ClsidKey + "\InprocServer32"
    Set-RegString $view $Inproc "" "mscoree.dll"
    Set-RegString $view $Inproc "ThreadingModel" "Both"
    Set-RegString $view $Inproc "Class" $ClassName
    Set-RegString $view $Inproc "Assembly" $AssemblyName
    Set-RegString $view $Inproc "RuntimeVersion" "v4.0.30319"
    Set-RegString $view $Inproc "CodeBase" $CodeBase

    $AddinKey = "Software\Microsoft\Visio\Addins\" + $ProgId
    Set-RegString $view $AddinKey "FriendlyName" "EnergoLogic Visio Editor"
    Set-RegString $view $AddinKey "Description" "EnergoLogic engineering editor tools for Microsoft Visio"
    Set-RegDword $view $AddinKey "LoadBehavior" 0

    $SettingsKey = "Software\EnergoLogic\VisioEditor"
    Set-RegString $view $SettingsKey "Version" $Version
    Set-RegString $view $SettingsKey "ProgId" $ProgId
    Set-RegString $view $SettingsKey "InstallPath" $InstallRoot
    Set-RegString $view $SettingsKey "StencilsPath" $StencilsRoot
}

$KitStencils = Join-Path $KitRoot "stencils"
if (Test-Path -LiteralPath $KitStencils) {
    New-Item -ItemType Directory -Force -Path $StencilsRoot | Out-Null
    Get-ChildItem -LiteralPath $KitStencils -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -match '^\.vss(x|m)?$' } |
        ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $StencilsRoot $_.Name) -Force
        }
}

Copy-Item -LiteralPath (Join-Path $KitRoot "Start-EnergoLogic-Visio.ps1") -Destination $InstallRoot -Force
Copy-Item -LiteralPath (Join-Path $KitRoot "Uninstall-EnergoLogic.ps1") -Destination $InstallRoot -Force

if (-not $NoShortcut) {
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $ShortcutPath = Join-Path $Desktop "EnergoLogic Visio.lnk"
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = (Join-Path $PSHOME "powershell.exe")
    $Shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $InstallRoot "Start-EnergoLogic-Visio.ps1") + '"'
    $Shortcut.WorkingDirectory = $InstallRoot
    $Shortcut.Description = "Microsoft Visio with EnergoLogic Editor"
    $Shortcut.Save()
}

Write-Host ""
Write-Host "EnergoLogic Visio Editor $Version установлен." -ForegroundColor Green
Write-Host "Каталог: $InstallRoot"
Write-Host "Трафареты: $StencilsRoot"
Write-Host "LoadBehavior=0: используйте ярлык 'EnergoLogic Visio' или Start-EnergoLogic-Visio.ps1."
