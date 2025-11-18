# Reinforcement Learning for Employer Matching Preferences

## Overview

**Goal**: Learn employer-specific preferences beyond static weights by observing their actions (views, likes, interviews, hires) to continuously improve candidate rankings.

## System Architecture

```
Static Weights (UI)  →  Initial Ranking  →  RL Model  →  Final Ranking
   (baseline)              (embedding)        (learns)      (personalized)
```

## Database Schema

```sql
-- Store employer interaction feedback
CREATE TABLE dbo.EmployerFeedback (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    EmployerId INT NOT NULL,
    PositionId INT NOT NULL,
    CandidateId INT NOT NULL,
    
    -- Interaction types (explicit and implicit signals)
    ActionType VARCHAR(50), -- 'view', 'like', 'dislike', 'save', 'interview_request', 'interview_completed', 'offer', 'hire', 'reject'
    ActionValue FLOAT, -- Normalized reward: -1.0 to 1.0
    
    -- Context at time of action
    CandidateRank INT, -- Where candidate appeared in search results
    SearchWeights NVARCHAR(MAX), -- JSON: {"skills": 0.6, "experience": 0.3, ...}
    BaseSimilarityScore FLOAT, -- Original embedding similarity
    
    CreatedAt DATETIME2 DEFAULT GETUTCDATE(),
    
    FOREIGN KEY (EmployerId) REFERENCES dbo.Employers(Id),
    FOREIGN KEY (PositionId) REFERENCES dbo.Positions(Id),
    FOREIGN KEY (CandidateId) REFERENCES dbo.Seekers(Id)
);

-- Store learned employer preferences (RL model state)
CREATE TABLE dbo.EmployerPreferenceModel (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    EmployerId INT NOT NULL,
    
    -- Learned weight adjustments
    LearnedWeights NVARCHAR(MAX), -- JSON: {"skills": 0.65, "experience": 0.25, ...}
    
    -- Feature importance learned from interactions
    FeatureImportance NVARCHAR(MAX), -- JSON: specific skills/experiences that matter
    
    -- Model metadata
    ModelVersion VARCHAR(50),
    TrainingExamples INT, -- Number of feedback instances used
    LastTrainedAt DATETIME2,
    PerformanceMetrics NVARCHAR(MAX), -- JSON: {"accuracy": 0.82, "precision": 0.76, ...}
    
    CreatedAt DATETIME2 DEFAULT GETUTCDATE(),
    UpdatedAt DATETIME2 DEFAULT GETUTCDATE(),
    
    FOREIGN KEY (EmployerId) REFERENCES dbo.Employers(Id)
);

-- Track A/B test performance
CREATE TABLE dbo.RankingExperiments (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    EmployerId INT NOT NULL,
    PositionId INT NOT NULL,
    ExperimentGroup VARCHAR(50), -- 'control' (weights only) or 'rl_enhanced'
    
    -- Metrics
    CandidatesViewed INT,
    CandidatesLiked INT,
    InterviewRequests INT,
    Hires INT,
    AvgTimeToAction FLOAT, -- Seconds to first positive action
    
    StartedAt DATETIME2,
    EndedAt DATETIME2
);
```

## Reward Signal Design

### Action → Reward Mapping

```python
REWARD_VALUES = {
    'view': 0.1,              # Weak positive signal
    'profile_view_long': 0.2, # Stayed on profile >30 seconds
    'save': 0.3,              # Bookmarked for later
    'like': 0.5,              # Explicit positive
    'dislike': -0.5,          # Explicit negative
    'interview_request': 0.7, # Strong positive
    'interview_completed': 0.8,
    'offer': 0.9,
    'hire': 1.0,              # Maximum reward
    'reject': -0.3,           # Negative but not as strong as dislike
    'no_action': -0.05        # Shown but ignored (implicit negative)
}

# Time decay: Older actions matter less
def apply_time_decay(reward, days_ago, half_life=30):
    return reward * (0.5 ** (days_ago / half_life))
```

## Implementation Approaches

### Approach 1: **Learning to Rank with Gradient Boosting** (Recommended for MVP)

**Why**: Simple, interpretable, works with small data, fast inference.

