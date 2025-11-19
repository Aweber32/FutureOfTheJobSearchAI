"""
Azure Functions App - Embedding Service
HTTP trigger endpoint for generating embeddings from candidate and position data
"""
import logging
import json
import azure.functions as func
from shared.global_embedding_service import EmbeddingService

# Create the function app
app = func.FunctionApp()

@app.route(route="trigger_embedding", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def trigger_embedding(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP trigger function for generating embeddings.
    
    Expected JSON body:
    {
        "entityType": "Candidate" or "Position",
        "entityId": "123"
    }
    
    Returns:
    {
        "status": "success",
        "entityType": "Candidate",
        "entityId": "123",
        "embedding_dimension": 768,
        "model_version": "v1"
    }
    """
    logging.info('Embedding trigger function processing a request.')
    
    try:
        # Parse request body
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({
                    "status": "error",
                    "message": "Invalid JSON in request body"
                }),
                status_code=400,
                mimetype="application/json"
            )
        
        # Validate required fields
        entity_type = req_body.get('entityType')
        entity_id = req_body.get('entityId')
        
        if not entity_type or not entity_id:
            return func.HttpResponse(
                json.dumps({
                    "status": "error",
                    "message": "Missing required fields: entityType and entityId"
                }),
                status_code=400,
                mimetype="application/json"
            )
        
        # Validate entity type
        if entity_type not in ['Candidate', 'Position']:
            return func.HttpResponse(
                json.dumps({
                    "status": "error",
                    "message": "entityType must be either 'Candidate' or 'Position'"
                }),
                status_code=400,
                mimetype="application/json"
            )
        
        logging.info(f'Processing embedding for {entity_type} ID: {entity_id}')
        
        # Generate embedding with timeout awareness
        import time
        start_time = time.time()
        
        try:
            result = EmbeddingService.trigger_embedding(entity_type, str(entity_id))
            elapsed = time.time() - start_time
            logging.info(f'Embedding generated in {elapsed:.2f} seconds')
            
            return func.HttpResponse(
                json.dumps(result),
                status_code=200,
                mimetype="application/json"
            )
        except TimeoutError:
            elapsed = time.time() - start_time
            logging.error(f'Timeout after {elapsed:.2f} seconds')
            return func.HttpResponse(
                json.dumps({
                    "status": "error",
                    "message": f"Request timed out after {elapsed:.2f} seconds. Try again or use smaller batch."
                }),
                status_code=504,  # Gateway Timeout
                mimetype="application/json"
            )
        
    except Exception as e:
        logging.error(f'Error processing embedding: {str(e)}', exc_info=True)
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "message": str(e),
                "type": type(e).__name__
            }),
            status_code=500,
            mimetype="application/json"
        )
