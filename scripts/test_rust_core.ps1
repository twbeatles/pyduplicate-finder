# Run cargo test and clippy for pydup_core
$ErrorActionPreference = "Stop"

$vcvars = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if (-not (Test-Path $vcvars)) {
    Write-Error "vcvars64.bat not found at $vcvars"
}

$env:PYO3_USE_ABI3_FORWARD_COMPATIBILITY = "1"

$rustDir = Join-Path $PSScriptRoot "..\rust\pydup_core"
$rustDir = (Resolve-Path $rustDir).Path

Write-Host "Running cargo test..." -ForegroundColor Cyan
$testCmd = "call `"$vcvars`" && cd /d `"$rustDir`" && cargo test"
cmd.exe /c $testCmd
if ($LASTEXITCODE -ne 0) {
    Write-Error "cargo test failed!"
}

Write-Host "Running cargo clippy..." -ForegroundColor Cyan
$clippyCmd = "call `"$vcvars`" && cd /d `"$rustDir`" && cargo clippy --all-targets --all-features -- -D warnings"
cmd.exe /c $clippyCmd
if ($LASTEXITCODE -ne 0) {
    Write-Error "cargo clippy failed!"
}

Write-Host "All Rust checks passed!" -ForegroundColor Green