```python
from sklearn.ensemble import GradientBoostingRegressor
import numpy as np

class EmployerRankingModel:
    def __init__(self, employer_id):
        self.employer_id = employer_id
        self.model = GradientBoostingRegressor(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=5
        )
        
    def extract_features(self, candidate_sections, position_sections, base_weights):
        """Extract features for ranking model"""
        features = []
        
        # 1. Section-wise similarities (before weighting)
        for section in ['skills', 'experience', 'education', 'overview']:
            if section in candidate_sections and section in position_sections:
                sim = np.dot(candidate_sections[section], position_sections[section])
                features.append(sim)
            else:
                features.append(0.0)
        
        # 2. Weighted similarity (baseline score)
        weighted_sim = self._compute_weighted_similarity(
            candidate_sections, position_sections, base_weights
        )
        features.append(weighted_sim)
        
        # 3. Weight values themselves (model learns if employer's weights are good)
        features.extend([base_weights.get(k, 0) for k in ['skills', 'experience', 'education', 'overview']])
        
        # 4. Candidate metadata features
        features.extend([
            len(candidate_sections.get('skills', [])),  # Number of skills
            len(candidate_sections.get('experience', [])),  # Number of experiences
            # Add more as needed
        ])
        
        return np.array(features)
    
    def train(self, training_data):
        """Train on employer's historical feedback"""
        X = []  # Feature vectors
        y = []  # Rewards
        
        for feedback in training_data:
            features = self.extract_features(
                feedback['candidate_sections'],
                feedback['position_sections'],
                feedback['search_weights']
            )
            X.append(features)
            y.append(feedback['reward'])
        
        self.model.fit(np.array(X), np.array(y))
        
    def predict(self, candidate_sections, position_sections, base_weights):
        """Predict adjusted score for candidate"""
        features = self.extract_features(
            candidate_sections, position_sections, base_weights
        )
        return self.model.predict([features])[0]
    
    def rerank(self, candidates, position_sections, base_weights, alpha=0.3):
        """Rerank candidates using RL model
        
        Args:
            alpha: Blend factor (0=use only base weights, 1=use only RL model)
        """
        results = []
        
        for candidate in candidates:
            # Base similarity score (from weighted embeddings)
            base_score = candidate['base_similarity']
            
            # RL-enhanced score
            rl_score = self.predict(
                candidate['sections'],
                position_sections,
                base_weights
            )
            
            # Blend scores
            final_score = (1 - alpha) * base_score + alpha * rl_score
            
            results.append({
                'candidate_id': candidate['id'],
                'base_score': base_score,
                'rl_score': rl_score,
                'final_score': final_score
            })
        
        # Sort by final score
        results.sort(key=lambda x: x['final_score'], reverse=True)
        return results
```

### Approach 2: **Contextual Bandits** (Multi-Armed Bandit)

**Why**: Balances exploration vs exploitation, handles cold start, updates online.

```python
from scipy.stats import beta

class ContextualBanditRanker:
    """Thompson Sampling for personalized ranking"""
    
    def __init__(self, employer_id):
        self.employer_id = employer_id
        # For each candidate type/cluster, maintain beta distribution
        self.arms = {}  # {candidate_profile_type: (alpha, beta)}
        
    def get_candidate_profile_type(self, candidate_sections, position_sections):
        """Cluster candidates into types based on section similarities"""
        # Simple clustering: which section matches best?
        similarities = {}
        for section in ['skills', 'experience', 'education']:
            if section in candidate_sections and section in position_sections:
                sim = np.dot(candidate_sections[section], position_sections[section])
                similarities[section] = sim
        
        # Profile type is dominant section
        if similarities:
            dominant = max(similarities.items(), key=lambda x: x[1])
            return f"{dominant[0]}_focused"  # e.g., "skills_focused"
        return "unknown"
    
    def select_and_rank(self, candidates, position_sections, base_weights):
        """Select candidates using Thompson Sampling"""
        results = []
        
        for candidate in candidates:
            profile_type = self.get_candidate_profile_type(
                candidate['sections'], position_sections
            )
            
            # Get or initialize arm
            if profile_type not in self.arms:
                self.arms[profile_type] = (1, 1)  # Uniform prior
            
            alpha, beta_param = self.arms[profile_type]
            
            # Sample from beta distribution
            sampled_score = beta.rvs(alpha, beta_param)
            
            # Combine with base similarity
            base_score = candidate['base_similarity']
            final_score = 0.7 * base_score + 0.3 * sampled_score
            
            results.append({
                'candidate_id': candidate['id'],
                'profile_type': profile_type,
                'base_score': base_score,
                'exploration_score': sampled_score,
                'final_score': final_score
            })
        
        results.sort(key=lambda x: x['final_score'], reverse=True)
        return results
    
    def update(self, candidate_id, profile_type, reward):
        """Update arm based on feedback"""
        if profile_type not in self.arms:
            self.arms[profile_type] = (1, 1)
        
        alpha, beta_param = self.arms[profile_type]
        
        # Update beta distribution based on reward
        if reward > 0:
            alpha += reward  # Increase success count
        else:
            beta_param += abs(reward)  # Increase failure count
        
        self.arms[profile_type] = (alpha, beta_param)
```

