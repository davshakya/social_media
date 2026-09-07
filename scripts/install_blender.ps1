$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$blenderRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../.tools'))
$blenderVersion = '4.5.3'
$blenderName = "blender-$blenderVersion-windows-x64.zip"
$blenderArchive = Join-Path $blenderRoot $blenderName
$blenderBase = 'https://download.blender.org/release/Blender4.5/'
New-Item -ItemType Directory -Path $blenderRoot -Force | Out-Null
$blenderChecksums = Join-Path $blenderRoot "blender-$blenderVersion.sha256"
Invoke-WebRequest -UseBasicParsing -Uri "${blenderBase}blender-$blenderVersion.sha256" -OutFile $blenderChecksums
if (-not (Test-Path -LiteralPath $blenderArchive)) {
    Write-Output "Downloading portable Blender $blenderVersion..."
    Invoke-WebRequest -UseBasicParsing -Uri "${blenderBase}${blenderName}" -OutFile "$blenderArchive.part"
    Move-Item -LiteralPath "$blenderArchive.part" -Destination $blenderArchive
}
$blenderActual = (Get-FileHash -Algorithm SHA256 -LiteralPath $blenderArchive).Hash.ToLower()
$blenderExpected = ((Get-Content -LiteralPath $blenderChecksums | Select-String -SimpleMatch $blenderName).Line -split '\s+')[0]
if ($blenderActual -ne $blenderExpected) { throw 'Blender SHA-256 mismatch. Remove the downloaded ZIP and retry.' }
Write-Output 'Blender SHA-256 verified.'
$blenderTarget = Join-Path $blenderRoot "blender-$blenderVersion-windows-x64"
$blenderMarker = Join-Path $blenderTarget '.science-video-install-complete'
if (-not (Test-Path -LiteralPath $blenderMarker)) {
    $blenderExe = Join-Path $blenderTarget 'blender.exe'
    $activeBlender = Get-Process -Name blender -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $blenderExe }
    if ($activeBlender) { throw 'This portable Blender is rendering. Wait for the render to finish before running the installer.' }
}
