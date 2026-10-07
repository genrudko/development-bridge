param([switch]$KeepStencils)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (Get-Process VISIO -ErrorAction SilentlyContinue) {
    throw "Перед удалением полностью закройте Microsoft Visio."
}

function Registry-Views {
    if ([Environment]::Is64BitOperatingSystem) {
        return @([Microsoft.Win32.RegistryView]::Registry64,[Microsoft.Win32.RegistryView]::Registry32)
    }
    return @([Microsoft.Win32.RegistryView]::Registry32)
}
function Open-Hkcu([Microsoft.Win32.RegistryView]$View) {
    return [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser,$View)
}
function Read-Default([Microsoft.Win32.RegistryView]$View,[string]$SubKey) {
    $base=Open-Hkcu $View
    try {
        $key=$base.OpenSubKey($SubKey)
        if(-not $key){return $null}
        try{return [string]$key.GetValue("")} finally{$key.Dispose()}
    } finally{$base.Dispose()}
}
function Remove-Tree([Microsoft.Win32.RegistryView]$View,[string]$SubKey) {
    $base=Open-Hkcu $View
    try{try{$base.DeleteSubKeyTree($SubKey,$false)}catch{}}finally{$base.Dispose()}
}

foreach($view in (Registry-Views)){
    $base=Open-Hkcu $view
    try{
        $addins=$base.OpenSubKey("Software\Microsoft\Visio\Addins")
        if($addins){
            try{
                foreach($progid in @($addins.GetSubKeyNames())){
                    if(-not $progid.StartsWith("EnergoLogic.VisioEditorAddinV")){continue}
                    $clsid=Read-Default $view ("Software\Classes\"+$progid+"\CLSID")
                    Remove-Tree $view ("Software\Microsoft\Visio\Addins\"+$progid)
                    Remove-Tree $view ("Software\Classes\"+$progid)
                    if($clsid){Remove-Tree $view ("Software\Classes\CLSID\"+$clsid)}
                }
            }finally{$addins.Dispose()}
        }
    }finally{$base.Dispose()}
    Remove-Tree $view "Software\EnergoLogic\VisioEditor"
}

$EditorRoot=Join-Path $env:LOCALAPPDATA "EnergoLogic\VisioEditor"
if(Test-Path -LiteralPath $EditorRoot){Remove-Item -LiteralPath $EditorRoot -Recurse -Force}
if(-not $KeepStencils){
    $StencilsRoot=Join-Path $env:LOCALAPPDATA "EnergoLogic\Stencils"
    if(Test-Path -LiteralPath $StencilsRoot){Remove-Item -LiteralPath $StencilsRoot -Recurse -Force}
}
$Shortcut=Join-Path ([Environment]::GetFolderPath("Desktop")) "EnergoLogic Visio.lnk"
if(Test-Path -LiteralPath $Shortcut){Remove-Item -LiteralPath $Shortcut -Force}

Write-Host "EnergoLogic Visio Editor удалён." -ForegroundColor Green