### Approach 3: **Neural Network with Embedding Inputs** (Advanced)

**Why**: Can learn complex non-linear patterns, scales well, but needs more data.

```python
import torch
import torch.nn as nn

class RankingNeuralNetwork(nn.Module):
    def __init__(self, embedding_dim=384, num_sections=4):
        super().__init__()
        
        # Input: concatenated embeddings + metadata
        input_dim = embedding_dim * num_sections * 2 + 10  # 2 for query/candidate, +10 for metadata
        
        self.network = nn.Sequential(
            nn.Linear(input_dim, 256),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, 1),  # Output: predicted reward/relevance
            nn.Sigmoid()  # Scale to 0-1
        )
    
    def forward(self, query_sections, candidate_sections, metadata):
        # Concatenate all inputs
        inputs = torch.cat([
            query_sections.flatten(),
            candidate_sections.flatten(),
            metadata
        ])
        return self.network(inputs)

class NeuralRanker:
    def __init__(self, employer_id):
        self.employer_id = employer_id
        self.model = RankingNeuralNetwork()
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)
        self.loss_fn = nn.MSELoss()
    
    def train_step(self, query_sections, candidate_sections, metadata, reward):
        """Single training step"""
        self.model.train()
        self.optimizer.zero_grad()
        
        prediction = self.model(query_sections, candidate_sections, metadata)
        loss = self.loss_fn(prediction, torch.tensor([reward]))
        
        loss.backward()
        self.optimizer.step()
        
        return loss.item()
    
    def predict(self, query_sections, candidate_sections, metadata):
        """Predict relevance score"""
        self.model.eval()
        with torch.no_grad():
            return self.model(query_sections, candidate_sections, metadata).item()
```

## Integration Workflow

### 1. **Search Request with RL Enhancement**

```python
@app.route(route="search_candidates_rl", methods=["POST"])
def search_candidates_rl(req: func.HttpRequest) -> func.HttpResponse:
    data = req.get_json()
    
    employer_id = data.get('employerId')
    position_id = data.get('positionId')
    base_weights = data.get('weights')  # From UI (saved in table)
    use_rl = data.get('useRL', True)
    
    # Step 1: Get base ranking using weighted embeddings
    position_sections = embedding_service.get_section_embeddings('Position', position_id)
    all_candidates = embedding_service.get_all_section_embeddings('Candidate')
    
    base_results = []
    for candidate in all_candidates:
        base_similarity = embedding_service.compute_weighted_similarity(
            position_sections,
            candidate['sections'],
            base_weights
        )
        base_results.append({
            'candidate_id': candidate['id'],
            'sections': candidate['sections'],
            'base_similarity': base_similarity
        })
    
    # Step 2: Apply RL reranking if enabled and model exists
    if use_rl and has_enough_feedback(employer_id):
        rl_model = load_employer_model(employer_id)
        final_results = rl_model.rerank(
            base_results,
            position_sections,
            base_weights,
            alpha=0.3  # 70% base weights, 30% RL
        )
    else:
        # No RL model yet, use base ranking
        final_results = sorted(base_results, key=lambda x: x['base_similarity'], reverse=True)
    
    # Step 3: Return top 15
    return func.HttpResponse(
        json.dumps(final_results[:15]),
        mimetype="application/json"
    )
```

### 2. **Feedback Collection**

