$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found at $python. Set up backend/.venv first."
}

function Start-LocalService([int]$port, [string]$workingDirectory, [string[]]$arguments, [string]$name) {
    if (Test-NetConnection -ComputerName 127.0.0.1 -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue) {
        Write-Host "$name already running on http://127.0.0.1:$port"
        return
    }

    $stdout = Join-Path $root "$name.stdout.log"
    $stderr = Join-Path $root "$name.stderr.log"
    Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $workingDirectory `
        -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr | Out-Null
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        if (Test-NetConnection -ComputerName 127.0.0.1 -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue) {
            Write-Host "$name started on http://127.0.0.1:$port"
            return
        }
    }
    throw "$name failed to start. Check $stderr"
}

Start-LocalService 5500 $root @('-m', 'http.server', '5500', '--bind', '127.0.0.1') 'website'
Start-LocalService 8001 (Join-Path $root 'pretrained 2') @('-m', 'uvicorn', 'app:app', '--host', '127.0.0.1', '--port', '8001') 'analyzer'
Start-LocalService 8002 (Join-Path $root 'backend') @('-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8002') 'backend'
Write-Host 'Open http://127.0.0.1:5500/ in your browser.'
