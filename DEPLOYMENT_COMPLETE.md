# Container App Deployment - Complete! ✅

## What's Been Set Up

### ✅ Infrastructure
- **Container Apps Environment**: `futureofthejobsearch-env`
- **Container App**: `futureofthejobsearchai`
- **ACR**: `futureofthejobsearchacr.azurecr.io`
- **Storage Queue**: `embedding-requests`

### ✅ Configuration
- **CPU**: 0.5 vCPU per instance
- **Memory**: 1 GiB per instance
- **Scaling**: 0 to 5 replicas (auto-scales based on queue depth)
- **Scaling Rule**: 10 messages in queue = 1 replica
- **Authentication**: Managed Identity with Storage Queue Data Contributor + Storage Blob Data Owner roles

### ✅ Cost Optimization
- **$0/month when idle** (scales to 0 replicas)
- **~$0.05/hour per active replica** (only when processing)
- No cold start delays after first run (model cached in container)

## How to Test

### 1. Send a Test Message to the Queue

```powershell
# Using Azure CLI
az storage message put `
  --queue-name embedding-requests `
  --content '{"entityType":"Candidate","entityId":"1"}' `
  --account-name futureofthejobsearcb26e `
  --auth-mode login
```

### 2. Monitor the Container App

```powershell
# View logs
az containerapp logs show `
  --name futureofthejobsearchai `
  --resource-group futureofthejobsearch `
  --follow

# Check replica count
az containerapp replica list `
  --name futureofthejobsearchai `
  --resource-group futureofthejobsearch `
  --output table
```

### 3. Check the Database

After the message is processed (30-60 seconds for first run, 2-3 seconds after), check the database:

```sql
SELECT TOP 10 * 
FROM dbo.SeekerEmbeddings 
ORDER BY CreatedAt DESC
```

## Expected Behavior

| Event | Timeline | What Happens |
|-------|----------|--------------|
| Message sent to queue | 0s | Queue depth = 1 |
| Container App scales up | ~10-15s | 1 replica starts |
| First execution | ~30-60s | Model downloads from HuggingFace |
| Embedding saved | ~60-90s total | Record appears in database |
| Queue empty | After processing | Container scales to 0 after cooldown (~5 min) |
| Subsequent messages | 2-3s | Fast (model already cached) |

## GitHub Actions Integration

Every push to `main` branch:
1. Builds Docker container
2. Pushes to ACR with tags: `latest` and `{commit-sha}`
3. Container App automatically pulls latest image

## Monitoring & Troubleshooting

### View Application Insights
```powershell
# Get the Application Insights connection string
az containerapp show `
  --name futureofthejobsearchai `
  --resource-group futureofthejobsearch `
  --query "properties.configuration.activeRevisionsMode"
```

### Check Queue Depth
```powershell
az storage queue show `
  --name embedding-requests `
  --account-name futureofthejobsearcb26e `
  --auth-mode login `
  --query "metadata.ApproximateMessageCount"
```

### View Poison Queue (Failed Messages)
```powershell
az storage message list `
  --queue-name embedding-requests-poison `
  --account-name futureofthejobsearcb26e `
  --auth-mode login
```

## Next Steps

1. **Test with a real candidate/position** from your database
2. **Monitor costs** in Azure Portal
3. **Set up alerts** for failed messages
4. **Consider adding**:
   - Dead letter queue monitoring
   - Batch processing (process multiple messages per execution)
   - Priority queues (high-priority vs normal)

## Architecture Diagram

```
[Your Application] 
    ↓ (sends JSON message)
[Azure Storage Queue: embedding-requests]
    ↓ (triggers via queue depth)
[Container App: 0-5 replicas]
    ↓ (reads entity from DB)
[Azure SQL Database]
    ↓ (generates embedding)
[HuggingFace Model Cache]
    ↓ (saves result)
[Azure SQL: SeekerEmbeddings / PositionEmbeddings]
```

## Files Reference
- `function_app.py` - Queue trigger function
- `Dockerfile` - Container definition
- `QUEUE_USAGE.md` - Detailed usage examples
- `.github/workflows/main_futureofthejobsearchai.yml` - CI/CD pipeline