```python
@app.route(route="record_feedback", methods=["POST"])
def record_feedback(req: func.HttpRequest) -> func.HttpResponse:
    data = req.get_json()
    
    feedback = {
        'employer_id': data['employerId'],
        'position_id': data['positionId'],
        'candidate_id': data['candidateId'],
        'action_type': data['actionType'],  # 'view', 'like', 'hire', etc.
        'candidate_rank': data['rank'],
        'search_weights': data['searchWeights'],
        'base_similarity': data['baseSimilarity']
    }
    
    # Save to database
    db.save_feedback(feedback)
    
    # Check if we should retrain model
    feedback_count = db.get_feedback_count(feedback['employer_id'])
    if feedback_count % 10 == 0:  # Retrain every 10 feedback instances
        trigger_model_retraining(feedback['employer_id'])
    
    return func.HttpResponse(status_code=200)
```

### 3. **Model Training (Background Job)**

```python
@app.route(route="train_employer_model", methods=["POST"])
def train_employer_model(req: func.HttpRequest) -> func.HttpResponse:
    data = req.get_json()
    employer_id = data['employerId']
    
    # Fetch all feedback for employer
    feedback_data = db.get_employer_feedback(employer_id)
    
    if len(feedback_data) < 10:
        return func.HttpResponse(
            json.dumps({'message': 'Not enough data to train'}),
            status_code=400
        )
    
    # Prepare training data
    training_examples = []
    for feedback in feedback_data:
        candidate_sections = db.get_section_embeddings('Candidate', feedback['candidate_id'])
        position_sections = db.get_section_embeddings('Position', feedback['position_id'])
        
        # Apply time decay to reward
        days_ago = (datetime.now() - feedback['created_at']).days
        reward = apply_time_decay(
            REWARD_VALUES[feedback['action_type']],
            days_ago
        )
        
        training_examples.append({
            'candidate_sections': candidate_sections,
            'position_sections': position_sections,
            'search_weights': json.loads(feedback['search_weights']),
            'reward': reward
        })
    
    # Train model
    model = EmployerRankingModel(employer_id)
    model.train(training_examples)
    
    # Save model
    save_employer_model(employer_id, model)
    
    return func.HttpResponse(
        json.dumps({'message': 'Model trained successfully'}),
        mimetype="application/json"
    )
```

## Metrics to Track

```python
# Success metrics
metrics = {
    'click_through_rate': interviews_requested / candidates_shown,
    'conversion_rate': hires / candidates_shown,
    'time_to_first_action': avg_seconds_until_first_like,
    'ranking_quality': {
        'ndcg': normalized_discounted_cumulative_gain,  # Industry standard
        'map': mean_average_precision
    },
    'model_performance': {
        'mse': mean_squared_error_on_rewards,
        'correlation': spearman_correlation(predicted_rank, actual_engagement)
    }
}
```

## Cold Start Strategies

### For New Employers (No Feedback Yet)

1. **Use Industry Averages**: Start with learned models from similar employers
2. **Conservative Blending**: Use α=0.1 (90% base weights, 10% RL) until 20+ feedback instances
3. **A/B Testing**: Show some candidates with RL, some without, measure performance

```python
def get_blend_factor(feedback_count):
    """Gradually increase RL influence as we get more data"""
    if feedback_count < 10:
        return 0.0  # No RL yet
    elif feedback_count < 50:
        return 0.1  # Conservative
    elif feedback_count < 100:
        return 0.2
    else:
        return 0.3  # Full RL enhancement
```

## Recommended Implementation Path

### Phase 1: MVP (Month 1)
- ✅ Implement feedback collection endpoints
- ✅ Store employer actions in database
- ✅ Build simple gradient boosting ranker
- ✅ A/B test with α=0.1 for employers with 20+ feedback

### Phase 2: Enhancement (Month 2-3)
- Add contextual bandit for exploration
- Implement automatic retraining pipeline
- Add model performance dashboards
- Increase α to 0.2-0.3 for validated employers

### Phase 3: Advanced (Month 4+)
- Neural network ranker for high-volume employers
- Multi-task learning (predict multiple outcomes)
- Transfer learning from similar employers
- Real-time online learning

## Key Advantages

1. **Learns Implicit Preferences**: Discovers patterns employers don't explicitly configure
2. **Adapts Over Time**: Preferences evolve, model evolves
3. **Handles Noise**: Statistical learning smooths out random actions
4. **Scales**: Works for 1 employer or 10,000 employers
5. **Transparent**: Can explain why candidate was ranked higher (feature importance)

---

## Weight Learning & Auto-Update Feature

### Overview
The RL model can extract learned weights and suggest updates to the employer's stated preferences, creating a transparent feedback loop.

### Visual Representation in UI

