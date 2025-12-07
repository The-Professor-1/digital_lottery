# Scale up to peak capacity (4 machines) during high traffic hours
# Usage: .\scale-scripts\scale-up-peak.ps1

Write-Host "Scaling up to peak capacity (4 machines)..." -ForegroundColor Green
fly scale count 4 -y --app markos-bingo
Write-Host "✅ Scaled to 4 machines for peak hours" -ForegroundColor Green

