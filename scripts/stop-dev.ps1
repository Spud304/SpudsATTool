# Kill dev servers left behind after Ctrl+C: listeners on the dev ports plus orphaned uvicorn
# reload workers (spawned via multiprocessing, they outlive the reloader on Windows).
$ports = 8000, 5173
$killed = @()
foreach ($conn in Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in $ports }) {
    if (Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue) {
        taskkill /PID $conn.OwningProcess /T /F | Out-Null
        $killed += $conn.OwningProcess
    }
}
$alive = @(Get-Process | Select-Object -ExpandProperty Id)
foreach ($p in Get-CimInstance Win32_Process -Filter "Name = 'python.exe'") {
    if ($p.CommandLine -match 'multiprocessing\.spawn' -and $alive -notcontains $p.ParentProcessId) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        $killed += $p.ProcessId
    }
}
Start-Sleep -Milliseconds 500
$left = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in $ports }
if ($killed.Count) { "stopped: $($killed -join ', ')" } else { "nothing to stop" }
if ($left) { "still listening:"; $left | Format-Table LocalAddress, LocalPort, OwningProcess -AutoSize } else { "ports $($ports -join ', ') are free" }
