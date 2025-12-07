# Setup Auto-Scaling Scheduled Tasks for Markos Bingo
# This script creates Windows scheduled tasks to automatically scale machines up/down

Write-Host "Setting up auto-scaling scheduled tasks..." -ForegroundColor Cyan

$scriptPath = Join-Path $PSScriptRoot "scale-up-peak.ps1"
$downPath = Join-Path $PSScriptRoot "scale-down-offpeak.ps1"

# Check if scripts exist
if (-not (Test-Path $scriptPath)) {
    Write-Host "Error: scale-up-peak.ps1 not found!" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $downPath)) {
    Write-Host "Error: scale-down-offpeak.ps1 not found!" -ForegroundColor Red
    exit 1
}

# Remove existing tasks if they exist
Get-ScheduledTask -TaskName "BingoScaleUpPeak" -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false
Get-ScheduledTask -TaskName "BingoScaleDownOffpeak" -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false

# Create Scale Up Task (Peak Hours - 8:00 AM UTC = 11:00 AM EAT)
$actionUp = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$scriptPath`""
$triggerUp = New-ScheduledTaskTrigger -Daily -At "11:00AM"
$principalUp = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Highest
$settingsUp = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName "BingoScaleUpPeak" `
    -Action $actionUp `
    -Trigger $triggerUp `
    -Principal $principalUp `
    -Settings $settingsUp `
    -Description "Scale Bingo app to 4 machines for peak hours (11:00 AM EAT daily)"

Write-Host "✅ Created scheduled task: BingoScaleUpPeak (runs daily at 11:00 AM EAT)" -ForegroundColor Green

# Create Scale Down Task (Off-Peak Hours - 2:00 AM UTC = 5:00 AM EAT)
$actionDown = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$downPath`""
$triggerDown = New-ScheduledTaskTrigger -Daily -At "5:00AM"
$principalDown = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Highest
$settingsDown = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName "BingoScaleDownOffpeak" `
    -Action $actionDown `
    -Trigger $triggerDown `
    -Principal $principalDown `
    -Settings $settingsDown `
    -Description "Scale Bingo app to 2 machines for off-peak hours (5:00 AM EAT daily)"

Write-Host "✅ Created scheduled task: BingoScaleDownOffpeak (runs daily at 5:00 AM EAT)" -ForegroundColor Green

Write-Host "`n📋 Auto-scaling setup complete!" -ForegroundColor Cyan
Write-Host "`nScheduled Tasks:" -ForegroundColor Yellow
Write-Host "  - BingoScaleUpPeak: Scales to 4 machines at 11:00 AM EAT (peak hours)" -ForegroundColor White
Write-Host "  - BingoScaleDownOffpeak: Scales to 2 machines at 5:00 AM EAT (off-peak hours)" -ForegroundColor White
Write-Host "`n💡 To view/modify tasks: Open Task Scheduler and search for 'Bingo'" -ForegroundColor Cyan
Write-Host "💰 Estimated monthly savings: ~\$3-4/month" -ForegroundColor Green

