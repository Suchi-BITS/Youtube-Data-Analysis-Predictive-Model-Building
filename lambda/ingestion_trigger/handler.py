"""
Lambda Function: S3 Ingestion Trigger
Purpose: Triggered when new files land in S3 raw bucket, validates and processes them
"""

import json
import boto3
import logging
from datetime import datetime
from typing import Dict, Any
import os

# Initialize clients
s3_client = boto3.client('s3')
glue_client = boto3.client('glue')
sns_client = boto3.client('sns')

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
GLUE_DATABASE = os.environ.get('GLUE_DATABASE_NAME', 'youtube_analytics_db')
SNS_TOPIC_ARN = os.environ.get('SNS_ALERT_TOPIC_ARN')
PROCESSED_BUCKET = os.environ.get('S3_PROCESSED_BUCKET')


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main handler function triggered by S3 events
    
    Args:
        event: S3 event notification
        context: Lambda context
        
    Returns:
        Response dict with status and details
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Extract S3 event details
        for record in event['Records']:
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            event_time = record['eventTime']
            
            logger.info(f"Processing file: s3://{bucket}/{key}")
            
            # Validate file
            validation_result = validate_file(bucket, key)
            
            if validation_result['valid']:
                logger.info(f"File validation passed for {key}")
                
                # Trigger Glue crawler or ETL job
                trigger_result = trigger_etl_processing(bucket, key)
                
                # Send success notification
                send_notification(
                    subject="Data Ingestion Success",
                    message=f"Successfully ingested and validated file: {key}",
                    severity="INFO"
                )
                
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': 'File processed successfully',
                        'file': key,
                        'validation': validation_result,
                        'processing': trigger_result
                    })
                }
            else:
                logger.error(f"File validation failed for {key}: {validation_result['errors']}")
                
                # Send failure notification
                send_notification(
                    subject="Data Ingestion Validation Failed",
                    message=f"Validation failed for file: {key}. Errors: {validation_result['errors']}",
                    severity="ERROR"
                )
                
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'message': 'File validation failed',
                        'file': key,
                        'errors': validation_result['errors']
                    })
                }
                
    except Exception as e:
        logger.error(f"Error processing S3 event: {str(e)}", exc_info=True)
        
        send_notification(
            subject="Data Ingestion Error",
            message=f"Error processing file: {str(e)}",
            severity="CRITICAL"
        )
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Internal error',
                'error': str(e)
            })
        }


def validate_file(bucket: str, key: str) -> Dict[str, Any]:
    """
    Validate uploaded file for schema, format, and completeness
    
    Args:
        bucket: S3 bucket name
        key: S3 object key
        
    Returns:
        Dict with validation status and errors
    """
    errors = []
    
    try:
        # Get file metadata
        response = s3_client.head_object(Bucket=bucket, Key=key)
        file_size = response['ContentLength']
        
        # Check file size
        if file_size == 0:
            errors.append("File is empty")
        
        # Check file extension
        valid_extensions = ['.csv', '.json', '.parquet']
        if not any(key.endswith(ext) for ext in valid_extensions):
            errors.append(f"Invalid file extension. Expected one of {valid_extensions}")
        
        # For CSV files, check basic structure
        if key.endswith('.csv'):
            # Get first few bytes to validate
            obj = s3_client.get_object(Bucket=bucket, Key=key, Range='bytes=0-1024')
            content = obj['Body'].read().decode('utf-8')
            
            # Check if file has header
            lines = content.split('\n')
            if len(lines) < 2:
                errors.append("CSV file must have at least header and one data row")
            
            # Basic schema check for YouTube data
            expected_columns = ['video_id', 'title', 'channel_title', 'category_id', 
                              'publish_time', 'views', 'likes', 'dislikes', 'comment_count']
            
            if lines:
                header = lines[0].lower()
                missing_cols = [col for col in expected_columns if col not in header]
                if missing_cols:
                    errors.append(f"Missing required columns: {missing_cols}")
        
        logger.info(f"Validation completed for {key}. Errors: {errors}")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'file_size': file_size,
            'validation_timestamp': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error validating file {key}: {str(e)}")
        return {
            'valid': False,
            'errors': [f"Validation error: {str(e)}"]
        }


def trigger_etl_processing(bucket: str, key: str) -> Dict[str, Any]:
    """
    Trigger Glue ETL job or crawler to process the validated file
    
    Args:
        bucket: S3 bucket name
        key: S3 object key
        
    Returns:
        Dict with trigger status
    """
    try:
        # Start Glue crawler to catalog new data
        try:
            response = glue_client.start_crawler(Name='youtube_raw_crawler')
            logger.info(f"Started Glue crawler: {response}")
            
            return {
                'triggered': True,
                'crawler_name': 'youtube_raw_crawler',
                'job_run_id': response.get('ResponseMetadata', {}).get('RequestId')
            }
        except glue_client.exceptions.CrawlerRunningException:
            logger.info("Crawler already running")
            return {
                'triggered': False,
                'message': 'Crawler already running'
            }
            
    except Exception as e:
        logger.error(f"Error triggering ETL processing: {str(e)}")
        return {
            'triggered': False,
            'error': str(e)
        }


def send_notification(subject: str, message: str, severity: str = "INFO"):
    """
    Send SNS notification for monitoring and alerts
    
    Args:
        subject: Notification subject
        message: Notification message
        severity: Severity level (INFO, WARNING, ERROR, CRITICAL)
    """
    if not SNS_TOPIC_ARN:
        logger.warning("SNS_TOPIC_ARN not configured, skipping notification")
        return
    
    try:
        response = sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f"[{severity}] {subject}",
            Message=json.dumps({
                'severity': severity,
                'subject': subject,
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            }, indent=2)
        )
        logger.info(f"Notification sent: {response['MessageId']}")
    except Exception as e:
        logger.error(f"Error sending notification: {str(e)}")
