# Security Configuration Checklist for Azure Function

## Azure Portal Configuration

### 1. Authentication / Authorization
```
Azure Portal → Function App → Authentication
- Enable "Require authentication"
- Identity provider: Microsoft Entra ID (Azure AD)
- Action: Return 401 (for API)
```

### 2. Networking
```
Azure Portal → Function App → Networking
- Enable "Access Restrictions" (IP whitelist)
- Add allowed IP ranges for your backend services
- Enable "Private Endpoints" for production
```

### 3. CORS (if called from web frontend)
```
Azure Portal → Function App → CORS
- Add specific domain: https://yourapp.com
- Remove * (wildcard) if present
```

### 4. Application Settings (Environment Variables)
```
Azure Portal → Function App → Configuration → Application Settings

Required:
- FUNCTIONS_WORKER_RUNTIME = python
- WEBSITE_RUN_FROM_PACKAGE = 1
- SQL_CONNECTION_STRING = [Use Key Vault Reference]

Security:
- USE_MANAGED_IDENTITY = true (for production)
- ENABLE_AUDIT_LOGGING = true
```

### 5. Managed Identity
```
Azure Portal → Function App → Identity
- System assigned: ON
- Grant permissions:
  ✓ SQL Database: "SQL DB Contributor"
  ✓ Key Vault: "Key Vault Secrets User"
```

### 6. Key Vault Integration
```
Store secrets in Azure Key Vault:
- SQL_CONNECTION_STRING
- Function keys (use Key Vault references)

Format in App Settings:
@Microsoft.KeyVault(SecretUri=https://your-vault.vault.azure.net/secrets/sql-connection/)
```

### 7. Monitoring & Alerts
```
Azure Portal → Function App → Monitoring → Alerts
- Create alert: Failed requests > 5 in 5 minutes
- Create alert: Response time > 30 seconds
- Create alert: CPU usage > 80%
```

## Code-Level Security

### ✅ Implemented
- [x] Function-level authentication (requires function key)
- [x] Input validation (entityType whitelist)
- [x] entityId sanitization (numeric validation)
- [x] Parameterized SQL queries (? placeholders)
- [x] Azure AD token authentication for SQL
- [x] Error message sanitization
- [x] Request audit logging (IP + parameters)
- [x] Rate limiting (20 concurrent requests)
- [x] Timeout handling (10 minutes)

### 🔄 Recommended Next Steps
- [ ] Implement request throttling per IP (Azure API Management)
- [ ] Add request signing/HMAC validation
- [ ] Implement idempotency keys
- [ ] Add request size limits
- [ ] Enable DDoS protection (Azure DDoS Protection Standard)
- [ ] Add Web Application Firewall (Azure Front Door)
- [ ] Implement circuit breaker pattern for database
- [ ] Add data encryption at rest (Azure SQL TDE - auto-enabled)
- [ ] Enable diagnostic logs export to Log Analytics

## Cost & Resource Protection

### Current Settings
```json
{
  "maxConcurrentRequests": 20,
  "maxOutstandingRequests": 50,
  "functionTimeout": "00:10:00"
}
```

### Cost Protection
- Set budget alerts in Azure Cost Management
- Enable consumption quotas
- Monitor daily execution count

### Expected Costs (Flex Consumption)
- Free tier: 1 million executions/month
- After free tier: ~$0.20 per million executions
- With 2GB memory: ~$0.0000166 per GB-second

## Compliance

### Data Protection
- All data in transit: HTTPS (enforced)
- Database: Encrypted at rest (TDE enabled by default)
- Logs: Retained in Application Insights (90 days default)

### GDPR Considerations
- Audit trail: ✅ (logs IP and entity accessed)
- Right to deletion: Implement deletion endpoint
- Data minimization: ✅ (only fetches needed fields)

## Security Testing

### Test with:
```bash
# 1. Test without function key (should fail)
curl -X POST https://your-app.azurewebsites.net/api/trigger_embedding

# 2. Test with invalid entityType (should return 400)
curl -X POST https://your-app.azurewebsites.net/api/trigger_embedding?code=KEY \
  -H "Content-Type: application/json" \
  -d '{"entityType": "INVALID", "entityId": "1"}'

# 3. Test with SQL injection attempt (should fail)
curl -X POST https://your-app.azurewebsites.net/api/trigger_embedding?code=KEY \
  -H "Content-Type: application/json" \
  -d '{"entityType": "Candidate", "entityId": "1; DROP TABLE Users--"}'

# 4. Test with negative ID (should return 400)
curl -X POST https://your-app.azurewebsites.net/api/trigger_embedding?code=KEY \
  -H "Content-Type: application/json" \
  -d '{"entityType": "Candidate", "entityId": "-1"}'

# 5. Load test (should throttle after 20 concurrent)
# Use Apache JMeter or Azure Load Testing
```

## Incident Response

### If Compromised
1. Rotate all function keys immediately
2. Rotate SQL credentials
3. Check Application Insights logs for suspicious activity
4. Review Key Vault access logs
5. Check Azure AD sign-in logs
6. Contact Azure support

### Monitoring Queries (Application Insights)
```kusto
// Suspicious activity: Multiple failed auth attempts
requests
| where timestamp > ago(1h)
| where resultCode == 401
| summarize FailedAttempts = count() by client_IP
| where FailedAttempts > 10

// Unusual patterns: High volume from single IP
requests
| where timestamp > ago(1h)
| summarize Requests = count() by client_IP
| where Requests > 100
| order by Requests desc

// Error rate spike
requests
| where timestamp > ago(1h)
| summarize SuccessRate = 100.0 * countif(success == true) / count()
| where SuccessRate < 95
```

## Penetration Testing

Before production:
- Hire security firm for pen test
- Run OWASP ZAP scan
- Use Microsoft Security Code Analysis
- Enable Azure Defender for App Service

## Security Score

### Current: 7.5/10

**Strengths:**
- ✅ Function key authentication
- ✅ Managed Identity for Azure SQL
- ✅ Parameterized queries
- ✅ Input validation
- ✅ HTTPS enforced

**Improvements Needed:**
- ⚠️ Add Azure AD authentication (not just function key)
- ⚠️ Implement IP whitelisting
- ⚠️ Add WAF protection
- ⚠️ Enable Private Endpoints
- ⚠️ Add request signing

### To reach 10/10:
1. Enable Azure AD authentication
2. Add Azure API Management in front
3. Enable Private Link
4. Implement request signing (HMAC)
5. Add DDoS protection
