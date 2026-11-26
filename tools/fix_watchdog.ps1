# Fix the KruxoAI Watchdog scheduled task (it never ran: its trigger had a
# 5-minute repetition with NO duration, so it fired once at 11:45 and never
# again) and restart the app, which has been dead since ~15:09.
# Run on the laptop as Faisal (the MCP server runs non-elevated, so this
# must work without admin — scheduled tasks for the current user do).
$taskName = "KruxoAI Watchdog"
$installDir = "C:\Users\Faisal\Downloads\Virtual Ai Assistant"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$installDir\watchdog.ps1`""
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 365)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
Write-Output "TASK RECREATED with 5-min repetition for 365 days, StartWhenAvailable on."
Start-ScheduledTask -TaskName $taskName
Write-Output "WATCHDOG STARTED MANUALLY (it should relaunch the app now)."
Start-Sleep -Seconds 20
Write-Output "--- processes ---"
Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" | Select-Object ProcessId,Name,@{N='Started';E={$_.CreationDate.ToString('HH:mm:ss')}} | Format-Table -AutoSize | Out-String -Width 100
Write-Output ("STATE_AT: " + (Get-Item ($installDir + "\memory\living_state.json")).LastWriteTime.ToString('HH:mm:ss'))
Write-Output "--- watchdog.log ---"
Get-Content ($installDir + "\watchdog.log") -ErrorAction SilentlyContinue
