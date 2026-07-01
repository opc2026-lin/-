$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "Load Forecast Manual Runner v4.3.1"
Write-Host ""
Write-Host "Select mode:"
Write-Host "  1. all"
Write-Host "  2. train"
Write-Host "  3. predict"
Write-Host "  4. validate"
Write-Host "  5. verify"

$modeChoice = Read-Host "Enter number"
$modeMap = @{
    "1" = "all"
    "2" = "train"
    "3" = "predict"
    "4" = "validate"
    "5" = "verify"
}

if (-not $modeMap.ContainsKey($modeChoice)) {
    Write-Host "Invalid mode."
    Read-Host "Press Enter to exit"
    exit 1
}

$mode = $modeMap[$modeChoice]
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
    & py -3 "$scriptDir\05_auto_run_v4_3_1.py" --mode $mode
} else {
    & python "$scriptDir\05_auto_run_v4_3_1.py" --mode $mode
}

Read-Host "Press Enter to exit"

