# ELEV8R - Embedding Service

Video-based Job Matching Platform - Embedding Pipeline (Phase 1)

## Overview

Azure Functions-based embedding service that transforms candidate profiles and job postings into numerical vector embeddings for semantic matching.

## Project Structure

```
/elev8r-embedding-function/
├── host.json                    # Azure Functions host configuration
├── local.settings.json          # Local development settings (not in git)
├── requirements.txt             # Python dependencies
├── shared/                      # Shared modules
│   ├── __init__.py
│   ├── db_client.py            # Database client for Azure SQL
│   └── global_embedding_service.py  # Embedding generation service
├── functions/                   # Azure Functions
│   ├── __init__.py
│   └── trigger_embedding/      # HTTP trigger for embedding generation
│       ├── __init__.py
│       └── function.json
├── tests/                       # Unit tests
│   ├── __init__.py
│   └── test_trigger_embedding.py
└── database/                    # Database setup scripts
    ├── schema.sql
    └── test_data.sql
```

## Database Schema

### Seeker Table
The service reads from the `Seeker` table with these fields:
- **Profile**: `FirstName`, `LastName`, `ProfessionalSummary`
- **Skills & Experience**: `Skills`, `ExperienceJson`, `EducationJson`
- **Preferences**: `WorkSetting`, `Travel`, `Relocate`, `PreferredSalary`
- **Location**: `City`, `State`
- **Qualifications**: `VisaStatus`, `Languages`, `Certifications`
- **Additional**: `Interests`

### Positions Table
The service reads from the `Positions` table with these fields:
- **Job Info**: `Title`, `Category`, `Description`, `CompanyName` (via `Employers` join)
- **Employment**: `EmploymentType`, `WorkSetting`, `TravelRequirements`
- **Compensation**: `SalaryType`, `SalaryValue`, `SalaryMin`, `SalaryMax`
- **Related Collections**: 
  - `PositionSkills` → Required skills (normalized)
  - `PositionEducations` → Education requirements (normalized)
  - `PositionExperiences` → Experience requirements (normalized)

### Embedding Storage Tables
- **SeekerEmbeddings**: Stores embeddings for job seekers (FK: `SeekerId` → `Seeker.Id`)
- **PositionEmbeddings**: Stores embeddings for job positions (FK: `PositionId` → `Positions.Id`)

Both embedding tables contain:
- `Embedding` (VARBINARY(MAX)) - Vector embedding as bytes
- `ModelVersion` (NVARCHAR(50)) - Model identifier
- `CreatedAt`, `UpdatedAt` - Timestamps

## Setup

### Prerequisites

- Python 3.9+
- Azure Functions Core Tools
- Azure SQL Database with `Seeker`, `Positions`, `SeekerEmbeddings`, and `PositionEmbeddings` tables
- Azure CLI (for local authentication)

### Database Connection

**Local Development:**
1. Login to Azure: `az login`
2. The connection string in `local.settings.json` uses Active Directory Default authentication

**Production (Azure Functions):**
- Uses Managed Identity automatically
- Set `USE_MANAGED_IDENTITY=true` in Application Settings
- Grant the Function App's Managed Identity database access:
  ```sql
  CREATE USER [<function-app-name>] FROM EXTERNAL PROVIDER;
  ALTER ROLE db_datareader ADD MEMBER [<function-app-name>];
  ALTER ROLE db_datawriter ADD MEMBER [<function-app-name>];
  ```

### Local Development

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure local settings**:
   Copy `local.settings.json.template` to `local.settings.json` and fill in:
   - `SQL_CONNECTION_STRING`: Your Azure SQL connection string
   - `EMBEDDING_MODEL_PATH`: Model name (default: "all-MiniLM-L6-v2", 384-dim, 80MB)
   - `EMBEDDING_MODEL_VERSION`: Version identifier (default: "v1")
   
   **Model Options:**
   - `all-MiniLM-L6-v2`: Fast, smaller (80MB, 384-dim) - **Recommended for Consumption Plan**
   - `all-mpnet-base-v2`: More accurate, larger (420MB, 768-dim) - **Requires Premium Plan**

3. **Run locally**:
   ```bash
   func start
   ```

## Usage

### Trigger Embedding Generation

POST to the HTTP endpoint with:

**For Job Seekers:**
```json
{
  "entityType": "Candidate",
  "entityId": "12345"
}
```

**For Job Positions:**
```json
{
  "entityType": "Position",
  "entityId": "67890"
}
```

## Deployment

See deployment documentation for CI/CD setup with GitHub Actions.

## Phase 1 Tasks

- [x] Project structure setup
- [ ] Database connectivity validation
- [ ] Embedding service implementation
- [ ] End-to-end testing
- [ ] Azure deployment
- [ ] Monitoring setup
