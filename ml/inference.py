"""
ML Inference Script for YouTube Video Performance Prediction
Purpose: Generate predictions for new videos using trained models
"""

import os
import json
import boto3
import pickle
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any

# AWS clients
s3_client = boto3.client('s3')

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
MODEL_BUCKET = os.environ.get('MODEL_BUCKET', 'youtube-analytics-models')
CURATED_BUCKET = os.environ.get('CURATED_BUCKET', 'youtube-analytics-curated-gold')


class VideoPerformanceInference:
    """Inference engine for video performance predictions"""
    
    def __init__(self, model_name: str = 'youtube_performance_predictor'):
        """Initialize inference engine"""
        self.model_name = model_name
        self.model = None
        self.scaler = None
        self.metadata = None
        
        logger.info(f"Initializing inference engine for model: {model_name}")
        self.load_model()
    
    def load_model(self):
        """Load trained model and scaler from S3"""
        logger.info(f"Loading model: {self.model_name}")
        
        try:
            prefix = f"models/{self.model_name}/"
            response = s3_client.list_objects_v2(
                Bucket=MODEL_BUCKET,
                Prefix=prefix,
                Delimiter='/'
            )
            
            versions = [p['Prefix'] for p in response.get('CommonPrefixes', [])]
            if not versions:
                raise ValueError(f"No models found for {self.model_name}")
            
            latest_version = sorted(versions)[-1]
            logger.info(f"Loading latest version: {latest_version}")
            
            model_key = f"{latest_version}model.pkl"
            model_path = f"/tmp/{self.model_name}_model.pkl"
            s3_client.download_file(MODEL_BUCKET, model_key, model_path)
            
            with open(model_path, 'rb') as f:
                self.model = pickle.load(f)
            
            scaler_key = f"{latest_version}scaler.pkl"
            scaler_path = f"/tmp/{self.model_name}_scaler.pkl"
            s3_client.download_file(MODEL_BUCKET, scaler_key, scaler_path)
            
            with open(scaler_path, 'rb') as f:
                self.scaler = pickle.load(f)
            
            metadata_key = f"{latest_version}metadata.json"
            metadata_path = f"/tmp/{self.model_name}_metadata.json"
            s3_client.download_file(MODEL_BUCKET, metadata_key, metadata_path)
            
            with open(metadata_path, 'r') as f:
                self.metadata = json.load(f)
            
            logger.info(f"Model loaded successfully")
            
        except Exception as e:
            logger.error(f"Error loading model: {str(e)}", exc_info=True)
            raise
    
    def prepare_features(self, video_data: Dict[str, Any]) -> pd.DataFrame:
        """Prepare features for inference"""
        features = {
            'publish_hour': video_data.get('publish_hour', 12),
            'publish_day_of_week': video_data.get('publish_day_of_week', 3),
            'publish_month': video_data.get('publish_month', 6),
            'is_weekend': 1 if video_data.get('publish_day_of_week', 3) in [1, 7] else 0,
            'title_length': len(video_data.get('title', '')),
            'title_word_count': len(video_data.get('title', '').split()),
            'title_has_question': 1 if '?' in video_data.get('title', '') else 0,
            'title_has_exclamation': 1 if '!' in video_data.get('title', '') else 0,
            'description_length': len(video_data.get('description', '')),
            'tag_count': len(video_data.get('tags', [])),
            'category_id': video_data.get('category_id', 24),
        }
        
        features['hour_sin'] = np.sin(2 * np.pi * features['publish_hour'] / 24)
        features['hour_cos'] = np.cos(2 * np.pi * features['publish_hour'] / 24)
        
        df = pd.DataFrame([features])
        df = df.fillna(0)
        
        return df
    
    def predict(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate prediction for a video"""
        X = self.prepare_features(video_data)
        X_scaled = self.scaler.transform(X)
        prediction = self.model.predict(X_scaled)[0]
        
        return {
            'video_id': video_data.get('video_id'),
            'predicted_views': float(prediction),
            'prediction_timestamp': datetime.utcnow().isoformat(),
            'model_version': self.metadata.get('timestamp')
        }


def main():
    """Main function for testing"""
    sample_video = {
        'video_id': 'test123',
        'title': 'Amazing Tutorial: How to Build Data Pipelines!',
        'description': 'Learn how to build production-grade data pipelines.',
        'tags': ['tutorial', 'aws', 'data'],
        'category_id': 28,
        'publish_hour': 14,
        'publish_day_of_week': 3,
        'publish_month': 6
    }
    
    inference = VideoPerformanceInference()
    prediction = inference.predict(sample_video)
    
    print(json.dumps(prediction, indent=2))


if __name__ == "__main__":
    main()
