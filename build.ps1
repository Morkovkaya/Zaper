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
& $compiler /nologo /nowarn:4014,0108,1998 /target:winexe /platform:x64 /optimize+ ("/out:$app\Zapret2Manager.exe") /reference:System.Windows.Forms.dll,System.Drawing.dll,System.ServiceProcess.dll,System.Web.Extensions.dll $sources
if($LASTEXITCODE){throw 'C# compilation failed'}
Copy-Item "$app\Zapret2Manager.exe" "$app\Zapret2Service.exe" -Force
Copy-Item "$root\src\*.cs" $app -Force
$manifest=[ordered]@{}
$paths=@('winws2.exe','cygwin1.dll','WinDivert.dll','WinDivert64.sys','app\Zapret2Service.exe','files\faceit_legacy_udp.bin')+@(Get-ChildItem "$payload\lua" -File -Recurse | ForEach-Object {$_.FullName.Substring($payload.Length+1)})
foreach($path in $paths){$manifest[$path]=(Get-FileHash -LiteralPath "$payload\$path" -Algorithm SHA256).Hash}
$manifest | ConvertTo-Json | Set-Content "$payload\runtime-sha256.json" -Encoding UTF8
if(!$SkipInstaller){
 if(!$InnoCompiler){$found=Get-Command ISCC.exe -ErrorAction SilentlyContinue;if($found){$InnoCompiler=$found.Source}}
 if(!$InnoCompiler -or !(Test-Path $InnoCompiler)){throw 'Specify -InnoCompiler with the path to ISCC.exe, or use -SkipInstaller.'}
 New-Item -ItemType Directory "$root\dist" -Force | Out-Null
 & $InnoCompiler /Q "$root\installer\setup.iss"
 if($LASTEXITCODE){throw 'Installer compilation failed'}
}
Write-Output "Application: $app\Zapret2Manager.exe"
if(!$SkipInstaller){Write-Output "Installer: $root\dist\Zapret2Manager-Setup-3.6.3-x64.exe"}
