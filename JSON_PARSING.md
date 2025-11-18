# JSON Field Parsing - Experience & Education

This document explains how `ExperienceJson` and `EducationJson` fields are parsed to extract individual entries for embeddings.

## Experience JSON Parsing

### Supported Field Names

The `_format_experience()` method is flexible and handles multiple naming conventions:

| Data Point | Accepted Field Names |
|------------|---------------------|
| Job Title | `title`, `position`, `jobTitle` |
| Company | `company`, `employer`, `companyName` |
| Duration | `duration` (e.g., "2020-2023") |
| Dates | `startDate` + `endDate` |
| Years | `years`, `yearsOfExperience` |
| Description | `description`, `responsibilities`, `details` |

### Example Input JSON

```json
[
  {
    "title": "Senior Software Engineer",
    "company": "Tech Solutions Inc",
    "startDate": "2021-01",
    "endDate": "Present",
    "description": "Lead development of microservices architecture on Azure. Mentor junior developers and conduct code reviews."
  },
  {
    "position": "Software Engineer",
    "employer": "StartupXYZ",
    "duration": "2019-2021",
    "responsibilities": "Built React-based SPA and Node.js APIs. Improved application performance by 40%."
  }
]
```

### Formatted Output for Embedding

```
Senior Software Engineer at Tech Solutions Inc (2021-01 - Present) - Lead development of microservices architecture on Azure. Mentor junior developers and conduct code reviews.; Software Engineer at StartupXYZ (2019-2021) - Built React-based SPA and Node.js APIs. Improved application performance by 40%.
```

### Parsing Logic

```python
for each experience in ExperienceJson:
    1. Extract title (required for inclusion)
    2. Extract company name
    3. Extract duration OR compute from startDate/endDate
    4. Extract description (truncated to 200 chars if too long)
    5. Join with spaces: "Title at Company (Duration) - Description"
    6. Separate multiple experiences with "; "
```

---

## Education JSON Parsing

### Supported Field Names

The `_format_education()` method handles multiple naming conventions:

| Data Point | Accepted Field Names |
|------------|---------------------|
| Degree | `degree`, `degreeName`, `degreeType` |
| Major/Field | `field`, `major`, `fieldOfStudy` |
| Institution | `institution`, `school`, `university` |
| Year | `year`, `graduationYear`, `endDate` |
| GPA | `gpa` (only included if ≥ 3.5) |

### Example Input JSON

```json
[
  {
    "degree": "Bachelor of Science",
    "field": "Computer Science",
    "institution": "State University",
    "year": "2019",
    "gpa": "3.8"
  },
  {
    "degreeName": "Master of Science",
    "major": "Software Engineering",
    "school": "Tech Institute",
    "graduationYear": "2021"
  }
]
```

### Formatted Output for Embedding

```
Bachelor of Science in Computer Science from State University (2019) GPA: 3.8; Master of Science in Software Engineering from Tech Institute (2021)
```

### Parsing Logic

```python
for each education in EducationJson:
    1. Extract degree name
    2. Extract field/major
    3. Extract institution
    4. Extract graduation year
    5. Extract GPA if >= 3.5 (high achievers)
    6. Join with spaces: "Degree in Field from Institution (Year) GPA: X.X"
    7. Separate multiple degrees with "; "
```

---

## Why This Matters for Matching

### Individual Entries Preserved

Each work experience is a separate sentence in the embedding text, so:
- "Software Engineer at Google" and "Data Scientist at Microsoft" are both captured
- The model learns the candidate has experience at multiple companies
- Specific job titles and companies can be matched against position requirements

### Rich Context for Semantic Matching

**Example Seeker:**
```json
{
  "ExperienceJson": [
    {"title": "ML Engineer", "company": "AI Startup", "description": "Built NLP models"}
  ]
}
```

**Embedded As:**
```
Experience: ML Engineer at AI Startup - Built NLP models
```

**Matches Position:**
```
Position: Machine Learning Engineer | Description: We need someone with NLP experience
```

The semantic similarity between "ML Engineer...Built NLP models" and "Machine Learning Engineer...NLP experience" enables accurate matching even with different wording!

---

## Handling Edge Cases

### Missing Fields
```json
{"title": "Developer"}  // No company
```
**Output:** `Developer` (just the title)

### Empty JSON
```json
[]  // or null
```
**Output:** `` (empty string, field omitted from embedding)

### Long Descriptions
```json
{
  "description": "Very long text exceeding 200 characters..."
}
```
**Output:** Truncated to 200 chars + "..."

### Multiple Formats in Same JSON
```json
[
  {"title": "...", "company": "..."},       // Uses "title"
  {"position": "...", "employer": "..."}    // Uses "position"
]
```
**Both work!** The parser tries all field name variations.

---

## Testing Your JSON Format

To ensure your JSON structure works correctly, it should match one of these patterns:

### ✅ Recommended Experience Format
```json
[
  {
    "title": "Job Title",
    "company": "Company Name",
    "startDate": "YYYY-MM",
    "endDate": "YYYY-MM" or "Present",
    "description": "What you did in this role"
  }
]
```

### ✅ Recommended Education Format
```json
[
  {
    "degree": "Bachelor of Science",
    "field": "Computer Science",
    "institution": "University Name",
    "year": "YYYY",
    "gpa": "X.X"
  }
]
```

The parser is forgiving and will extract whatever fields are present!
