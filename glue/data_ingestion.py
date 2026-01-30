"""
Data Ingestion Script: Download YouTube Dataset from Kaggle
Purpose: Download and upload YouTube trending videos dataset to S3 raw bucket
"""

import os
import sys
import boto3
import logging
import pandas as pd
from datetime import datetime
import json

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# AWS clients
s3_client = boto3.client('s3')

# Configuration
RAW_BUCKET = os.environ.get('S3_RAW_BUCKET', 'youtube-analytics-raw-bronze')
RAW_PREFIX = os.environ.get('RAW_DATA_PREFIX', 'raw/youtube/')


class YouTubeDataIngestion:
    """Handle YouTube dataset ingestion from various sources"""
    
    def __init__(self):
        """Initialize ingestion handler"""
        logger.info("Initializing YouTube data ingestion")
        self.s3_client = s3_client
    
    def download_kaggle_dataset(self, dataset_name: str = 'datasnaek/youtube-new'):
        """
        Download YouTube dataset from Kaggle
        
        Args:
            dataset_name: Kaggle dataset identifier
            
        Note: Requires kaggle API credentials in ~/.kaggle/kaggle.json
        """
        logger.info(f"Downloading dataset from Kaggle: {dataset_name}")
        
        try:
            import kaggle
            
            # Download dataset
            kaggle.api.dataset_download_files(
                dataset_name,
                path='./data/raw/',
                unzip=True
            )
            
            logger.info("Dataset downloaded successfully")
            return './data/raw/'
            
        except Exception as e:
            logger.error(f"Error downloading from Kaggle: {str(e)}")
            raise
    
    def load_sample_data(self):
        """
        Create sample YouTube data for testing
        
        Returns:
            DataFrame with sample data
        """
        logger.info("Creating sample YouTube data")
        
        import numpy as np
        from datetime import timedelta
        
        # Sample data structure matching YouTube trending videos dataset
        num_records = 1000
        
        # Categories: Entertainment(24), Music(10), Gaming(20), Science & Tech(28), etc.
        categories = [1, 10, 15, 17, 19, 20, 22, 23, 24, 25, 26, 27, 28, 29]
        
        base_date = datetime(2024, 1, 1)
        
        data = {
            'video_id': [f'vid_{i:06d}' for i in range(num_records)],
            'title': [f'Video Title {i} - Amazing Content!' for i in range(num_records)],
            'channel_title': [f'Channel_{i % 50}' for i in range(num_records)],
            'category_id': np.random.choice(categories, num_records),
            'publish_time': [(base_date + timedelta(days=np.random.randint(0, 365), 
                                                     hours=np.random.randint(0, 24))).strftime('%Y-%m-%dT%H:%M:%S.000Z') 
                            for _ in range(num_records)],
            'tags': ['tutorial|howto|learning' if i % 3 == 0 else 'entertainment|fun' 
                    for i in range(num_records)],
            'views': np.random.lognormal(10, 2, num_records).astype(int),
            'likes': np.random.lognormal(8, 2, num_records).astype(int),
            'dislikes': np.random.lognormal(5, 1.5, num_records).astype(int),
            'comment_count': np.random.lognormal(6, 1.8, num_records).astype(int),
            'thumbnail_link': [f'https://i.ytimg.com/vi/vid_{i:06d}/default.jpg' 
                              for i in range(num_records)],
            'comments_disabled': np.random.choice([True, False], num_records, p=[0.1, 0.9]),
            'ratings_disabled': np.random.choice([True, False], num_records, p=[0.05, 0.95]),
            'video_error_or_removed': np.random.choice([True, False], num_records, p=[0.02, 0.98]),
            'description': [f'This is a description for video {i}. Learn amazing things!' 
                           for i in range(num_records)]
        }
        
        df = pd.DataFrame(data)
        
        # Ensure non-negative values
        df['views'] = df['views'].abs()
        df['likes'] = df['likes'].abs()
        df['dislikes'] = df['dislikes'].abs()
        df['comment_count'] = df['comment_count'].abs()
        
        logger.info(f"Created sample data with {len(df)} records")
        
        return df
    
    def upload_to_s3(self, df: pd.DataFrame, file_name: str = None):
        """
        Upload data to S3 raw bucket
        
        Args:
            df: DataFrame to upload
            file_name: Optional custom filename
        """
        if file_name is None:
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            file_name = f'youtube_trending_{timestamp}.csv'
        
        logger.info(f"Uploading data to S3: {file_name}")
        
        # Save locally first
        local_path = f'/tmp/{file_name}'
        df.to_csv(local_path, index=False)
        
        # Upload to S3
        s3_key = f"{RAW_PREFIX}{file_name}"
        
        try:
            self.s3_client.upload_file(
                local_path,
                RAW_BUCKET,
                s3_key,
                ExtraArgs={'ContentType': 'text/csv'}
            )
            
            logger.info(f"Data uploaded to s3://{RAW_BUCKET}/{s3_key}")
            
            # Add metadata
            metadata = {
                'record_count': str(len(df)),
                'upload_timestamp': datetime.utcnow().isoformat(),
                'columns': ','.join(df.columns.tolist()),
                'source': 'sample_data_generator'
            }
            
            self.s3_client.put_object_tagging(
                Bucket=RAW_BUCKET,
                Key=s3_key,
                Tagging={'TagSet': [
                    {'Key': k, 'Value': v} for k, v in metadata.items()
                ]}
            )
            
            return f"s3://{RAW_BUCKET}/{s3_key}"
            
        except Exception as e:
            logger.error(f"Error uploading to S3: {str(e)}")
            raise
    
    def ingest_from_youtube_api(self, api_key: str, max_results: int = 50):
        """
        Ingest data directly from YouTube Data API
        
        Args:
            api_key: YouTube Data API key
            max_results: Maximum number of videos to fetch
            
        Returns:
            DataFrame with video data
        """
        logger.info("Fetching data from YouTube Data API")
        
        try:
            from googleapiclient.discovery import build
            
            youtube = build('youtube', 'v3', developerKey=api_key)
            
            # Get trending videos
            request = youtube.videos().list(
                part='snippet,statistics,contentDetails',
                chart='mostPopular',
                regionCode='US',
                maxResults=max_results
            )
            
            response = request.execute()
            
            # Parse response
            videos = []
            for item in response['items']:
                video = {
                    'video_id': item['id'],
                    'title': item['snippet']['title'],
                    'channel_title': item['snippet']['channelTitle'],
                    'category_id': int(item['snippet']['categoryId']),
                    'publish_time': item['snippet']['publishedAt'],
                    'tags': '|'.join(item['snippet'].get('tags', [])),
                    'views': int(item['statistics'].get('viewCount', 0)),
                    'likes': int(item['statistics'].get('likeCount', 0)),
                    'dislikes': 0,  # YouTube API no longer provides dislikes
                    'comment_count': int(item['statistics'].get('commentCount', 0)),
                    'thumbnail_link': item['snippet']['thumbnails']['default']['url'],
                    'comments_disabled': not item['statistics'].get('commentCount'),
                    'ratings_disabled': False,
                    'video_error_or_removed': False,
                    'description': item['snippet']['description']
                }
                videos.append(video)
            
            df = pd.DataFrame(videos)
            logger.info(f"Fetched {len(df)} videos from YouTube API")
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching from YouTube API: {str(e)}")
            logger.info("Falling back to sample data")
            return self.load_sample_data()
    
    def validate_data(self, df: pd.DataFrame) -> bool:
        """
        Validate data before upload
        
        Args:
            df: DataFrame to validate
            
        Returns:
            True if valid, False otherwise
        """
        logger.info("Validating data")
        
        required_columns = [
            'video_id', 'title', 'channel_title', 'category_id',
            'publish_time', 'views', 'likes', 'comment_count'
        ]
        
        # Check required columns
        missing_cols = set(required_columns) - set(df.columns)
        if missing_cols:
            logger.error(f"Missing required columns: {missing_cols}")
            return False
        
        # Check for null values in critical columns
        null_counts = df[required_columns].isnull().sum()
        if null_counts.any():
            logger.warning(f"Null values found: {null_counts[null_counts > 0].to_dict()}")
        
        # Check data types
        if df['views'].dtype not in ['int64', 'int32', 'float64']:
            logger.error("Views column must be numeric")
            return False
        
        logger.info("Data validation passed")
        return True


