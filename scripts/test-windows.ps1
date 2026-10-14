param([string]$SourceRoot="")
$ErrorActionPreference = 'Stop'
$root = if ($SourceRoot) { (Resolve-Path $SourceRoot).Path } else { Split-Path $PSScriptRoot -Parent }
$payload = Join-Path $root 'build\payload'
$evidence = Join-Path $root 'build\evidence'
New-Item -ItemType Directory $evidence -Force | Out-Null
function Run-App($exe, $arguments) {
    Write-Output "RUN: $arguments"
    $p = Start-Process -FilePath $exe -ArgumentList $arguments -PassThru
    if (!$p.WaitForExit(180000)) {
        Stop-Process -Id $p.Id -Force
        Get-ChildItem $payload -Recurse -Filter '*error*.txt' | ForEach-Object { Get-Content $_.FullName }
        throw "Application timed out: $arguments"
    }
    $p.Refresh()
    Write-Output "EXIT: $($p.ExitCode)"
    if ($p.ExitCode -ne 0) { throw "Application failed ($($p.ExitCode)): $arguments" }
}
$app = Join-Path $payload 'app\Zapret2Manager.exe'
Run-App $app '--configure-package'
# Keep every attempt: Cygwin initialization and the old process-enumeration
# check can race on hosted runners. Other failures are never retried.
function Run-Suite($suiteApp, $suiteSwitch, $report) {
for ($attempt = 1; $attempt -le 3; $attempt++) {
    try {
        Run-App $suiteApp "$suiteSwitch `"$report`""
        break
    } catch {
        if (!(Test-Path $report)) { throw }
        Copy-Item $report ($report -replace '\.txt$', "-attempt-$attempt.txt")
        $text = Get-Content $report -Raw
        $failLines = @($text -split "`n" | Where-Object { $_ -match '^FAIL:' })
        $knownTransient = $failLines.Count -eq 1 -and ($failLines[0] -match 'cancelled curl process cleaned up|exit=-1073741502')
        if (!$knownTransient -or $attempt -eq 3) { throw }
        Write-Output "Retrying known runner race; original evidence retained (attempt $attempt)."
        Start-Sleep -Seconds 2
    }
}
}
Run-Suite $app '--self-test' "$evidence\self-test.txt"
New-Item -ItemType Directory "$payload\app\tests" -Force | Out-Null
Run-App $app '--ui-test'
Copy-Item "$payload\app\tests\*" $evidence -Force
foreach ($report in @('self-test.txt', 'ui-test.txt', 'tray-test.txt')) {
    $text = Get-Content (Join-Path $evidence $report) -Raw
    if ($text -match '(?m)^FAIL:' -or $text -notmatch 'PASS') { throw "Failed report: $report`n$text" }
}
Run-App $app '--test-package-service'
Copy-Item "$payload\package-service-test.txt" $evidence
$target = Join-Path $env:RUNNER_TEMP 'zapret2-installer-test'
$installer = (Get-ChildItem "$root\dist\Zapret2Manager-Setup-*-x64.exe" | Select-Object -First 1).FullName
$p = Start-Process $installer -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /TESTMODE=1 /DIR=`"$target`" /LOG=`"$evidence\install.log`"" -Wait -PassThru
if ($p.ExitCode -ne 0) { throw "Installer failed: $($p.ExitCode)" }
Run-Suite "$target\app\Zapret2Manager.exe" '--package-check' "$evidence\installed-check.txt"
$uninstaller = Get-ChildItem "$target\uninstall\unins*.exe" | Select-Object -First 1
$p = Start-Process $uninstaller.FullName -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART' -Wait -PassThru
if ($p.ExitCode -ne 0) { throw "Uninstaller failed: $($p.ExitCode)" }
'PASS: isolated install, installed configuration checks and uninstall' | Set-Content "$evidence\installer-test.txt"
