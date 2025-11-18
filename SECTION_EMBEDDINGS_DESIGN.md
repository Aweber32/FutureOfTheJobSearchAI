# Section-Based Embeddings Design

## Database Schema

### Option A: Separate Columns (Good for fixed sections)
```sql
CREATE TABLE dbo.SeekerEmbeddings (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    SeekerId INT NOT NULL,
    
    -- Section embeddings (each 1536 bytes for 384-dim float32)
    SkillsEmbedding VARBINARY(MAX),
    ExperienceEmbedding VARBINARY(MAX),
    EducationEmbedding VARBINARY(MAX),
    OverviewEmbedding VARBINARY(MAX),
    
    -- Combined for backward compatibility
    CombinedEmbedding VARBINARY(MAX),
    
    ModelVersion VARCHAR(50),
    CreatedAt DATETIME2 DEFAULT GETUTCDATE(),
    
    FOREIGN KEY (SeekerId) REFERENCES dbo.Seekers(Id)
);
```

### Option B: JSON Metadata (More flexible)
```sql
CREATE TABLE dbo.SeekerEmbeddings (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    SeekerId INT NOT NULL,
    
    -- Store all section embeddings as separate rows or in blob storage
    CombinedEmbedding VARBINARY(MAX),
    
    -- JSON with section info
    SectionMetadata NVARCHAR(MAX), -- {"skills": {"offset": 0, "length": 1536}, ...}
    
    ModelVersion VARCHAR(50),
    CreatedAt DATETIME2 DEFAULT GETUTCDATE()
);

-- Or separate table for sections
CREATE TABLE dbo.EmbeddingSections (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    EntityType VARCHAR(50), -- 'Candidate' or 'Position'
    EntityId INT,
    SectionName VARCHAR(100), -- 'skills', 'experience', etc.
    Embedding VARBINARY(MAX),
    ModelVersion VARCHAR(50),
    CreatedAt DATETIME2 DEFAULT GETUTCDATE()
);
```

## Implementation Options

### 1. Pre-compute with Default Weights (Fast queries)
- Store one combined embedding with default weights
- Recompute when user changes preferences
- **Best for**: Few preference changes, fast search needed

### 2. Store Sections + Combine at Query Time (Flexible)
- Store separate section embeddings
- Combine based on user weights during search
- **Best for**: Frequent preference changes

### 3. Hybrid Approach (Recommended)
- Store section embeddings separately
- Cache combined embeddings for common weight profiles
- Fall back to real-time combination for custom weights

## Code Implementation

```python
class SectionEmbeddingService:
    def generate_section_embeddings(self, entity_type: str, entity_id: int):
        """Generate separate embeddings for each section"""
        profile_data = self.db.fetch_profile_text(entity_type, entity_id)
        raw_data = profile_data["raw_data"]
        
        sections = {}
        
        if entity_type == "Candidate":
            # Create text for each section
            sections['skills'] = self._format_skills(raw_data.get('skills', []))
            sections['experience'] = self._format_experience(raw_data.get('experiences', []))
            sections['education'] = self._format_education(raw_data.get('educations', []))
            sections['overview'] = self._format_overview(raw_data)
        else:  # Position
            sections['skills'] = self._format_position_skills(raw_data.get('skills', []))
            sections['requirements'] = self._format_requirements(raw_data)
            sections['description'] = raw_data.get('description', '')
            sections['company'] = self._format_company(raw_data)
        
        # Generate embedding for each section
        embeddings = {}
        for section_name, text in sections.items():
            if text.strip():  # Only if section has content
                embeddings[section_name] = self.model.encode(text, normalize_embeddings=True)
        
        return embeddings
    
    def combine_embeddings(self, section_embeddings: dict, weights: dict) -> np.ndarray:
        """Combine section embeddings with user-specified weights"""
        # Normalize weights to sum to 1.0
        total_weight = sum(weights.get(k, 0) for k in section_embeddings.keys())
        if total_weight == 0:
            total_weight = 1.0
        
        normalized_weights = {
            k: weights.get(k, 0) / total_weight 
            for k in section_embeddings.keys()
        }
        
        # Weighted sum
        combined = np.zeros_like(next(iter(section_embeddings.values())))
        for section_name, embedding in section_embeddings.items():
            weight = normalized_weights.get(section_name, 0)
            combined += embedding * weight
        
        # Normalize to unit length (critical for cosine similarity)
        norm = np.linalg.norm(combined)
        if norm > 0:
            combined = combined / norm
        
        return combined
    
    def search_with_preferences(self, query_embedding: np.ndarray, 
                                entity_type: str, user_weights: dict, top_k: int = 10):
        """Search using user-specified section weights"""
        # Fetch all section embeddings from database
        all_entities = self.db.get_all_section_embeddings(entity_type)
        
        results = []
        for entity in all_entities:
            # Combine sections with user weights
            combined = self.combine_embeddings(entity['sections'], user_weights)
            
            # Compute cosine similarity
            similarity = np.dot(query_embedding, combined)
            results.append({
                'entity_id': entity['id'],
                'similarity': similarity,
                'sections': entity['sections']
            })
        
        # Sort by similarity
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]
```

