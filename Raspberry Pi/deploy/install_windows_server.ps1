# Start the SmartMat server when Windows starts (scheduled task, runs as the current user, no window).
# Run once from an elevated PowerShell in the "Raspberry Pi" folder:
#   powershell -ExecutionPolicy Bypass -File deploy\install_windows_server.ps1            # from source (pythonw)
#   powershell -ExecutionPolicy Bypass -File deploy\install_windows_server.ps1 -Exe "C:\SmartMat\SmartMatServer\SmartMatServer.exe"
# Remove it again: Unregister-ScheduledTask -TaskName SmartMatServer -Confirm:$false
param(
    [string]$Exe = "",                  # the built SmartMatServer.exe; empty = run the source with pythonw
    [string]$Arguments = "",            # e.g. "--port 8000" or "--demo"
    [string]$TaskName = "SmartMatServer"
)

$folder = Split-Path -Parent $PSScriptRoot   # the "Raspberry Pi" folder
if ($Exe) {
    $action = New-ScheduledTaskAction -Execute $Exe -Argument $Arguments -WorkingDirectory (Split-Path -Parent $Exe)
} else {
    $pythonw = (Get-Command pythonw.exe -ErrorAction Stop).Source
    $action = New-ScheduledTaskAction -Execute $pythonw -Argument "-m server $Arguments".Trim() -WorkingDirectory $folder
}
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
# S4U: runs at startup without anyone logged in, as this user (the data folder is this user's)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "Task '$TaskName' registered and started. Open http://localhost:8000"
