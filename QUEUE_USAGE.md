# Queue-Based Embedding Service - Usage Guide

## Architecture

This service uses **Azure Storage Queues** to trigger embedding generation, enabling:
- ✅ **Cost-effective scaling**: Scales from 0 to 5 replicas based on queue depth
- ✅ **No frontend waiting**: Async processing
- ✅ **Automatic retries**: Failed messages retry up to 3 times
- ✅ **0.5 vCPU, 1-2 GiB RAM** per instance

## How to Send Embedding Requests

### Using Azure CLI

```bash
# Send a message to generate a candidate embedding
az storage message put \
  --queue-name embedding-requests \
  --content '{"entityType":"Candidate","entityId":"123"}' \
  --account-name futureofthejobsearcb26e \
  --auth-mode login

# Send a message to generate a position embedding
az storage message put \
  --queue-name embedding-requests \
  --content '{"entityType":"Position","entityId":"456"}' \
  --account-name futureofthejobsearcb26e \
  --auth-mode login
```

### Using PowerShell

```powershell
# Get storage context
$ctx = New-AzStorageContext -StorageAccountName "futureofthejobsearcb26e" -UseConnectedAccount

# Send candidate embedding request
$message = @{
    entityType = "Candidate"
    entityId = "123"
} | ConvertTo-Json

New-AzStorageQueue -Name "embedding-requests" -Context $ctx -ErrorAction SilentlyContinue
$queue = Get-AzStorageQueue -Name "embedding-requests" -Context $ctx
$queue.CloudQueue.AddMessageAsync($message)

# Send position embedding request
$message = @{
    entityType = "Position"
    entityId = "456"
} | ConvertTo-Json
$queue.CloudQueue.AddMessageAsync($message)
```

### Using Python SDK

```python
from azure.storage.queue import QueueClient
from azure.identity import DefaultAzureCredential
import json

# Create queue client
credential = DefaultAzureCredential()
queue_client = QueueClient(
    account_url="https://futureofthejobsearcb26e.queue.core.windows.net",
    queue_name="embedding-requests",
    credential=credential
)

# Send candidate embedding request
message = {
    "entityType": "Candidate",
    "entityId": "123"
}
queue_client.send_message(json.dumps(message))

# Send position embedding request
message = {
    "entityType": "Position",
    "entityId": "456"
}
queue_client.send_message(json.dumps(message))
```

### Using C# / .NET

```csharp
using Azure.Storage.Queues;
using Azure.Identity;
using System.Text.Json;

var credential = new DefaultAzureCredential();
var queueClient = new QueueClient(
    new Uri("https://futureofthejobsearcb26e.queue.core.windows.net/embedding-requests"),
    credential
);

// Create queue if it doesn't exist
await queueClient.CreateIfNotExistsAsync();

// Send candidate embedding request
var message = new { entityType = "Candidate", entityId = "123" };
await queueClient.SendMessageAsync(JsonSerializer.Serialize(message));

// Send position embedding request
var posMessage = new { entityType = "Position", entityId = "456" };
await queueClient.SendMessageAsync(JsonSerializer.Serialize(posMessage));
```

## Message Format

**Required Fields:**
```json
{
  "entityType": "Candidate" or "Position",
  "entityId": "123"
}
```

**Validation:**
- `entityType` must be exactly "Candidate" or "Position" (case-sensitive)
- `entityId` must be a positive integer

## Monitoring

### Check Queue Depth
```bash
az storage queue show \
  --name embedding-requests \
  --account-name futureofthejobsearcb26e \
  --auth-mode login \
  --query "metadata.ApproximateMessageCount"
```

### View Logs
```bash
az containerapp logs show \
  --name futureofthejobsearchai \
  --resource-group futureofthejobsearch \
  --follow
```

## Error Handling

- **Invalid JSON**: Message moved to poison queue after 1 attempt
- **Invalid entityType/entityId**: Message moved to poison queue after 1 attempt  
- **Database/Model errors**: Message retries up to 3 times, then moved to poison queue

Poison queue name: `embedding-requests-poison`

## Scaling Behavior

| Queue Depth | Active Replicas | Avg Processing Time |
|-------------|-----------------|---------------------|
| 0           | 0 (scaled down) | N/A                 |
| 1-5         | 1               | ~30s (first run)    |
| 6-10        | 2               | ~3s (cached model)  |
| 11-20       | 3-5             | ~3s (cached model)  |

**Cold start**: First execution takes ~30-60 seconds (model download)  
**Warm execution**: Subsequent executions take ~2-3 seconds
