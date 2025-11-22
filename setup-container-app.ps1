# Azure Container App Setup Script for Function App
# Run this script to set up the required Azure resources

# Variables
$RESOURCE_GROUP = "futureofthejobsearch"
$LOCATION = "centralus"
$ACR_NAME = "futureofthejobsearch"
$FUNCTION_APP_NAME = "futureofthejobsearchai"
$STORAGE_ACCOUNT = "futureofthejobsearcb26e"

Write-Host "Setting up Azure Container Registry and Container-based Function App..." -ForegroundColor Green

# 1. Create Azure Container Registry (if it doesn't exist)
Write-Host "`n1. Creating Azure Container Registry..." -ForegroundColor Yellow
az acr create `
  --resource-group $RESOURCE_GROUP `
  --name $ACR_NAME `
  --sku Basic `
  --admin-enabled true `
  --location $LOCATION

# 2. Get ACR credentials
Write-Host "`n2. Getting ACR credentials..." -ForegroundColor Yellow
$ACR_USERNAME = az acr credential show --name $ACR_NAME --query username --output tsv
$ACR_PASSWORD = az acr credential show --name $ACR_NAME --query "passwords[0].value" --output tsv

Write-Host "ACR Username: $ACR_USERNAME"

# 3. Create or update Function App for containers
Write-Host "`n3. Creating/Updating Function App for container deployment..." -ForegroundColor Yellow

# Option A: If you want to use the existing function app, update it to use containers
Write-Host "Updating existing function app to use containers..." -ForegroundColor Cyan
az functionapp config container set `
  --name $FUNCTION_APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --docker-registry-server-url "https://$ACR_NAME.azurecr.io" `
  --docker-registry-server-user $ACR_USERNAME `
  --docker-registry-server-password $ACR_PASSWORD

# 4. Configure app settings
Write-Host "`n4. Configuring app settings..." -ForegroundColor Yellow
az functionapp config appsettings set `
  --name $FUNCTION_APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --settings `
    "DOCKER_REGISTRY_SERVER_URL=https://$ACR_NAME.azurecr.io" `
    "DOCKER_REGISTRY_SERVER_USERNAME=$ACR_USERNAME" `
    "DOCKER_REGISTRY_SERVER_PASSWORD=$ACR_PASSWORD" `
    "WEBSITES_ENABLE_APP_SERVICE_STORAGE=false" `
    "DOCKER_ENABLE_CI=true"

# 5. Grant GitHub Actions access to ACR
Write-Host "`n5. Setting up GitHub Actions service principal access to ACR..." -ForegroundColor Yellow
$ACR_ID = az acr show --name $ACR_NAME --query id --output tsv
$SP_APP_ID = "8337d9cc-580d-462f-8137-fad1e306c24e"  # Your existing GitHub Actions client ID

az role assignment create `
  --assignee $SP_APP_ID `
  --role "AcrPush" `
  --scope $ACR_ID

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Commit and push your changes (Dockerfile .dockerignore workflow)"
Write-Host "2. GitHub Actions will build and deploy the container"
Write-Host "3. First startup may take 2-3 minutes as the model downloads"
Write-Host ""
$acrServer = "$ACR_NAME.azurecr.io"
Write-Host "ACR Login Server: $acrServer" -ForegroundColor White
