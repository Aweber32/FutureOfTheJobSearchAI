# Embedding Text Generation - Field Mapping

This document shows exactly what fields are queried and how they're formatted into text for embedding generation.

## Candidate (Job Seeker) Embedding

### Source Table: `Seeker`

**Query Fields:**
```sql
SELECT 
    Id, FirstName, LastName, Skills, ProfessionalSummary,
    ExperienceJson, EducationJson, VisaStatus, PreferredSalary,
    WorkSetting, Travel, Relocate, Languages, Certifications,
    Interests, City, State
FROM Seeker
WHERE Id = ?
```

**Text Format:**
```
Name: {FirstName} {LastName} | 
Professional Summary: {ProfessionalSummary} | 
Skills: {Skills} | 
Experience: {parsed from ExperienceJson} | 
Education: {parsed from EducationJson} | 
Location: {City}, {State} | 
Work Setting: {WorkSetting} | 
Travel: {Travel} | 
Relocation: {Relocate} | 
Preferred Salary: {PreferredSalary} | 
Certifications: {Certifications} | 
Languages: {Languages} | 
Visa Status: {VisaStatus} | 
Interests: {Interests}
```

**Example Output:**
```
Name: Alice Johnson | Professional Summary: Experienced full-stack software engineer with 5+ years building scalable cloud applications | Skills: Python, JavaScript, React, Node.js, Azure, SQL | Experience: Senior Software Engineer at Tech Solutions Inc (2021-Present) - Lead development of microservices architecture; Software Engineer at StartupXYZ (2019-2021) - Built React-based SPA | Education: Bachelor of Science in Computer Science from State University (2019) | Location: Seattle, WA | Work Setting: Remote, Hybrid | Travel: Occasionally | Relocation: Open to relocation | Preferred Salary: $120,000 - $150,000 | Certifications: Azure Solutions Architect, AWS Certified Developer | Languages: English (Native), Spanish (Conversational) | Visa Status: US Citizen | Interests: Open source contributions, hiking, photography
```

---

## Position (Job Posting) Embedding

### Source Tables: 
- `Positions` (main)
- `Employers` (joined for company name)
- `PositionSkills` → `Skills` (many-to-many)
- `PositionEducations` → `Educations` (many-to-many)
- `PositionExperiences` → `Experiences` (many-to-many)

**Main Query:**
```sql
SELECT 
    p.Id, p.Title, p.Category, p.Description,
    p.EmploymentType, p.WorkSetting, p.TravelRequirements,
    p.SalaryType, p.SalaryValue, p.SalaryMin, p.SalaryMax,
    e.CompanyName
FROM Positions p
LEFT JOIN Employers e ON p.EmployerId = e.Id
WHERE p.Id = ?
```

**Related Queries:**
```sql
-- Skills
SELECT s.SkillName 
FROM PositionSkills ps
INNER JOIN Skills s ON ps.SkillId = s.Id
WHERE ps.PositionId = ?

-- Education Requirements
SELECT ed.DegreeName, ed.FieldOfStudy
FROM PositionEducations pe
INNER JOIN Educations ed ON pe.EducationId = ed.Id
WHERE pe.PositionId = ?

-- Experience Requirements
SELECT ex.Title, ex.YearsRequired
FROM PositionExperiences pex
INNER JOIN Experiences ex ON pex.ExperienceId = ex.Id
WHERE pex.PositionId = ?
```

**Text Format:**
```
Position: {Title} | 
Company: {CompanyName} | 
Category: {Category} | 
Description: {Description} | 
Required Skills: {Skills joined by comma} | 
Education Requirements: {Educations joined by comma} | 
Experience Requirements: {Experiences joined by comma} | 
Employment Type: {EmploymentType} | 
Work Setting: {WorkSetting} | 
Travel: {TravelRequirements} | 
Salary: {SalaryType} ${SalaryMin} - ${SalaryMax}
```

**Example Output:**
```
Position: Senior Software Engineer | Company: Tech Innovations Inc | Category: Software Development | Description: We're seeking an experienced full-stack engineer to lead our cloud platform development. You'll architect scalable solutions and mentor junior developers. | Required Skills: Python, React, Node.js, Azure, Kubernetes, SQL | Education Requirements: Bachelor's Degree in Computer Science, Master's Degree in Software Engineering | Experience Requirements: Senior Engineer (5 years), Cloud Architecture (3 years) | Employment Type: Full-time | Work Setting: Hybrid | Travel: Occasionally | Salary: Annual $130,000 - $160,000
```

---

## Key Design Principles

1. **Semantic Richness**: Include descriptive fields that convey meaning (not just keywords)
2. **Structured Format**: Use consistent delimiters (`|`) for clear separation
3. **Prioritization**: Most important fields (summary, description, skills) come first
4. **Completeness**: Include all relevant fields even if some are empty
5. **Normalization**: Related collections are flattened into comma-separated lists
6. **Human Readable**: Text is readable and makes sense to humans (helps with debugging)

## Why This Format Works

The embedding model (all-mpnet-base-v2) is trained on natural language, so our text format:
- Uses natural sentence structure where possible
- Labels fields clearly ("Skills:", "Location:", etc.)
- Preserves semantic relationships (e.g., experience with company names and duration)
- Allows the model to understand context and relationships between fields

This enables semantic matching where:
- A candidate with "Python, React" skills matches a position requiring "Python, JavaScript frameworks"
- "Remote, Hybrid" work preferences match "Hybrid" work settings
- "5 years experience" matches "Senior Engineer (5 years)" requirements
