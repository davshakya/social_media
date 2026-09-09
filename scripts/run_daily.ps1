$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
& .\.venv\Scripts\python.exe science_video_generator.py queue daily --fast --resolution 1080 --duration 120
if ($LASTEXITCODE -ne 0) {
    throw "Daily video generation failed with exit code $LASTEXITCODE"
}
