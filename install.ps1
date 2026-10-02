# Claudon installer for Windows PowerShell (no Python needed):
#   irm https://raw.githubusercontent.com/infenia/claudon/main/install.ps1 | iex
# Pin a release with:  $env:CLAUDON_VERSION = 'vX.Y.Z'  before running. The download is checked against SHA256SUMS.
$ErrorActionPreference = 'Stop'
$ver = if ($env:CLAUDON_VERSION) { $env:CLAUDON_VERSION } else { 'latest' }
$repo = 'https://github.com/infenia/claudon'
$base = if ($ver -eq 'latest') { "$repo/releases/latest/download" } else { "$repo/releases/download/$ver" }
if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { throw 'No native Claudon binary for this architecture; use: pipx install claudon  (or npx @infenia/claudon).' }

$asset = 'claudon-windows-x86_64.exe'
$dir = Join-Path $env:LOCALAPPDATA 'claudon\bin'
New-Item -ItemType Directory -Force $dir | Out-Null
$tmp = Join-Path $dir '.claudon.download'
Write-Host "Downloading Claudon $ver..."
Invoke-WebRequest "$base/$asset" -OutFile $tmp -UseBasicParsing
$sums = (Invoke-WebRequest "$base/SHA256SUMS" -UseBasicParsing).Content -split "`n"
$want = ($sums | Where-Object { $_ -match "[ *]$([regex]::Escape($asset))\s*$" } | Select-Object -First 1) -split '\s+' | Select-Object -First 1
if (-not $want -or $want -ne (Get-FileHash $tmp -Algorithm SHA256).Hash.ToLower()) {
    Remove-Item $tmp -Force
    throw "Checksum verification failed for $asset $ver; nothing was installed."
}
Move-Item $tmp (Join-Path $dir 'claudon.exe') -Force
Write-Host "Successfully installed Claudon to $dir\claudon.exe"
if (($env:Path -split ';') -notcontains $dir) {
    [Environment]::SetEnvironmentVariable('Path', "$([Environment]::GetEnvironmentVariable('Path','User'));$dir", 'User')
    Write-Host "Added $dir to your user PATH; open a new terminal to use 'claudon'."
}