```
┌────────────────────────────────────────────────────────────┐
│  Employer Dashboard                                        │
│                                                            │
│  Your Stated Preferences:                                 │
│  ├─ Skills:      70% ████████████████                     │
│  ├─ Experience:  20% ████                                 │
│  └─ Education:   10% ██                                   │
│                                                            │
│  What You Actually Value (Based on Your Actions):         │
│  ├─ Skills:      50% ██████████ ⚠️ Lower than stated     │
│  ├─ Experience:  40% ████████ ⚡ Much higher!            │
│  └─ Education:   10% ██                                   │
│                                                            │
│  Confidence: 85% | Based on 47 interactions               │
│                                                            │
│  💡 Your actual behavior differs from stated preferences  │
│  [Use Learned Preferences] [Keep My Settings]             │
└────────────────────────────────────────────────────────────┘
```

### Database Schema Extensions

```sql
-- Add learned weights to preference model
ALTER TABLE dbo.EmployerPreferenceModel
ADD LearnedWeights NVARCHAR(MAX), -- JSON: {"skills": 0.5, "experience": 0.4, ...}
    ConfidenceScore FLOAT,        -- 0-1, how confident we are
    WeightDrift FLOAT;            -- Total difference from stated weights

-- Track weight evolution over time
CREATE TABLE dbo.EmployerWeightHistory (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    EmployerId INT NOT NULL,
    
    StatedWeights NVARCHAR(MAX),  -- What they set in UI
    LearnedWeights NVARCHAR(MAX), -- What RL discovered
    
    ConfidenceScore FLOAT,        -- How confident (0-1)
    SampleSize INT,               -- Number of feedback instances
    WeightDrift FLOAT,            -- Total difference
    
    ActionTaken VARCHAR(50),      -- 'applied', 'dismissed', 'pending'
    
    CreatedAt DATETIME2 DEFAULT GETUTCDATE(),
    
    FOREIGN KEY (EmployerId) REFERENCES dbo.Employers(Id)
);
```

### Weight Extraction Algorithm

```python
class EmployerRankingModel:
    # ... existing code ...
    
    def extract_learned_weights(self, num_samples=100):
        """
        Reverse-engineer what weights the model learned by testing
        how much each section impacts predictions.
        
        Method: Perturbation Analysis
        - Take average feature vector from training data
        - Increase each section's similarity by 0.1
        - Measure impact on predicted score
        - Normalize to get weight distribution
        """
        # Get baseline features (average from training data)
        base_features = self._get_average_features()
        base_score = self.model.predict([base_features])[0]
        
        weight_importance = {}
        
        for section in ['skills', 'experience', 'education', 'overview']:
            # Modify just this section's similarity
            modified_features = base_features.copy()
            section_idx = ['skills', 'experience', 'education', 'overview'].index(section)
            modified_features[section_idx] += 0.1  # +10% similarity
            
            modified_score = self.model.predict([modified_features])[0]
            
            # Impact = how much score increased
            impact = max(0, modified_score - base_score)
            weight_importance[section] = impact
        
        # Normalize to sum to 1.0
        total = sum(weight_importance.values())
        if total > 0:
            learned_weights = {k: v/total for k, v in weight_importance.items()}
        else:
            # Fallback to balanced weights
            learned_weights = {k: 0.25 for k in weight_importance.keys()}
        
        return learned_weights
    
    def compute_confidence(self, training_size, validation_score):
        """
        Confidence based on:
        1. Amount of training data (more = better)
        2. Model validation performance (accuracy)
        """
        # Data confidence: reaches 1.0 at 50+ examples
        data_confidence = min(training_size / 50.0, 1.0)
        
        # Model confidence: validation R² or accuracy
        model_confidence = max(0, validation_score)  # 0-1
        
        # Combined confidence (average)
        return (data_confidence + model_confidence) / 2
```

### Training Pipeline with Weight Extraction

