# Build pydup_core with MSVC x64 environment and install wheel via pip
param(
    [switch]$Release = $true
)

$ErrorActionPreference = "Stop"

$vcvars = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if (-not (Test-Path $vcvars)) {
    Write-Error "vcvars64.bat not found at $vcvars"
}

$env:PYO3_USE_ABI3_FORWARD_COMPATIBILITY = "1"

$rustDir = Join-Path $PSScriptRoot "..\rust\pydup_core"
$rustDir = (Resolve-Path $rustDir).Path

$flag = if ($Release) { "--release" } else { "" }
$cmd = "call `"$vcvars`" && cd /d `"$rustDir`" && maturin build $flag"

Write-Host "Building pydup_core wheel (Release=$Release)..." -ForegroundColor Cyan
cmd.exe /c $cmd

if ($LASTEXITCODE -ne 0) {
    Write-Error "maturin build failed with exit code $LASTEXITCODE"
}

# Locate newly built wheel
$wheelsDir = Join-Path $rustDir "target\wheels"
$wheel = Get-ChildItem -Path $wheelsDir -Filter "*.whl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if (-not $wheel) {
    Write-Error "No wheel found in $wheelsDir"
}

Write-Host "Installing wheel: $($wheel.FullName)..." -ForegroundColor Cyan
python -m pip install --no-deps --force-reinstall $wheel.FullName

if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed with exit code $LASTEXITCODE"
}

Write-Host "pydup_core built and installed successfully!" -ForegroundColor Green
