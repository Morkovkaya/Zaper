param([string]$InnoCompiler='', [switch]$SkipInstaller)
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$payload=Join-Path $root 'build\payload'
New-Item -ItemType Directory $payload -Force | Out-Null
Copy-Item "$root\vendor\runtime\*" $payload -Recurse -Force
Copy-Item "$root\LICENSE" "$payload\licenses\Zapret2Manager-MIT.txt" -Force
$app=Join-Path $payload 'app'
New-Item -ItemType Directory $app -Force | Out-Null
$compiler=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if(!(Test-Path $compiler)){throw 'The .NET Framework x64 C# compiler is required.'}
$sources=@(Get-ChildItem "$root\src" -Filter '*.cs' | ForEach-Object {$_.FullName})
& $compiler /nologo /nowarn:4014,0108,1998 /target:winexe /platform:x64 /optimize+ ("/out:$app\Zapret2Manager.exe") ("/win32icon:$root\assets\zaper.ico") /reference:System.Windows.Forms.dll,System.Drawing.dll,System.ServiceProcess.dll,System.Web.Extensions.dll,System.IO.Compression.dll,System.IO.Compression.FileSystem.dll,System.Security.dll,Microsoft.CSharp.dll,System.Net.Http.dll,System.Windows.Forms.DataVisualization.dll $sources
if($LASTEXITCODE){throw 'C# compilation failed'}
Copy-Item "$app\Zapret2Manager.exe" "$app\Zapret2Service.exe" -Force
Copy-Item "$root\src\*.cs" $app -Force
$manifest=[ordered]@{}
$paths=@('winws2.exe','cygwin1.dll','WinDivert.dll','WinDivert64.sys','app\Zapret2Service.exe','files\faceit_legacy_udp.bin')+@(Get-ChildItem "$payload\lua" -File -Recurse | ForEach-Object {$_.FullName.Substring($payload.Length+1)})
foreach($path in $paths){$manifest[$path]=(Get-FileHash -LiteralPath "$payload\$path" -Algorithm SHA256).Hash}
$manifest | ConvertTo-Json | Set-Content "$payload\runtime-sha256.json" -Encoding UTF8
Add-Type -AssemblyName System.IO.Compression.FileSystem
$repair=Join-Path $root 'build\repair'
$buildPrefix=[IO.Path]::GetFullPath((Join-Path $root 'build')).TrimEnd('\')+'\'
if(![IO.Path]::GetFullPath($repair).StartsWith($buildPrefix,[StringComparison]::OrdinalIgnoreCase)){throw 'Invalid repair build directory'}
if(Test-Path -LiteralPath $repair){Remove-Item -LiteralPath $repair -Recurse -Force}
New-Item -ItemType Directory "$repair\app" -Force | Out-Null
Copy-Item "$root\vendor\runtime\*" $repair -Recurse -Force
Copy-Item "$app\Zapret2Service.exe" "$repair\app" -Force
Copy-Item "$payload\runtime-sha256.json" $repair -Force
$archive=Join-Path $app 'repair-runtime.zip'
if(Test-Path -LiteralPath $archive){Remove-Item -LiteralPath $archive}
# ZIP entry names use '/', independently of the build host and .NET Framework.
# Convenience.Repair resolves manifest keys with these standard ZIP separators.
Add-Type -AssemblyName System.IO.Compression
$zip=[IO.Compression.ZipFile]::Open($archive,[IO.Compression.ZipArchiveMode]::Create)
try {
 foreach($file in Get-ChildItem -LiteralPath $repair -File -Recurse){
  $relative=$file.FullName.Substring($repair.Length+1).Replace('\','/')
  [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip,$file.FullName,$relative,[IO.Compression.CompressionLevel]::Optimal) | Out-Null
 }
} finally { $zip.Dispose() }
if(!$SkipInstaller){
 if(!$InnoCompiler){$found=Get-Command ISCC.exe -ErrorAction SilentlyContinue;if($found){$InnoCompiler=$found.Source}}
 if(!$InnoCompiler -or !(Test-Path $InnoCompiler)){throw 'Specify -InnoCompiler with the path to ISCC.exe, or use -SkipInstaller.'}
 New-Item -ItemType Directory "$root\dist" -Force | Out-Null
 & $InnoCompiler /Q "$root\installer\setup.iss"
 if($LASTEXITCODE){throw 'Installer compilation failed'}
}
Write-Output "Application: $app\Zapret2Manager.exe"
if(!$SkipInstaller){Write-Output "Installer: $root\dist\Zapret2Manager-Setup-3.8.1-x64.exe"}