```python
@app.route(route="train_employer_model", methods=["POST"])
def train_employer_model(req: func.HttpRequest) -> func.HttpResponse:
    """Train RL model and extract learned weights"""
    data = req.get_json()
    employer_id = data['employerId']
    
    # Fetch feedback history
    feedback_data = db.get_employer_feedback(employer_id)
    
    if len(feedback_data) < 10:
        return func.HttpResponse(
            json.dumps({'message': 'Need at least 10 interactions to train'}),
            status_code=400
        )
    
    # Get employer's current stated weights
    stated_weights = db.get_employer_stated_weights(employer_id)
    
    # Train the ranking model
    model = EmployerRankingModel(employer_id)
    model.train(feedback_data)
    
    # Extract learned weights from trained model
    learned_weights = model.extract_learned_weights()
    
    # Compute confidence in learned weights
    confidence = model.compute_confidence(
        training_size=len(feedback_data),
        validation_score=model.evaluate_on_validation()
    )
    
    # Calculate drift (how different are learned vs stated?)
    drift = calculate_weight_drift(stated_weights, learned_weights)
    
    # Save to database
    db.save_employer_preference_model(
        employer_id=employer_id,
        learned_weights=learned_weights,
        confidence=confidence,
        weight_drift=drift,
        training_examples=len(feedback_data)
    )
    
    # Log to history table
    db.save_weight_history(
        employer_id=employer_id,
        stated_weights=stated_weights,
        learned_weights=learned_weights,
        confidence=confidence,
        sample_size=len(feedback_data),
        weight_drift=drift,
        action_taken='pending'
    )
    
    # Flag for UI notification if significant drift + high confidence
    suggest_update = drift > 0.15 and confidence > 0.7
    if suggest_update:
        db.flag_for_weight_suggestion(employer_id)
    
    return func.HttpResponse(
        json.dumps({
            'message': 'Model trained successfully',
            'stated_weights': stated_weights,
            'learned_weights': learned_weights,
            'confidence': confidence,
            'drift': drift,
            'suggest_update': suggest_update
        }),
        mimetype="application/json"
    )

def calculate_weight_drift(stated, learned):
    """
    Calculate total difference between stated and learned weights.
    Returns value between 0 (identical) and 1 (completely different).
    """
    total_diff = 0
    for key in stated.keys():
        diff = abs(stated.get(key, 0) - learned.get(key, 0))
        total_diff += diff
    # Divide by 2 since differences are counted twice (e.g., +0.1 to A means -0.1 to B)
    return total_diff / 2
```

### API: Get Weight Comparison

```python
@app.route(route="get_employer_weights", methods=["GET"])
def get_employer_weights(req: func.HttpRequest) -> func.HttpResponse:
    """Get comparison between stated and learned weights"""
    employer_id = req.params.get('employerId')
    
    # Get stated weights (from UI/table)
    stated_weights = db.get_employer_stated_weights(employer_id)
    
    # Get learned weights (from RL model)
    preference_model = db.get_employer_preference_model(employer_id)
    
    if not preference_model:
        return func.HttpResponse(
            json.dumps({
                'stated_weights': stated_weights,
                'learned_weights': None,
                'confidence': 0,
                'message': 'Not enough interaction data yet. Keep reviewing candidates!'
            }),
            mimetype="application/json"
        )
    
    learned_weights = json.loads(preference_model['LearnedWeights'])
    confidence = preference_model['ConfidenceScore']
    drift = preference_model['WeightDrift']
    
    # Calculate detailed differences
    differences = {}
    for key in stated_weights.keys():
        stated_val = stated_weights.get(key, 0)
        learned_val = learned_weights.get(key, 0)
        diff = learned_val - stated_val
        
        differences[key] = {
            'stated': stated_val,
            'learned': learned_val,
            'difference': diff,
            'percentage_change': (diff / stated_val * 100) if stated_val > 0 else 0
        }
    
    return func.HttpResponse(
        json.dumps({
            'employer_id': employer_id,
            'confidence': confidence,
            'drift': drift,
            'training_examples': preference_model['TrainingExamples'],
            'weights': differences,
            'last_trained': preference_model['LastTrainedAt'].isoformat(),
            'suggest_update': drift > 0.15 and confidence > 0.7
        }),
        mimetype="application/json"
    )
```

### API: Apply Learned Weights

