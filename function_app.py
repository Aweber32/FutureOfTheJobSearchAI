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
    logging.info(f'========== QUEUE TRIGGER STARTED ==========')
    logging.info(f'Processing queue message ID: {msg.id}')
    logging.info(f'Message dequeue count: {msg.dequeue_count}')
    logging.info(f'Message insertion time: {msg.insertion_time}')
    
    try:
        # Parse queue message
        try:
            raw_body = msg.get_body().decode('utf-8')
            logging.info(f'Raw message body: {raw_body}')
            message_body = json.loads(raw_body)
            logging.info(f'Parsed message body: {json.dumps(message_body)}')
        except (ValueError, json.JSONDecodeError) as e:
            logging.error(f'❌ PARSE ERROR: Invalid JSON in queue message: {str(e)}')
            logging.error(f'Raw message content: {msg.get_body()}')
            # Message will be moved to poison queue after max retries
            raise
        
        # Validate required fields
        entity_type = message_body.get('entityType')
        entity_id = message_body.get('entityId')
        
        logging.info(f'Extracted fields - entityType: {entity_type}, entityId: {entity_id}')
        
        if not entity_type or not entity_id:
            logging.error(f'❌ VALIDATION ERROR: Missing required fields in message: {message_body}')
            raise ValueError("Missing required fields: entityType and entityId")
        
        # Validate entity type (whitelist)
        if entity_type not in ['Candidate', 'Position']:
            logging.error(f'❌ VALIDATION ERROR: Invalid entity type: {entity_type}')
            logging.error(f'Allowed values: Candidate, Position')
            raise ValueError("entityType must be either 'Candidate' or 'Position'")
        
        # Validate entity_id is numeric (prevent SQL injection attempts)
        try:
            entity_id_int = int(entity_id)
            if entity_id_int <= 0:
                raise ValueError("ID must be positive")
            logging.info(f'✓ Validation passed for {entity_type} ID: {entity_id_int}')
        except (ValueError, TypeError) as e:
            logging.error(f'❌ VALIDATION ERROR: Invalid entity ID: {entity_id} - {str(e)}')
            raise ValueError("entityId must be a positive integer")
        
        # Audit log
        logging.info(f'▶ Starting embedding generation for {entity_type} ID: {entity_id}')
        
        # Generate embedding with timing
        import time
        start_time = time.time()
        
        try:
            result = EmbeddingService.trigger_embedding(entity_type, str(entity_id))
            elapsed = time.time() - start_time
            
            logging.info(f'✓ Successfully generated embedding in {elapsed:.2f} seconds')
            logging.info(f'Result: {json.dumps(result)}')
            logging.info(f'========== QUEUE TRIGGER COMPLETED ==========')
        except Exception as embedding_error:
            elapsed = time.time() - start_time
            logging.error(f'❌ EMBEDDING ERROR after {elapsed:.2f}s: {str(embedding_error)}')
            logging.error(f'Error type: {type(embedding_error).__name__}')
            logging.error(f'Entity details: type={entity_type}, id={entity_id}')
            raise
        
    except Exception as e:
        logging.error(f'❌ FATAL ERROR in queue trigger: {str(e)}', exc_info=True)
        logging.error(f'Message will be retried (dequeue count: {msg.dequeue_count}/3)')
        logging.error(f'========== QUEUE TRIGGER FAILED ==========')
        # Re-raise to trigger retry (message will retry up to maxDequeueCount)
        raise