## User Interface Example

```python
# User preference profiles
preference_profiles = {
    'balanced': {
        'skills': 0.25,
        'experience': 0.25,
        'education': 0.25,
        'overview': 0.25
    },
    'skills_focused': {
        'skills': 0.6,
        'experience': 0.2,
        'education': 0.1,
        'overview': 0.1
    },
    'experience_focused': {
        'skills': 0.2,
        'experience': 0.6,
        'education': 0.1,
        'overview': 0.1
    },
    'custom': {
        # User can adjust sliders
    }
}
```

## API Design

```python
# Endpoint for weighted search
@app.route(route="search_candidates", methods=["POST"])
def search_candidates(req: func.HttpRequest) -> func.HttpResponse:
    data = req.get_json()
    
    position_id = data.get('positionId')
    weights = data.get('weights', {
        'skills': 0.4,
        'experience': 0.3,
        'education': 0.2,
        'overview': 0.1
    })
    
    # Get position embedding
    position_sections = embedding_service.get_section_embeddings('Position', position_id)
    position_combined = embedding_service.combine_embeddings(position_sections, weights)
    
    # Search candidates with same weights
    results = embedding_service.search_with_preferences(
        position_combined,
        'Candidate',
        weights,
        top_k=20
    )
    
    return func.HttpResponse(json.dumps(results), mimetype="application/json")
```

## Storage Considerations

### Option 1: Store as Separate Columns (1536 bytes each)
- **Pros**: Fast queries, simple SQL
- **Cons**: Fixed sections, schema changes for new sections
- **Storage**: ~6KB per entity (4 sections × 1536 bytes)

### Option 2: Store as Blob with Metadata
- **Pros**: Flexible sections, easy to add new ones
- **Cons**: Need to parse blob, slightly slower
- **Storage**: Same as Option 1 but more flexible

### Option 3: Separate Table (Recommended)
- **Pros**: Most flexible, can query individual sections
- **Cons**: Slightly more complex queries
- **Storage**: One row per section per entity

## Performance Tips

1. **Cache Common Weight Profiles**: Pre-compute embeddings for popular weight combinations
2. **Batch Processing**: Update section embeddings in batches during off-peak hours
3. **Incremental Updates**: Only recompute sections that changed
4. **Index Strategy**: Create indexes on EntityId + SectionName for fast retrieval
5. **Approximate Search**: Use FAISS or similar for fast similarity search at scale

## Migration Path

1. **Phase 1**: Add section columns to existing tables (backward compatible)
2. **Phase 2**: Generate section embeddings for all existing entities
3. **Phase 3**: Add weighted search endpoint
4. **Phase 4**: Deprecate single-embedding approach (optional)
