"""
Recommendation Engine for Optimal Video Posting Times
Purpose: Analyze historical data and recommend best posting times per channel/category
"""

import os
import json
import boto3
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

# AWS clients
s3_client = boto3.client('s3')
athena_client = boto3.client('athena')

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
CURATED_BUCKET = os.environ.get('CURATED_BUCKET', 'youtube-analytics-curated-gold')
ATHENA_DATABASE = os.environ.get('ATHENA_DATABASE', 'youtube_analytics_db')
ATHENA_OUTPUT_BUCKET = os.environ.get('ATHENA_OUTPUT_BUCKET', 'youtube-analytics-athena-results')


class PostingTimeRecommender:
    """Generate optimal posting time recommendations"""
    
    def __init__(self):
        """Initialize recommender"""
        logger.info("Initializing posting time recommender")
        self.posting_analysis = None
        self.recommendations = {}
    
    def load_posting_analysis(self) -> pd.DataFrame:
        """Load posting time analysis from Gold layer"""
        logger.info("Loading posting time analysis data")
        
        try:
            s3_path = f"s3://{CURATED_BUCKET}/gold/posting_time_analysis/"
            df = pd.read_parquet(s3_path)
            
            logger.info(f"Loaded {len(df)} posting time records")
            self.posting_analysis = df
            
            return df
            
        except Exception as e:
            logger.error(f"Error loading posting analysis: {str(e)}")
            raise
    
    def analyze_optimal_times_by_category(self, category_id: int, 
                                          top_n: int = 5) -> List[Dict]:
        """
        Find optimal posting times for a specific category
        
        Args:
            category_id: YouTube category ID
            top_n: Number of top time slots to recommend
            
        Returns:
            List of recommended time slots
        """
        logger.info(f"Analyzing optimal times for category {category_id}")
        
        if self.posting_analysis is None:
            self.load_posting_analysis()
        
        # Filter by category
        category_data = self.posting_analysis[
            self.posting_analysis['category_id'] == category_id
        ].copy()
        
        if len(category_data) == 0:
            logger.warning(f"No data found for category {category_id}")
            return []
        
        # Calculate composite score (weighted combination of metrics)
        category_data['composite_score'] = (
            0.4 * category_data['avg_views'] / category_data['avg_views'].max() +
            0.3 * category_data['avg_engagement_rate'] / category_data['avg_engagement_rate'].max() +
            0.3 * category_data['avg_viral_score'] / category_data['avg_viral_score'].max()
        )
        
        # Get top time slots
        top_times = category_data.nlargest(top_n, 'composite_score')
        
        recommendations = []
        for _, row in top_times.iterrows():
            recommendations.append({
                'hour': int(row['publish_hour']),
                'day_of_week': int(row['publish_day_of_week']),
                'day_name': self._get_day_name(int(row['publish_day_of_week'])),
                'avg_views': float(row['avg_views']),
                'avg_engagement': float(row['avg_engagement_rate']),
                'composite_score': float(row['composite_score']),
                'video_count': int(row['video_count']) if 'video_count' in row else 0
            })
        
        logger.info(f"Generated {len(recommendations)} recommendations for category {category_id}")
        
        return recommendations
    
    def analyze_optimal_times_by_channel(self, channel_title: str,
                                        top_n: int = 5) -> List[Dict]:
        """
        Find optimal posting times for a specific channel
        
        Args:
            channel_title: YouTube channel name
            top_n: Number of top time slots to recommend
            
        Returns:
            List of recommended time slots
        """
        logger.info(f"Analyzing optimal times for channel: {channel_title}")
        
        # Query historical performance by posting time for this channel
        query = f"""
        SELECT 
            EXTRACT(HOUR FROM publish_timestamp) as publish_hour,
            DAYOFWEEK(publish_date) as publish_day_of_week,
            COUNT(video_id) as video_count,
            AVG(views) as avg_views,
            AVG(engagement_rate) as avg_engagement_rate,
            AVG(viral_score) as avg_viral_score
        FROM youtube_videos_silver
        WHERE channel_title = '{channel_title}'
        GROUP BY EXTRACT(HOUR FROM publish_timestamp), DAYOFWEEK(publish_date)
        HAVING COUNT(video_id) >= 2
        """
        
        try:
            df = self._execute_athena_query(query)
            
            if len(df) == 0:
                logger.warning(f"No data found for channel {channel_title}")
                return []
            
            # Calculate composite score
            df['composite_score'] = (
                0.4 * df['avg_views'] / df['avg_views'].max() +
                0.3 * df['avg_engagement_rate'] / df['avg_engagement_rate'].max() +
                0.3 * df['avg_viral_score'] / df['avg_viral_score'].max()
            )
            
            # Get top time slots
            top_times = df.nlargest(top_n, 'composite_score')
            
            recommendations = []
            for _, row in top_times.iterrows():
                recommendations.append({
                    'hour': int(row['publish_hour']),
                    'day_of_week': int(row['publish_day_of_week']),
                    'day_name': self._get_day_name(int(row['publish_day_of_week'])),
                    'avg_views': float(row['avg_views']),
                    'avg_engagement': float(row['avg_engagement_rate']),
                    'composite_score': float(row['composite_score']),
                    'video_count': int(row['video_count'])
                })
            
            logger.info(f"Generated {len(recommendations)} recommendations for {channel_title}")
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error analyzing channel times: {str(e)}")
            return []
    
    def generate_posting_schedule(self, category_id: int, 
                                  videos_per_week: int = 3) -> List[Dict]:
        """
        Generate a recommended posting schedule
        
        Args:
            category_id: YouTube category ID
            videos_per_week: Number of videos to post per week
            
        Returns:
            List of recommended posting times for the week
        """
        logger.info(f"Generating posting schedule for category {category_id}")
        
        # Get optimal times
        optimal_times = self.analyze_optimal_times_by_category(
            category_id, 
            top_n=videos_per_week * 2  # Get extras in case of duplicates
        )
        
        if not optimal_times:
            return []
        
        # Select diverse time slots (avoid same day/hour combinations)
        schedule = []
        used_days = set()
        used_hours = set()
        
        for time_slot in optimal_times:
            if len(schedule) >= videos_per_week:
                break
            
            day = time_slot['day_of_week']
            hour = time_slot['hour']
            
            # Try to avoid posting on same day or at same hour
            if day not in used_days or len(schedule) < videos_per_week:
                schedule.append({
                    'day_of_week': day,
                    'day_name': time_slot['day_name'],
                    'hour': hour,
                    'time_slot': f"{time_slot['day_name']} at {hour}:00",
                    'expected_views': time_slot['avg_views'],
                    'expected_engagement': time_slot['avg_engagement'],
                    'recommendation_score': time_slot['composite_score']
                })
                used_days.add(day)
                used_hours.add(hour)
        
        # Sort by day of week
        schedule.sort(key=lambda x: x['day_of_week'])
        
        logger.info(f"Generated posting schedule with {len(schedule)} time slots")
        
        return schedule
    
    def compare_posting_strategies(self, category_id: int) -> Dict:
        """
        Compare different posting strategies
        
        Args:
            category_id: YouTube category ID
            
        Returns:
            Dict with strategy comparisons
        """
        logger.info(f"Comparing posting strategies for category {category_id}")
        
        if self.posting_analysis is None:
            self.load_posting_analysis()
        
        category_data = self.posting_analysis[
            self.posting_analysis['category_id'] == category_id
        ].copy()
        
        if len(category_data) == 0:
            return {}
        
        strategies = {}
        
        # Weekday vs Weekend
        weekday_data = category_data[~category_data['publish_day_of_week'].isin([1, 7])]
        weekend_data = category_data[category_data['publish_day_of_week'].isin([1, 7])]
        
        strategies['weekday_vs_weekend'] = {
            'weekday': {
                'avg_views': float(weekday_data['avg_views'].mean()) if len(weekday_data) > 0 else 0,
                'avg_engagement': float(weekday_data['avg_engagement_rate'].mean()) if len(weekday_data) > 0 else 0
            },
            'weekend': {
                'avg_views': float(weekend_data['avg_views'].mean()) if len(weekend_data) > 0 else 0,
                'avg_engagement': float(weekend_data['avg_engagement_rate'].mean()) if len(weekend_data) > 0 else 0
            }
        }
        
        # Time of day analysis
        morning = category_data[category_data['publish_hour'].between(6, 11)]
        afternoon = category_data[category_data['publish_hour'].between(12, 17)]
        evening = category_data[category_data['publish_hour'].between(18, 22)]
        
        strategies['time_of_day'] = {
            'morning': {
                'avg_views': float(morning['avg_views'].mean()) if len(morning) > 0 else 0,
                'avg_engagement': float(morning['avg_engagement_rate'].mean()) if len(morning) > 0 else 0
            },
            'afternoon': {
                'avg_views': float(afternoon['avg_views'].mean()) if len(afternoon) > 0 else 0,
                'avg_engagement': float(afternoon['avg_engagement_rate'].mean()) if len(afternoon) > 0 else 0
            },
            'evening': {
                'avg_views': float(evening['avg_views'].mean()) if len(evening) > 0 else 0,
                'avg_engagement': float(evening['avg_engagement_rate'].mean()) if len(evening) > 0 else 0
            }
        }
        
        return strategies
    
    def _execute_athena_query(self, query: str) -> pd.DataFrame:
        """Execute Athena query and return results as DataFrame"""
        execution_id = athena_client.start_query_execution(
            QueryString=query,
            QueryExecutionContext={'Database': ATHENA_DATABASE},
            ResultConfiguration={'OutputLocation': f"s3://{ATHENA_OUTPUT_BUCKET}/"}
        )['QueryExecutionId']
        
        # Wait for completion
        while True:
            response = athena_client.get_query_execution(QueryExecutionId=execution_id)
            state = response['QueryExecution']['Status']['State']
            
            if state == 'SUCCEEDED':
                break
            elif state in ['FAILED', 'CANCELLED']:
                raise Exception(f"Query failed: {response['QueryExecution']['Status']}")
        
        # Get results
        result = athena_client.get_query_results(QueryExecutionId=execution_id)
        
        # Parse to DataFrame
        columns = [col['Label'] for col in result['ResultSet']['ResultSetMetadata']['ColumnInfo']]
        rows = [[field.get('VarCharValue', '') for field in row['Data']] 
                for row in result['ResultSet']['Rows'][1:]]
        
        return pd.DataFrame(rows, columns=columns)
    
    @staticmethod
    def _get_day_name(day_of_week: int) -> str:
        """Convert day of week number to name"""
        days = {1: 'Sunday', 2: 'Monday', 3: 'Tuesday', 4: 'Wednesday',
                5: 'Thursday', 6: 'Friday', 7: 'Saturday'}
        return days.get(day_of_week, 'Unknown')
    
    def save_recommendations(self, recommendations: Dict):
        """Save recommendations to S3"""
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        s3_key = f"recommendations/{timestamp}_posting_recommendations.json"
        
        s3_client.put_object(
            Bucket=CURATED_BUCKET,
            Key=s3_key,
            Body=json.dumps(recommendations, indent=2)
        )
        
        logger.info(f"Recommendations saved to s3://{CURATED_BUCKET}/{s3_key}")


def main():
    """Main function for testing"""
    recommender = PostingTimeRecommender()
    
    # Get recommendations for a category
    category_recommendations = recommender.analyze_optimal_times_by_category(28, top_n=5)
    
    # Generate posting schedule
    schedule = recommender.generate_posting_schedule(28, videos_per_week=3)
    
    # Compare strategies
    strategies = recommender.compare_posting_strategies(28)
    
    results = {
        'category_id': 28,
        'top_posting_times': category_recommendations,
        'recommended_schedule': schedule,
        'strategy_comparison': strategies,
        'generated_at': datetime.utcnow().isoformat()
    }
    
    print(json.dumps(results, indent=2))
    
    recommender.save_recommendations(results)


if __name__ == "__main__":
    main()
