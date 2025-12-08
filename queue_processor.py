"""
Custom Queue Processor for Embedding Service
Polls Azure Storage Queue and processes embedding requests
Designed for Azure Container Apps with scale-to-zero support
"""
import os
import json
import time
import logging
import sys
from azure.storage.queue import QueueClient
from azure.identity import DefaultAzureCredential
from shared.global_embedding_service import EmbeddingService

# Configure logging - force unbuffered output for Container Apps
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)
logger = logging.getLogger(__name__)

# Also configure Azure SDK logging to see storage operations
azure_logger = logging.getLogger('azure')
azure_logger.setLevel(logging.WARNING)  # Reduce Azure SDK noise

# Configuration from environment variables
STORAGE_ACCOUNT_NAME = os.getenv('AzureWebJobsStorage__accountName', 'futureofthejobsearcb26e')
QUEUE_NAME = os.getenv('QUEUE_NAME', 'embedding-requests')
POISON_QUEUE_NAME = os.getenv('POISON_QUEUE_NAME', 'embedding-requests-poison')
MAX_DEQUEUE_COUNT = int(os.getenv('MAX_DEQUEUE_COUNT', '3'))
POLL_INTERVAL_SECONDS = int(os.getenv('POLL_INTERVAL_SECONDS', '2'))
VISIBILITY_TIMEOUT_SECONDS = int(os.getenv('VISIBILITY_TIMEOUT_SECONDS', '300'))  # 5 minutes
MAX_MESSAGES = int(os.getenv('MAX_MESSAGES', '1'))

