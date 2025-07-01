import azure.functions as func
import logging
import json
import os
from datetime import datetime
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential
from collections import defaultdict
import threading
import time

app = func.FunctionApp()

# Configuration from environment variables
STORAGE_ACCOUNT_NAME = os.environ.get('STORAGE_ACCOUNT_NAME')
EVENTHUB_NAMESPACE = os.environ.get('EVENTHUB_NAMESPACE')
EVENTHUB_NAME = os.environ.get('EVENTHUB_NAME')
FLUSH_INTERVAL_SECONDS = int(os.environ.get('FLUSH_INTERVAL_SECONDS', '300'))  # 5 minutes default
MAX_LINES_PER_FLUSH = int(os.environ.get('MAX_LINES_PER_FLUSH', '1000'))  # 1000 lines default

# Initialize Azure credential for managed identity
credential = DefaultAzureCredential()

# In-memory buffer to store data before flushing
data_buffer = defaultdict(list)
buffer_lock = threading.Lock()
last_flush_time = time.time()

def get_container_name(line_data):
    """
    Parse the line and return the container name in format: group-id
    Expected format: "1234567, test-api-group1, <encrypted values>"
    """
    try:
        parts = [part.strip() for part in line_data.split(',', 2)]
        if len(parts) >= 2:
            id_part = parts[0]
            group_part = parts[1]
            return f"{group_part}-{id_part}"
        else:
            logging.warning(f"Invalid data format: {line_data}")
            return "invalid-data"
    except Exception as e:
        logging.error(f"Error parsing line data: {e}")
        return "error-data"

def flush_to_blob_storage():
    """
    Flush all buffered data to respective blob containers
    """
    global data_buffer, last_flush_time
    
    if not STORAGE_ACCOUNT_NAME:
        logging.error("STORAGE_ACCOUNT_NAME not configured")
        return
    
    try:
        # Use managed identity to connect to blob storage
        account_url = f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net"
        blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)
        
        with buffer_lock:
            if not data_buffer:
                return
            
            # Create a copy of the buffer and clear it
            buffer_copy = dict(data_buffer)
            data_buffer.clear()
            last_flush_time = time.time()
        
        # Process each container's data
        for container_name, lines in buffer_copy.items():
            try:
                # Create container if it doesn't exist
                container_client = blob_service_client.get_container_client(container_name)
                try:
                    container_client.create_container()
                    logging.info(f"Created container: {container_name}")
                except Exception:
                    # Container might already exist
                    pass
                
                # Create blob name with timestamp
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
                blob_name = f"data_{timestamp}.txt"
                
                # Combine all lines into a single string
                blob_content = '\n'.join(lines)
                
                # Upload to blob
                blob_client = container_client.get_blob_client(blob_name)
                blob_client.upload_blob(blob_content, overwrite=True)
                
                logging.info(f"Uploaded {len(lines)} lines to {container_name}/{blob_name}")
                
            except Exception as e:
                logging.error(f"Error uploading to container {container_name}: {e}")
                
    except Exception as e:
        logging.error(f"Error in flush_to_blob_storage: {e}")

def should_flush():
    """
    Check if we should flush based on time or line count
    """
    current_time = time.time()
    time_exceeded = (current_time - last_flush_time) >= FLUSH_INTERVAL_SECONDS
    
    total_lines = sum(len(lines) for lines in data_buffer.values())
    lines_exceeded = total_lines >= MAX_LINES_PER_FLUSH
    
    return time_exceeded or lines_exceeded

@app.event_hub_message_trigger(
    arg_name="azeventhub", 
    event_hub_name="%EVENTHUB_NAME%",  # Reference environment variable
    connection="EventHubConnection__fullyQualifiedNamespace"  # Managed identity connection
)
def eventhub_trigger(azeventhub: func.EventHubEvent):
    """
    Azure Function triggered by Event Hub messages
    """
    try:
        # Get the message body
        message_body = azeventhub.get_body().decode('utf-8')
        logging.info(f"Received message: {message_body}")
        
        # Parse the container name from the message
        container_name = get_container_name(message_body)
        
        # Add to buffer
        with buffer_lock:
            data_buffer[container_name].append(message_body)
        
        # Check if we should flush
        if should_flush():
            logging.info("Flushing data to blob storage")
            flush_to_blob_storage()
            
    except Exception as e:
        logging.error(f"Error processing Event Hub message: {e}")

@app.timer_trigger(
    schedule="0 */5 * * * *",  # Every 5 minutes
    arg_name="mytimer", 
    run_on_startup=False
)
def timer_flush(mytimer: func.TimerRequest) -> None:
    """
    Timer function to ensure data is flushed every 5 minutes even if line count isn't reached
    """
    logging.info("Timer triggered - checking for data to flush")
    
    with buffer_lock:
        total_lines = sum(len(lines) for lines in data_buffer.values())
    
    if total_lines > 0:
        logging.info(f"Timer flush: {total_lines} lines pending")
        flush_to_blob_storage()
    else:
        logging.info("Timer flush: No data to flush")

# Health check endpoint
@app.route(route="health", auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """
    Simple health check endpoint
    """
    return func.HttpResponse(
        json.dumps({
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "config": {
                "flush_interval_seconds": FLUSH_INTERVAL_SECONDS,
                "max_lines_per_flush": MAX_LINES_PER_FLUSH
            }
        }),
        mimetype="application/json"
    )