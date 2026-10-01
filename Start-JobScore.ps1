$ErrorActionPreference = 'Stop'
$project = $PSScriptRoot
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-Error 'Create the Python environment first. See README.md.'
}
Push-Location -LiteralPath $project
try { & $python 'run.py' } finally { Pop-Location }