def main():
    """Main ingestion workflow"""
    try:
        logger.info("Starting YouTube data ingestion")
        
        ingestion = YouTubeDataIngestion()
        
        # Option 1: Load sample data (for testing)
        logger.info("Using sample data for demonstration")
        df = ingestion.load_sample_data()
        
        # Option 2: Download from Kaggle (requires API key)
        # Uncomment to use:
        # data_path = ingestion.download_kaggle_dataset()
        # df = pd.read_csv(f"{data_path}/USvideos.csv")
        
        # Option 3: Fetch from YouTube API (requires API key)
        # Uncomment to use:
        # youtube_api_key = os.environ.get('YOUTUBE_API_KEY')
        # if youtube_api_key:
        #     df = ingestion.ingest_from_youtube_api(youtube_api_key, max_results=100)
        
        # Validate data
        if not ingestion.validate_data(df):
            logger.error("Data validation failed")
            sys.exit(1)
        
        # Upload to S3
        s3_path = ingestion.upload_to_s3(df)
        
        logger.info(f"Data ingestion completed successfully: {s3_path}")
        
        # Print summary
        print("\n" + "="*60)
        print("INGESTION SUMMARY")
        print("="*60)
        print(f"Records ingested: {len(df)}")
        print(f"S3 location: {s3_path}")
        print(f"Categories: {df['category_id'].nunique()}")
        print(f"Channels: {df['channel_title'].nunique()}")
        print(f"Date range: {df['publish_time'].min()} to {df['publish_time'].max()}")
        print("="*60 + "\n")
        
        return s3_path
        
    except Exception as e:
        logger.error(f"Error in ingestion workflow: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