```python
@app.route(route="apply_learned_weights", methods=["POST"])
def apply_learned_weights(req: func.HttpRequest) -> func.HttpResponse:
    """Update employer's stated weights to match learned weights"""
    data = req.get_json()
    employer_id = data['employerId']
    
    # Get learned weights from model
    preference_model = db.get_employer_preference_model(employer_id)
    
    if not preference_model:
        return func.HttpResponse(
            json.dumps({'error': 'No learned weights available'}),
            status_code=400
        )
    
    # Get old and new weights
    old_weights = db.get_employer_stated_weights(employer_id)
    learned_weights = json.loads(preference_model['LearnedWeights'])
    
    # Update employer's weights in database
    db.update_employer_weights(employer_id, learned_weights)
    
    # Update history record
    db.update_weight_history_action(employer_id, 'applied')
    
    # Log the change for audit
    db.log_weight_change(
        employer_id=employer_id,
        old_weights=old_weights,
        new_weights=learned_weights,
        source='rl_suggestion',
        applied_by='employer'
    )
    
    return func.HttpResponse(
        json.dumps({
            'message': 'Weights updated successfully',
            'old_weights': old_weights,
            'new_weights': learned_weights
        }),
        mimetype="application/json"
    )

@app.route(route="dismiss_learned_weights", methods=["POST"])
def dismiss_learned_weights(req: func.HttpRequest) -> func.HttpResponse:
    """Employer chose to keep their current weights"""
    data = req.get_json()
    employer_id = data['employerId']
    
    # Update history record
    db.update_weight_history_action(employer_id, 'dismissed')
    
    return func.HttpResponse(
        json.dumps({'message': 'Suggestion dismissed'}),
        mimetype="application/json"
    )
```

### Progressive Disclosure Strategy

**Phase 1: Low Confidence (< 10 interactions)**
```
UI: "We're learning your preferences... 
     Review more candidates to get personalized insights!"
Action: Don't show comparison yet
```

**Phase 2: Medium Confidence (10-30 interactions, 50-70% confidence)**
```
UI: "Early insights available (65% confidence)"
Action: Show comparison but mark as preliminary, no suggestions
```

**Phase 3: High Confidence (30+ interactions, 70%+ confidence)**
```
UI: "Your preferences are clear! (85% confidence)"
Action: Show comparison + suggest updates if drift > 15%
```

**Phase 4: Very High Confidence (50+ interactions, 85%+ confidence)**
```
UI: "Strong preference pattern detected (92% confidence)"
Action: More aggressive suggestions, highlight benefits
```

### Example Scenarios

#### Scenario 1: Skills-Focused Employer Discovers Experience Matters
```
Stated:     Skills 70%, Experience 20%, Education 10%
Learned:    Skills 50%, Experience 40%, Education 10%
Drift:      0.20 (20% total difference)
Confidence: 0.83

Message: 
"You're actually valuing experience 2x more than you thought! 
Candidates with strong experience get 80% more likes from you.
Consider increasing experience weight to 40%."
```

#### Scenario 2: Overestimating Education Importance
```
Stated:     Skills 50%, Experience 30%, Education 20%
Learned:    Skills 55%, Experience 40%, Education 5%
Drift:      0.20
Confidence: 0.78

Message:
"Education doesn't seem to influence your decisions much.
You've hired candidates regardless of education requirements 85% of the time.
Consider reducing education weight to 5% for better matches."
```

#### Scenario 3: Well-Calibrated Employer
```
Stated:     Skills 40%, Experience 40%, Education 20%
Learned:    Skills 42%, Experience 38%, Education 20%
Drift:      0.04 (4% difference)
Confidence: 0.88

Message:
"Great job! Your stated preferences match your actual behavior. ✓
Your weights are well-calibrated - no changes needed."
```

### UI Component Structure (React/TypeScript)

