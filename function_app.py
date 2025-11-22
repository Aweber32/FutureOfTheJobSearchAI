"""
Azure Functions App - Embedding Service
Queue trigger for generating embeddings from candidate and position data
Optimized for Container Apps with auto-scaling
"""
import logging
import json
import azure.functions as func
from shared.global_embedding_service import EmbeddingService

# Create the function app
app = func.FunctionApp()

@app.queue_trigger(arg_name="msg", queue_name="embedding-requests", connection="AzureWebJobsStorage")
def trigger_embedding(msg: func.QueueMessage) -> None:
    """
    Queue trigger function for generating embeddings.
    
    Expected Queue Message (JSON):
    {
        "entityType": "Candidate" or "Position",
        "entityId": "123"
    }
    
    Processes the message and saves embedding to database.
    Auto-scales from 0 to 5 replicas based on queue depth.
    """
    logging.info(f'Processing queue message: {msg.id}')
    
    try:
        # Parse queue message
        try:
            message_body = json.loads(msg.get_body().decode('utf-8'))
        except (ValueError, json.JSONDecodeError) as e:
            logging.error(f'Invalid JSON in queue message: {str(e)}')
            # Message will be moved to poison queue after max retries
            raise
        
        # Validate required fields
        entity_type = message_body.get('entityType')
        entity_id = message_body.get('entityId')
        
        if not entity_type or not entity_id:
            logging.error(f'Missing required fields in message: {message_body}')
            raise ValueError("Missing required fields: entityType and entityId")
        
        # Validate entity type (whitelist)
        if entity_type not in ['Candidate', 'Position']:
            logging.error(f'Invalid entity type: {entity_type}')
            raise ValueError("entityType must be either 'Candidate' or 'Position'")
        
        # Validate entity_id is numeric (prevent SQL injection attempts)
        try:
            entity_id_int = int(entity_id)
            if entity_id_int <= 0:
                raise ValueError("ID must be positive")
        except (ValueError, TypeError) as e:
            logging.error(f'Invalid entity ID: {entity_id}')
            raise ValueError("entityId must be a positive integer")
        
        # Audit log
        logging.info(f'Processing embedding for {entity_type} ID: {entity_id}')
        
        # Generate embedding with timing
        import time
        start_time = time.time()
        
        result = EmbeddingService.trigger_embedding(entity_type, str(entity_id))
        elapsed = time.time() - start_time
        
        logging.info(f'Successfully generated embedding in {elapsed:.2f} seconds')
        logging.info(f'Result: {json.dumps(result)}')
        
    except Exception as e:
        logging.error(f'Error processing embedding: {str(e)}', exc_info=True)
        # Re-raise to trigger retry (message will retry up to maxDequeueCount)
        raise
