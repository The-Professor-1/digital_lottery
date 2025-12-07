# Complete Fly.io Deployment Script
# Usage: .\deploy-to-fly.ps1 -TelegramBotToken "YOUR_BOT_TOKEN"

param(
    [Parameter(Mandatory=$true)]
    [string]$TelegramBotToken
)

$AppName = "markos-bingo"
$PostgresClusterId = "w76geopwkgnrplk4"
$WebAppUrl = "https://${AppName}.fly.dev"

Write-Host "🚀 Starting deployment for $AppName" -ForegroundColor Green
Write-Host "Web App URL will be: $WebAppUrl" -ForegroundColor Cyan

# Generate secrets
$SecretKey = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 50 | ForEach-Object {[char]$_})
$JwtSecretKey = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 50 | ForEach-Object {[char]$_})

Write-Host "`n✅ Generated SECRET_KEY and JWT_SECRET_KEY" -ForegroundColor Green

# Step 1: Attach Managed Postgres
Write-Host "`n📦 Step 1: Attaching Managed Postgres cluster..." -ForegroundColor Cyan
Write-Host "Please select 'fly-user' when prompted" -ForegroundColor Yellow
fly mpg attach --app $AppName $PostgresClusterId

# Step 2: Create Redis
Write-Host "`n📦 Step 2: Creating Redis instance..." -ForegroundColor Cyan
$RedisName = "${AppName}-redis"
fly redis create --name $RedisName --region iad --yes 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Redis created: $RedisName" -ForegroundColor Green
} else {
    Write-Host "⚠️  Redis might already exist, continuing..." -ForegroundColor Yellow
}

# Attach Redis
fly redis attach --app $AppName $RedisName --yes
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Redis attached" -ForegroundColor Green
}

# Step 3: Set secrets
Write-Host "`n🔐 Step 3: Setting environment variables..." -ForegroundColor Cyan
fly secrets set --app $AppName `
    SECRET_KEY=$SecretKey `
    JWT_SECRET_KEY=$JwtSecretKey `
    DEBUG=False `
    TELEGRAM_BOT_TOKEN=$TelegramBotToken `
    TELEGRAM_WEB_APP_URL=$WebAppUrl `
    ALLOWED_HOSTS="$AppName.fly.dev,web.telegram.org" `
    CORS_ALLOWED_ORIGINS="$WebAppUrl,https://web.telegram.org"

Write-Host "✅ Secrets set" -ForegroundColor Green

# Step 4: Deploy
Write-Host "`n🚀 Step 4: Deploying application..." -ForegroundColor Cyan
fly deploy --app $AppName

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Deployment successful!" -ForegroundColor Green
} else {
    Write-Host "❌ Deployment failed. Check logs with: fly logs --app $AppName" -ForegroundColor Red
    exit 1
}

# Step 5: Run migrations
Write-Host "`n📊 Step 5: Running database migrations..." -ForegroundColor Cyan
fly ssh console --app $AppName -C "python manage.py migrate --noinput"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Migrations completed" -ForegroundColor Green
} else {
    Write-Host "⚠️  Migration failed. Run manually: fly ssh console --app $AppName -C 'python manage.py migrate'" -ForegroundColor Yellow
}

# Step 6: Create superuser (optional)
Write-Host "`n👤 Step 6: Create superuser (optional)..." -ForegroundColor Cyan
Write-Host "To create a superuser, run:" -ForegroundColor Yellow
Write-Host "  fly ssh console --app $AppName -C 'python manage.py createsuperuser'" -ForegroundColor White

# Step 7: Start bot
Write-Host "`n🤖 Step 7: Starting Telegram bot..." -ForegroundColor Cyan
Write-Host "The bot can be started with:" -ForegroundColor Yellow
Write-Host "  fly ssh console --app $AppName -C 'python manage.py runbot'" -ForegroundColor White
Write-Host "Or set up as a separate worker process." -ForegroundColor Yellow

Write-Host "`n" -NoNewline
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "✅ DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "`nYour app is live at: " -NoNewline
Write-Host $WebAppUrl -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "1. Update Telegram bot web app URL:" -ForegroundColor Yellow
Write-Host "   - Go to @BotFather on Telegram" -ForegroundColor White
Write-Host "   - Use /mybots → Select your bot → Bot Settings → Menu Button" -ForegroundColor White
Write-Host "   - Set URL to: $WebAppUrl" -ForegroundColor White
Write-Host "`n2. Test your bot and web app" -ForegroundColor Yellow
Write-Host "`n3. View logs: fly logs --app $AppName" -ForegroundColor Yellow
Write-Host "`n4. Set up bot as worker (recommended for production)" -ForegroundColor Yellow

