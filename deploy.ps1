# Fly.io Deployment Script for Markos Bingo
# Run this script after providing the required information

param(
    [Parameter(Mandatory=$true)]
    [string]$AppName,
    
    [Parameter(Mandatory=$true)]
    [string]$TelegramBotToken,
    
    [string]$SecretKey = "",
    [string]$JwtSecretKey = ""
)

Write-Host "Starting deployment for app: $AppName" -ForegroundColor Green

# Generate secrets if not provided
if ([string]::IsNullOrEmpty($SecretKey)) {
    $SecretKey = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 50 | ForEach-Object {[char]$_})
    Write-Host "Generated SECRET_KEY" -ForegroundColor Yellow
}

if ([string]::IsNullOrEmpty($JwtSecretKey)) {
    $JwtSecretKey = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 50 | ForEach-Object {[char]$_})
    Write-Host "Generated JWT_SECRET_KEY" -ForegroundColor Yellow
}

$WebAppUrl = "https://$AppName.fly.dev"

Write-Host "`nStep 1: Creating/updating Fly app..." -ForegroundColor Cyan
fly launch --no-deploy --name $AppName

Write-Host "`nStep 2: Attaching PostgreSQL database..." -ForegroundColor Cyan
fly postgres attach --app $AppName bingo_db

Write-Host "`nStep 3: Creating Redis instance..." -ForegroundColor Cyan
fly redis create --name "$AppName-redis" --region iad
fly redis attach --app $AppName "$AppName-redis"

Write-Host "`nStep 4: Setting environment variables..." -ForegroundColor Cyan
fly secrets set --app $AppName `
    SECRET_KEY=$SecretKey `
    JWT_SECRET_KEY=$JwtSecretKey `
    DEBUG=False `
    TELEGRAM_BOT_TOKEN=$TelegramBotToken `
    TELEGRAM_WEB_APP_URL=$WebAppUrl `
    ALLOWED_HOSTS="$AppName.fly.dev,web.telegram.org" `
    CORS_ALLOWED_ORIGINS="$WebAppUrl,https://web.telegram.org"

Write-Host "`nStep 5: Deploying application..." -ForegroundColor Cyan
fly deploy --app $AppName

Write-Host "`nStep 6: Running migrations..." -ForegroundColor Cyan
fly ssh console --app $AppName -C "python manage.py migrate"

Write-Host "`nStep 7: Creating superuser (if needed)..." -ForegroundColor Cyan
Write-Host "You can create a superuser by running:" -ForegroundColor Yellow
Write-Host "  fly ssh console --app $AppName -C 'python manage.py createsuperuser'" -ForegroundColor Yellow

Write-Host "`nStep 8: Starting Telegram bot..." -ForegroundColor Cyan
Write-Host "The bot can be started with:" -ForegroundColor Yellow
Write-Host "  fly ssh console --app $AppName -C 'python manage.py runbot'" -ForegroundColor Yellow
Write-Host "Or set up a separate worker process." -ForegroundColor Yellow

Write-Host "`n✅ Deployment complete!" -ForegroundColor Green
Write-Host "Your app is available at: $WebAppUrl" -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "1. Update your Telegram bot's web app URL to: $WebAppUrl" -ForegroundColor Yellow
Write-Host "2. Test the bot and web app" -ForegroundColor Yellow
Write-Host "3. Set up the bot as a worker (optional)" -ForegroundColor Yellow