```typescript
interface WeightComparison {
  stated: number;
  learned: number;
  difference: number;
  percentage_change: number;
}

interface WeightData {
  employer_id: number;
  confidence: number;
  drift: number;
  training_examples: number;
  weights: Record<string, WeightComparison>;
  last_trained: string;
  suggest_update: boolean;
}

function WeightComparisonDashboard({ employerId }: { employerId: number }) {
  const [data, setData] = useState<WeightData | null>(null);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    fetch(`/api/get_employer_weights?employerId=${employerId}`)
      .then(r => r.json())
      .then(d => {
        setData(d);
        setLoading(false);
      });
  }, [employerId]);
  
  const applyLearnedWeights = async () => {
    await fetch('/api/apply_learned_weights', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ employerId })
    });
    window.location.reload();
  };
  
  const dismissSuggestion = async () => {
    await fetch('/api/dismiss_learned_weights', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ employerId })
    });
    setData({ ...data, suggest_update: false });
  };
  
  if (loading) return <div>Loading...</div>;
  
  if (!data?.weights) {
    return (
      <div className="early-stage">
        <p>We're learning your preferences...</p>
        <p>Review more candidates to get personalized insights!</p>
        <progress value={data?.training_examples || 0} max={10} />
      </div>
    );
  }
  
  const hasSignificantDrift = data.drift > 0.15;
  const highConfidence = data.confidence > 0.7;
  
  return (
    <div className="weight-comparison-dashboard">
      <h2>Your Hiring Preferences</h2>
      
      <div className="confidence-badge" data-level={
        data.confidence > 0.85 ? 'high' : data.confidence > 0.7 ? 'medium' : 'low'
      }>
        Confidence: {(data.confidence * 100).toFixed(0)}%
        <span className="detail">
          Based on {data.training_examples} interactions
        </span>
      </div>
      
      {Object.entries(data.weights).map(([section, comparison]) => (
        <div key={section} className="weight-row">
          <h3>{section.charAt(0).toUpperCase() + section.slice(1)}</h3>
          
          <div className="weight-bars">
            <div className="stated-weight">
              <label>What you set:</label>
              <div 
                className="bar stated" 
                style={{ width: `${comparison.stated * 100}%` }}
              >
                {(comparison.stated * 100).toFixed(0)}%
              </div>
            </div>
            
            <div className="learned-weight">
              <label>What you actually value:</label>
              <div 
                className="bar learned" 
                style={{ width: `${comparison.learned * 100}%` }}
              >
                {(comparison.learned * 100).toFixed(0)}%
              </div>
              
              {Math.abs(comparison.difference) > 0.05 && (
                <span className={`change ${comparison.difference > 0 ? 'increase' : 'decrease'}`}>
                  {comparison.difference > 0 ? '↑' : '↓'} 
                  {Math.abs(comparison.percentage_change).toFixed(0)}%
                  {Math.abs(comparison.difference) > 0.15 && ' ⚠️'}
                </span>
              )}
            </div>
          </div>
        </div>
      ))}
      
      {hasSignificantDrift && highConfidence && data.suggest_update && (
        <div className="suggestion-banner">
          <div className="icon">💡</div>
          <div className="content">
            <h4>Suggestion: Update Your Preferences</h4>
            <p>
              Your actual hiring behavior differs significantly from your stated preferences.
              Would you like to update your weights to match what you actually value?
              This could improve your candidate matches by up to {(data.drift * 100).toFixed(0)}%.
            </p>
            <div className="actions">
              <button className="primary" onClick={applyLearnedWeights}>
                Use Learned Preferences
              </button>
              <button className="secondary" onClick={dismissSuggestion}>
                Keep My Current Settings
              </button>
            </div>
          </div>
        </div>
      )}
      
      {!hasSignificantDrift && highConfidence && (
        <div className="success-banner">
          <span className="icon">✓</span>
          <p>
            Great job! Your stated preferences match your actual behavior.
            Your weights are well-calibrated.
          </p>
        </div>
      )}
      
      <div className="timestamp">
        Last updated: {new Date(data.last_trained).toLocaleString()}
      </div>
    </div>
  );
}
```

### Benefits of Weight Auto-Update

1. **Transparency**: Employer sees exactly what they're doing vs what they think they're doing
2. **Self-Discovery**: "Oh, I didn't realize experience mattered that much to me!"
3. **Trust**: Employer has final say - can accept or reject suggestion
4. **Continuous Learning**: Even after accepting, model keeps learning and adapting
5. **Data-Driven**: Removes guesswork, based on actual hiring behavior
6. **Accountability**: Can track how preferences evolve over time
7. **Better Matches**: Aligned weights = better candidate rankings = faster hires

### Virtuous Cycle

```
Better Weights → Better Candidate Rankings → More Engagement → 
More Feedback → Better Learning → Even Better Weights → ...
```

### Implementation Phases

**Phase 1: Silent Learning (Month 1)**
- Collect feedback, train models, extract weights
- Don't show to users yet, validate accuracy internally

**Phase 2: Read-Only Insights (Month 2)**
- Show weight comparison in dashboard
- No suggestions yet, just informational
- A/B test with 25% of employers

**Phase 3: Suggestions (Month 3)**
- Add "Apply Learned Weights" button
- Only show for high-confidence + high-drift cases
- Track acceptance rate

**Phase 4: Proactive Nudges (Month 4+)**
- Email notifications when drift detected
- In-app tooltips during search
- Gradual auto-adjustment with user consent

Want me to implement this weight extraction and update system?
