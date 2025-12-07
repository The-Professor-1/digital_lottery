# Script to check which PostgreSQL database is attached and delete the unused one
# Fly CLI location: $env:USERPROFILE\.fly\bin\fly.exe

$FlyPath = "$env:USERPROFILE\.fly\bin\fly.exe"
$AppName = "markos-bingo"

Write-Host "🔍 Checking PostgreSQL databases for app: $AppName" -ForegroundColor Cyan
Write-Host ""

# Check which database is attached by looking at DATABASE_URL
Write-Host "Checking DATABASE_URL from app secrets..." -ForegroundColor Yellow
$secrets = & $FlyPath secrets list --app $AppName
$dbUrlLine = $secrets | Select-String -Pattern "DATABASE_URL"
Write-Host $dbUrlLine
Write-Host ""

Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Based on your configuration files:" -ForegroundColor Green
Write-Host "  ✅ ACTIVE: Cluster 'w76geopwkgnrplk4' (database name: bingo_db)" -ForegroundColor Green
Write-Host "  ❌ UNUSED: markos-bingo-db (should be deleted)" -ForegroundColor Yellow
Write-Host ""

Write-Host "To list all managed PostgreSQL clusters, run:" -ForegroundColor Cyan
Write-Host "  & `"$FlyPath`" mpg list" -ForegroundColor White
Write-Host ""

Write-Host "⚠️  CONFIRMATION REQUIRED" -ForegroundColor Red
Write-Host ""
Write-Host "The script will delete 'markos-bingo-db' database." -ForegroundColor Yellow
Write-Host "This action is PERMANENT and cannot be undone!" -ForegroundColor Red
Write-Host ""
$confirm = Read-Host "Type 'DELETE' to confirm deletion of markos-bingo-db"

if ($confirm -eq "DELETE") {
    Write-Host ""
    Write-Host "🗑️  Deleting markos-bingo-db..." -ForegroundColor Yellow
    
    # Try to delete using the cluster name
    & $FlyPath mpg destroy markos-bingo-db
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "✅ Successfully deleted markos-bingo-db" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "⚠️  If that failed, try with force flag:" -ForegroundColor Yellow
        Write-Host "  & `"$FlyPath`" mpg destroy markos-bingo-db --force" -ForegroundColor White
        Write-Host ""
        Write-Host "Or if it's an unmanaged database:" -ForegroundColor Yellow
        Write-Host "  & `"$FlyPath`" postgres destroy markos-bingo-db" -ForegroundColor White
    }
} else {
    Write-Host ""
    Write-Host "❌ Deletion cancelled." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To delete manually, run one of these:" -ForegroundColor Cyan
    Write-Host "  & `"$FlyPath`" mpg destroy markos-bingo-db" -ForegroundColor White
    Write-Host "  & `"$FlyPath`" postgres destroy markos-bingo-db" -ForegroundColor White
}

