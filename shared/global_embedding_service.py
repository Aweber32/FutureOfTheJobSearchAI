import os
import logging
import numpy as np
from sentence_transformers import SentenceTransformer
from shared.db_client import DBClient

class EmbeddingService:
    _model = None

    @classmethod
    def _load_model(cls):
        if cls._model is None:
            model_name = os.getenv("EMBEDDING_MODEL_PATH", "all-MiniLM-L6-v2")
            logging.info(f"Loading embedding model: {model_name}")
            
            import time
            start = time.time()
            cls._model = SentenceTransformer(model_name)
            elapsed = time.time() - start
            logging.info(f"Model loaded in {elapsed:.2f} seconds")
            
        return cls._model

    @classmethod
    def trigger_embedding(cls, entity_type: str, entity_id: str) -> bool:
        logging.info(f"[EmbeddingService] Starting embedding generation for {entity_type} {entity_id}")
        
        # Fetch text for embedding
        try:
            logging.info(f"[EmbeddingService] Fetching profile text from database...")
            db = DBClient()
            profile_data = db.fetch_profile_text(entity_type, entity_id)
            text = profile_data["text"]  # Extract text from the dictionary
            text_length = len(text)
            logging.info(f"[EmbeddingService] Retrieved text ({text_length} chars): {text[:200]}...")
        except Exception as e:
            logging.error(f"[EmbeddingService] ❌ Failed to fetch profile text: {str(e)}")
            raise

        # Generate embedding
        try:
            logging.info(f"[EmbeddingService] Generating embedding vector...")
            model = cls._load_model()
            vec = model.encode(text, show_progress_bar=False)
            vec_np = np.array(vec, dtype=np.float32)
            logging.info(f"[EmbeddingService] ✓ Generated {len(vec_np)}-dimensional embedding")
        except Exception as e:
            logging.error(f"[EmbeddingService] ❌ Failed to generate embedding: {str(e)}")
            raise

        # Save embedding
        try:
            logging.info(f"[EmbeddingService] Saving embedding to database...")
            model_version = os.getenv("EMBEDDING_MODEL_VERSION", "v1")
            db.save_embedding(entity_type, entity_id, vec_np, model_version)
            logging.info(f"[EmbeddingService] ✓ Saved embedding for {entity_type} {entity_id} with model version {model_version}")
        except Exception as e:
            logging.error(f"[EmbeddingService] ❌ Failed to save embedding: {str(e)}")
            raise
            
        return True