class QueueProcessor:
    """Processes embedding requests from Azure Storage Queue"""
    
    def __init__(self):
        """Initialize queue clients with managed identity authentication"""
        print("========== QUEUE PROCESSOR INITIALIZING ==========", flush=True)
        logger.info("========== QUEUE PROCESSOR INITIALIZING ==========")
        logger.info(f"Storage Account: {STORAGE_ACCOUNT_NAME}")
        logger.info(f"Queue: {QUEUE_NAME}")
        logger.info(f"Poison Queue: {POISON_QUEUE_NAME}")
        logger.info(f"Max Dequeue Count: {MAX_DEQUEUE_COUNT}")
        logger.info(f"Poll Interval: {POLL_INTERVAL_SECONDS}s")
        sys.stdout.flush()
        
        # Use managed identity for authentication
        credential = DefaultAzureCredential()
        queue_url = f"https://{STORAGE_ACCOUNT_NAME}.queue.core.windows.net/{QUEUE_NAME}"
        poison_queue_url = f"https://{STORAGE_ACCOUNT_NAME}.queue.core.windows.net/{POISON_QUEUE_NAME}"
        
        self.queue_client = QueueClient.from_queue_url(queue_url, credential=credential)
        self.poison_queue_client = QueueClient.from_queue_url(poison_queue_url, credential=credential)
        
        print("✓ Queue clients initialized successfully", flush=True)
        logger.info("✓ Queue clients initialized successfully")
        logger.info("========== QUEUE PROCESSOR READY ==========")
        sys.stdout.flush()
    
    def process_message(self, message):
        """
        Process a single queue message
        
        Args:
            message: Azure Storage Queue message object
            
        Returns:
            bool: True if processing succeeded, False otherwise
        """
        message_id = message.id
        dequeue_count = message.dequeue_count
        
        logger.info(f"========== PROCESSING MESSAGE {message_id} ==========")
        logger.info(f"Dequeue count: {dequeue_count}/{MAX_DEQUEUE_COUNT}")
        logger.info(f"Insertion time: {message.inserted_on}")
        
        try:
            # Parse message content
            raw_content = message.content
            logger.info(f"Raw message content: {raw_content}")
            
            try:
                message_body = json.loads(raw_content)
                logger.info(f"Parsed message: {json.dumps(message_body)}")
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON PARSE ERROR: {str(e)}")
                logger.error(f"Invalid JSON content: {raw_content}")
                # Move to poison queue immediately - malformed JSON won't fix itself
                self._move_to_poison_queue(message, f"Invalid JSON: {str(e)}")
                return False
            
            # Validate required fields
            entity_type = message_body.get('entityType')
            entity_id = message_body.get('entityId')
            
            logger.info(f"Entity Type: {entity_type}, Entity ID: {entity_id}")
            
            if not entity_type or not entity_id:
                error_msg = f"Missing required fields. entityType={entity_type}, entityId={entity_id}"
                logger.error(f"❌ VALIDATION ERROR: {error_msg}")
                self._move_to_poison_queue(message, error_msg)
                return False
            
            # Validate entity type
            if entity_type not in ['Candidate', 'Position']:
                error_msg = f"Invalid entity type: {entity_type}. Must be 'Candidate' or 'Position'"
                logger.error(f"❌ VALIDATION ERROR: {error_msg}")
                self._move_to_poison_queue(message, error_msg)
                return False
            
            # Validate entity ID is numeric
            try:
                entity_id_int = int(entity_id)
                if entity_id_int <= 0:
                    raise ValueError("Entity ID must be positive")
            except (ValueError, TypeError) as e:
                error_msg = f"Invalid entity ID: {entity_id}. Must be a positive integer"
                logger.error(f"❌ VALIDATION ERROR: {error_msg}")
                self._move_to_poison_queue(message, error_msg)
                return False
            
            logger.info(f"✓ Validation passed for {entity_type} {entity_id}")
            
            # Process the embedding
            logger.info(f"Triggering embedding generation for {entity_type} {entity_id}...")
            success = EmbeddingService.trigger_embedding(entity_type, str(entity_id))
            
            if success:
                logger.info(f"✓ Successfully processed {entity_type} {entity_id}")
                logger.info(f"========== MESSAGE {message_id} COMPLETED ==========")
                return True
            else:
                logger.error(f"❌ Failed to process {entity_type} {entity_id}")
                return False
                
        except Exception as e:
            logger.error(f"❌ UNEXPECTED ERROR processing message {message_id}: {str(e)}", exc_info=True)
            return False
    
    def _move_to_poison_queue(self, message, error_reason):
        """
        Move a message to the poison queue
        
        Args:
            message: Original queue message
            error_reason: Reason for moving to poison queue
        """
        try:
            # Create poison queue message with metadata
            poison_message = {
                "originalMessage": json.loads(message.content) if message.content else None,
                "errorReason": error_reason,
                "originalMessageId": message.id,
                "originalDequeueCount": message.dequeue_count,
                "originalInsertionTime": str(message.inserted_on),
                "movedToPoisonAt": time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
            }
            
            self.poison_queue_client.send_message(json.dumps(poison_message))
            logger.info(f"✓ Moved message {message.id} to poison queue: {error_reason}")
        except Exception as e:
            logger.error(f"❌ Failed to move message to poison queue: {str(e)}", exc_info=True)
    
    def run(self):
        """
        Main processing loop - polls queue and processes messages
        """
        logger.info("========== STARTING QUEUE PROCESSOR LOOP ==========")
        
        while True:
            try:
                # Receive messages from queue
                messages = self.queue_client.receive_messages(
                    max_messages=MAX_MESSAGES,
                    visibility_timeout=VISIBILITY_TIMEOUT_SECONDS
                )
                
                message_processed = False
                
                for message in messages:
                    message_processed = True
                    print(f"📨 Received message: {message.id} (dequeue count: {message.dequeue_count})", flush=True)
                    
                    # Check if message has exceeded max dequeue count
                    if message.dequeue_count > MAX_DEQUEUE_COUNT:
                        logger.warning(f"⚠️ Message {message.id} exceeded max dequeue count ({message.dequeue_count} > {MAX_DEQUEUE_COUNT})")
                        self._move_to_poison_queue(
                            message, 
                            f"Exceeded max dequeue count: {message.dequeue_count}"
                        )
                        self.queue_client.delete_message(message)
                        continue
                    
                    # Process the message
                    success = self.process_message(message)
                    
                    if success:
                        # Delete message from queue on success
                        self.queue_client.delete_message(message)
                        print(f"✅ DELETED message {message.id} from queue", flush=True)
                        logger.info(f"✓ Deleted message {message.id} from queue")
                    else:
                        # Message will become visible again after visibility timeout
                        # and can be retried up to MAX_DEQUEUE_COUNT times
                        print(f"⚠️  FAILED - Message {message.id} will retry (attempt {message.dequeue_count}/{MAX_DEQUEUE_COUNT})", flush=True)
                        logger.warning(f"⚠️ Message {message.id} will be retried (attempt {message.dequeue_count}/{MAX_DEQUEUE_COUNT})")
                        
                        # If this was the last attempt, move to poison queue
                        if message.dequeue_count >= MAX_DEQUEUE_COUNT:
                            self._move_to_poison_queue(
                                message,
                                f"Failed after {message.dequeue_count} attempts"
                            )
                            self.queue_client.delete_message(message)
                
                if not message_processed:
                    # No messages in queue - sleep before polling again
                    # This allows the container to scale to zero when idle
                    time.sleep(POLL_INTERVAL_SECONDS)
                    
            except KeyboardInterrupt:
                logger.info("========== QUEUE PROCESSOR SHUTTING DOWN (KeyboardInterrupt) ==========")
                break
            except Exception as e:
                logger.error(f"❌ ERROR in main loop: {str(e)}", exc_info=True)
                # Wait before retrying to avoid tight error loop
                time.sleep(5)

def main():
    """Main entry point"""
    try:
        processor = QueueProcessor()
        processor.run()
    except Exception as e:
        logger.error(f"❌ FATAL ERROR: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
