# Database Schema Reference

This document describes the expected database schema for the ELEV8R embedding service.

## Tables Used

### 1. Seeker (Source Data)
Job seeker profiles - data source for candidate embeddings.

**Key Fields:**
- `Id` (PK)
- `FirstName`, `LastName`
- `ProfessionalSummary` - Main description
- `Skills` - Comma-separated skills
- `ExperienceJson` - Structured experience data
- `EducationJson` - Structured education data
- `City`, `State` - Location
- `WorkSetting`, `Travel`, `Relocate` - Preferences
- `PreferredSalary`
- `VisaStatus`, `Languages`, `Certifications`, `Interests`

### 2. Positions (Source Data)
Job positions - data source for position embeddings.

**Main Fields:**
- `Id` (PK)
- `EmployerId` (FK) → Links to `Employers.CompanyName`
- `Title` - Job title
- `Category` - Job category
- `Description` - Main job description
- `EmploymentType` - Full-time, Part-time, Contract, etc.
- `WorkSetting` - Remote, Hybrid, On-site
- `TravelRequirements` - Travel expectations
- `SalaryType`, `SalaryValue`, `SalaryMin`, `SalaryMax` - Compensation details
- `PosterVideoUrl` - Video introduction URL
- `IsOpen` - Whether accepting applications

**Related Collections (Normalized):**
- `PositionSkills` → Links to `Skills` table (many-to-many)
- `PositionEducations` → Links to `Educations` table (education requirements)
- `PositionExperiences` → Links to `Experiences` table (experience requirements)

### 3. SeekerEmbeddings (Embedding Storage)
Stores vector embeddings for job seekers.

**Schema:**
```sql
CREATE TABLE SeekerEmbeddings (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    SeekerId INT NOT NULL,
    Embedding VARBINARY(MAX) NOT NULL,
    ModelVersion NVARCHAR(50) NOT NULL,
    CreatedAt DATETIME2 NOT NULL,
    UpdatedAt DATETIME2 NOT NULL,
    
    CONSTRAINT FK_SeekerEmbeddings_Seeker 
        FOREIGN KEY (SeekerId) REFERENCES Seeker(Id) ON DELETE CASCADE,
    CONSTRAINT UQ_SeekerEmbeddings_SeekerId UNIQUE (SeekerId)
);
```

### 4. PositionEmbeddings (Embedding Storage)
Stores vector embeddings for job positions.

**Schema:**
```sql
CREATE TABLE PositionEmbeddings (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    PositionId INT NOT NULL,
    Embedding VARBINARY(MAX) NOT NULL,
    ModelVersion NVARCHAR(50) NOT NULL,
    CreatedAt DATETIME2 NOT NULL,
    UpdatedAt DATETIME2 NOT NULL,
    
    CONSTRAINT FK_PositionEmbeddings_Position 
        FOREIGN KEY (PositionId) REFERENCES Positions(Id) ON DELETE CASCADE,
    CONSTRAINT UQ_PositionEmbeddings_PositionId UNIQUE (PositionId)
);
```

## Embedding Format

- **Storage**: `VARBINARY(MAX)` - numpy array serialized to bytes via `.tobytes()`
- **Dimension**: 768 floats (for all-mpnet-base-v2 model)
- **Size**: ~3KB per embedding (768 × 4 bytes for float32)
- **Model Version**: Tracks which model generated the embedding (e.g., "all-mpnet-base-v2-v1")

## Data Flow

1. **Trigger**: HTTP POST with `{"entityType": "Candidate", "entityId": "123"}` or `{"entityType": "Position", "entityId": "456"}`
2. **Fetch**: 
   - For Candidates: Query `Seeker` table for all profile fields
   - For Positions: Query `Positions` table + join to `Employers` + fetch related `PositionSkills`, `PositionEducations`, `PositionExperiences`
3. **Format**: Concatenate fields into structured text optimized for semantic search
4. **Embed**: Generate 768-dimensional vector using SentenceTransformer (all-mpnet-base-v2)
5. **Store**: MERGE (upsert) into `SeekerEmbeddings` or `PositionEmbeddings` table
6. **Update**: Set `UpdatedAt` timestamp for cache invalidation

## API Usage

### Generate Candidate Embedding
```bash
curl -X POST http://localhost:7071/api/trigger_embedding \
  -H "Content-Type: application/json" \
  -d '{"entityType": "Candidate", "entityId": "123"}'
```

### Generate Position Embedding
```bash
curl -X POST http://localhost:7071/api/trigger_embedding \
  -H "Content-Type: application/json" \
  -d '{"entityType": "Position", "entityId": "456"}'
```

## Notes

- One embedding per entity (enforced by unique constraint)
- Embeddings automatically update via MERGE operation
- Old embeddings are overwritten when regenerated
- `ModelVersion` allows tracking model upgrades over time
