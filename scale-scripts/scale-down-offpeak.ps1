# Scale down to off-peak capacity (2 machines) during low traffic hours
# Usage: .\scale-scripts\scale-down-offpeak.ps1

Write-Host "Scaling down to off-peak capacity (2 machines)..." -ForegroundColor Yellow
fly scale count 2 -y --app markos-bingo
Write-Host "✅ Scaled to 2 machines for off-peak hours" -ForegroundColor Yellow
Write-Host "💰 Estimated savings: ~$12-15/month during off-peak periods" -ForegroundColor Cyan

