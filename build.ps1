param([string]$InnoCompiler='', [switch]$SkipInstaller)
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$payload=Join-Path $root 'build\payload'
New-Item -ItemType Directory $payload -Force | Out-Null
Copy-Item "$root\vendor\runtime\*" $payload -Recurse -Force
Copy-Item "$root\LICENSE" "$payload\licenses\Zapret2Manager-MIT.txt" -Force
$app=Join-Path $payload 'app'
if(Test-Path -LiteralPath $app){Remove-Item -LiteralPath $app -Recurse -Force}
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
[IO.Compression.ZipFile]::CreateFromDirectory($repair,$archive,[IO.Compression.CompressionLevel]::Optimal,$false)
$installerPath=Join-Path $root 'dist\Zapret2Manager-Setup-3.8.2-x64.exe'
if(!$SkipInstaller){
 if(!$InnoCompiler){$found=Get-Command ISCC.exe -ErrorAction SilentlyContinue;if($found){$InnoCompiler=$found.Source}}
 New-Item -ItemType Directory "$root\dist" -Force | Out-Null
 if($InnoCompiler -and (Test-Path $InnoCompiler)){
  & $InnoCompiler /Q "$root\installer\setup.iss"
  if($LASTEXITCODE){throw 'Installer compilation failed'}
  Write-Output "Installer: $installerPath"
 }else{
  $stub=Join-Path $root 'build\ZaperSetup.exe'
  & $compiler /nologo /nowarn:4014,0108,1998 /target:winexe /platform:x64 /optimize+ ("/out:$stub") ("/win32icon:$root\assets\zaper.ico") /reference:System.Windows.Forms.dll,System.ServiceProcess.dll,System.Web.Extensions.dll,System.IO.Compression.dll,System.IO.Compression.FileSystem.dll "$root\installer\SelfInstaller.cs"
  if($LASTEXITCODE){throw 'Self-contained installer compilation failed'}
  $zipPath=Join-Path $root 'build\payload.zip'
  if(Test-Path -LiteralPath $zipPath){Remove-Item -LiteralPath $zipPath -Force}
  [IO.Compression.ZipFile]::CreateFromDirectory($payload,$zipPath,[IO.Compression.CompressionLevel]::Optimal,$false)
  Copy-Item $stub $installerPath -Force
  $zipInfo=Get-Item -LiteralPath $zipPath
  $output=New-Object IO.FileStream($installerPath,[IO.FileMode]::Append,[IO.FileAccess]::Write,[IO.FileShare]::None)
  try{$input=New-Object IO.FileStream($zipPath,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read);try{$input.CopyTo($output)}finally{$input.Dispose()};$marker=[BitConverter]::GetBytes($zipInfo.Length);$output.Write($marker,0,8)}finally{$output.Dispose()}
  Write-Output "Installer (self-contained): $installerPath"
 }
}
Write-Output "Application: $app\Zapret2Manager.exe"
