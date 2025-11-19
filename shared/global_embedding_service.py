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
        # Fetch text for embedding
        db = DBClient()
        profile_data = db.fetch_profile_text(entity_type, entity_id)
        text = profile_data["text"]  # Extract text from the dictionary

        # Generate embedding
        model = cls._load_model()
        vec = model.encode(text, show_progress_bar=False)
        vec_np = np.array(vec, dtype=np.float32)

        # Save embedding
        model_version = os.getenv("EMBEDDING_MODEL_VERSION", "v1")
        db.save_embedding(entity_type, entity_id, vec_np, model_version)
        logging.info(f"Saved embedding for {entity_type} {entity_id} with model version {model_version}")
        return True
