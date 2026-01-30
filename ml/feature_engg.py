"""
Feature Engineering for YouTube Video Performance Prediction
Purpose: Generate ML-ready features from curated data
"""

import sys
import boto3
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F
from pyspark.sql.types import *
from pyspark.sql.window import Window
from datetime import datetime, timedelta
import logging

# Initialize
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'CURATED_BUCKET', 'FEATURE_STORE_BUCKET'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

CURATED_BUCKET = args['CURATED_BUCKET']
FEATURE_STORE_BUCKET = args['FEATURE_STORE_BUCKET']


def load_curated_data():
    """Load data from Gold layer"""
    logger.info("Loading curated data")
    
    df = spark.read.parquet(f"s3://{CURATED_BUCKET}/gold/")
    logger.info(f"Loaded {df.count()} records")
    
    return df


def create_temporal_features(df):
    """
    Create time-based features
    
    Args:
        df: Input DataFrame
        
    Returns:
        DataFrame with temporal features
    """
    logger.info("Creating temporal features")
    
    # Hour-based features
    df = df.withColumn('hour_sin', F.sin(2 * 3.14159 * F.col('publish_hour') / 24)) \
           .withColumn('hour_cos', F.cos(2 * 3.14159 * F.col('publish_hour') / 24))
    
    # Day of week features (cyclical encoding)
    df = df.withColumn('dow_sin', F.sin(2 * 3.14159 * F.col('publish_day_of_week') / 7)) \
           .withColumn('dow_cos', F.cos(2 * 3.14159 * F.col('publish_day_of_week') / 7))
    
    # Month features (cyclical encoding)
    df = df.withColumn('month_sin', F.sin(2 * 3.14159 * F.col('publish_month') / 12)) \
           .withColumn('month_cos', F.cos(2 * 3.14159 * F.col('publish_month') / 12))
    
    # Is weekend
    df = df.withColumn('is_weekend', 
                       F.when(F.col('publish_day_of_week').isin([1, 7]), 1).otherwise(0))
    
    # Time of day categories
    df = df.withColumn('time_of_day',
                       F.when(F.col('publish_hour').between(6, 11), 'morning')
                       .when(F.col('publish_hour').between(12, 17), 'afternoon')
                       .when(F.col('publish_hour').between(18, 22), 'evening')
                       .otherwise('night'))
    
    return df


def create_text_features(df):
    """
    Create features from text fields
    
    Args:
        df: Input DataFrame
        
    Returns:
        DataFrame with text features
    """
    logger.info("Creating text features")
    
    # Title features
    df = df.withColumn('title_word_count', 
                       F.size(F.split(F.col('title'), ' '))) \
           .withColumn('title_char_count', F.length(F.col('title'))) \
           .withColumn('title_has_question', 
                      F.when(F.col('title').contains('?'), 1).otherwise(0)) \
           .withColumn('title_has_exclamation',
                      F.when(F.col('title').contains('!'), 1).otherwise(0)) \
           .withColumn('title_has_numbers',
                      F.when(F.col('title').rlike('[0-9]'), 1).otherwise(0)) \
           .withColumn('title_all_caps_ratio',
                      F.length(F.regexp_replace(F.col('title'), '[^A-Z]', '')) / 
                      F.length(F.col('title')))
    
    # Description features
    df = df.withColumn('description_word_count',
                       F.size(F.split(F.col('description'), ' '))) \
           .withColumn('description_char_count', F.length(F.col('description'))) \
           .withColumn('description_has_link',
                      F.when(F.col('description').rlike('http[s]?://'), 1).otherwise(0))
    
    # Tag features
    df = df.withColumn('tag_count', 
                       F.when(F.col('tags').isNotNull(),
                              F.size(F.split(F.col('tags'), '\\|')))
                       .otherwise(0))
    
    return df


def create_channel_features(df):
    """
    Create channel-level features
    
    Args:
        df: Input DataFrame
        
    Returns:
        DataFrame with channel features
    """
    logger.info("Creating channel features")
    
    # Channel historical performance
    window_channel = Window.partitionBy('channel_title').orderBy('publish_timestamp') \
        .rowsBetween(Window.unboundedPreceding, -1)
    
    df = df.withColumn('channel_avg_views_historical',
                       F.avg('views').over(window_channel)) \
           .withColumn('channel_avg_engagement_historical',
                      F.avg('engagement_rate').over(window_channel)) \
           .withColumn('channel_video_count_historical',
                      F.count('video_id').over(window_channel))
    
    # Channel upload frequency
    df = df.withColumn('days_since_last_upload',
                       F.datediff(F.col('publish_date'),
                                 F.lag('publish_date', 1).over(
                                     Window.partitionBy('channel_title').orderBy('publish_date'))))
    
    # Channel consistency score
    df = df.withColumn('channel_consistency_score',
                       1 / (F.stddev('days_since_last_upload').over(window_channel) + 1))
    
    return df


def create_rolling_features(df, windows=[7, 14, 30]):
    """
    Create rolling window features
    
    Args:
        df: Input DataFrame
        windows: List of window sizes in days
        
    Returns:
        DataFrame with rolling features
    """
    logger.info(f"Creating rolling features for windows: {windows}")
    
    for window_days in windows:
        # Define window spec
        window_spec = Window.partitionBy('channel_title').orderBy('publish_date') \
            .rangeBetween(-window_days * 86400, -1)
        
        # Rolling averages
        df = df.withColumn(f'rolling_avg_views_{window_days}d',
                           F.avg('views').over(window_spec)) \
               .withColumn(f'rolling_avg_likes_{window_days}d',
                          F.avg('likes').over(window_spec)) \
               .withColumn(f'rolling_avg_comments_{window_days}d',
                          F.avg('comment_count').over(window_spec)) \
               .withColumn(f'rolling_avg_engagement_{window_days}d',
                          F.avg('engagement_rate').over(window_spec))
        
        # Rolling sums
        df = df.withColumn(f'rolling_sum_views_{window_days}d',
                           F.sum('views').over(window_spec)) \
               .withColumn(f'rolling_video_count_{window_days}d',
                          F.count('video_id').over(window_spec))
        
        # Rolling max
        df = df.withColumn(f'rolling_max_views_{window_days}d',
                           F.max('views').over(window_spec))
    
    return df


def create_engagement_features(df):
    """
    Create engagement-specific features
    
    Args:
        df: Input DataFrame
        
    Returns:
        DataFrame with engagement features
    """
    logger.info("Creating engagement features")
    
    # Basic engagement metrics
    df = df.withColumn('likes_per_view',
                       F.when(F.col('views') > 0, F.col('likes') / F.col('views')).otherwise(0)) \
           .withColumn('comments_per_view',
                      F.when(F.col('views') > 0, F.col('comment_count') / F.col('views')).otherwise(0)) \
           .withColumn('like_comment_ratio',
                      F.when(F.col('comment_count') > 0, 
                            F.col('likes') / F.col('comment_count')).otherwise(0))
    
    # Engagement velocity (engagement rate / days since publish)
    df = df.withColumn('engagement_velocity',
                       F.when(F.col('days_since_publish') > 0,
                              F.col('engagement_rate') / F.col('days_since_publish'))
                       .otherwise(F.col('engagement_rate')))
    
    # Viral coefficient
    df = df.withColumn('viral_coefficient',
                       F.col('views') * F.col('engagement_rate') / 
                       (F.col('days_since_publish') + 1))
    
    return df


def create_category_features(df):
    """
    Create category-level features
    
    Args:
        df: Input DataFrame
        
    Returns:
        DataFrame with category features
    """
    logger.info("Creating category features")
    
    # Category average performance
    window_category = Window.partitionBy('category_id')
    
    df = df.withColumn('category_avg_views',
                       F.avg('views').over(window_category)) \
           .withColumn('category_avg_engagement',
                      F.avg('engagement_rate').over(window_category)) \
           .withColumn('category_video_count',
                      F.count('video_id').over(window_category))
    
    # Video performance relative to category
    df = df.withColumn('views_vs_category_avg',
                       F.col('views') / F.col('category_avg_views')) \
           .withColumn('engagement_vs_category_avg',
                      F.col('engagement_rate') / F.col('category_avg_engagement'))
    
    return df


def create_target_variable(df, target_col='views', high_threshold_percentile=0.75):
    """
    Create target variable for classification/regression
    
    Args:
        df: Input DataFrame
        target_col: Column to use as target
        high_threshold_percentile: Percentile for high performance classification
        
    Returns:
        DataFrame with target variables
    """
    logger.info(f"Creating target variable from {target_col}")
    
    # Calculate percentile threshold
    threshold = df.approxQuantile(target_col, [high_threshold_percentile], 0.01)[0]
    
    # Binary classification target
    df = df.withColumn('high_performance',
                       F.when(F.col(target_col) >= threshold, 1).otherwise(0))
    
    # Multi-class classification target
    df = df.withColumn('performance_category',
                       F.when(F.col(target_col) >= df.approxQuantile(target_col, [0.9], 0.01)[0], 'excellent')
                       .when(F.col(target_col) >= df.approxQuantile(target_col, [0.75], 0.01)[0], 'good')
                       .when(F.col(target_col) >= df.approxQuantile(target_col, [0.5], 0.01)[0], 'average')
                       .otherwise('poor'))
    
    return df


def select_feature_columns(df):
    """
    Select final feature columns for ML
    
    Args:
        df: DataFrame with all features
        
    Returns:
        DataFrame with selected features
    """
    logger.info("Selecting feature columns")
    
    # Define feature groups
    id_columns = ['video_id', 'channel_title', 'publish_timestamp']
    
    temporal_features = [
        'publish_hour', 'publish_day_of_week', 'publish_month',
        'hour_sin', 'hour_cos', 'dow_sin', 'dow_cos', 'month_sin', 'month_cos',
        'is_weekend', 'days_since_publish'
    ]
    
    text_features = [
        'title_word_count', 'title_char_count', 'title_has_question',
        'title_has_exclamation', 'title_has_numbers', 'title_all_caps_ratio',
        'description_word_count', 'description_char_count', 'description_has_link',
        'tag_count'
    ]
    
    channel_features = [
        'channel_avg_views_historical', 'channel_avg_engagement_historical',
        'channel_video_count_historical', 'days_since_last_upload',
        'channel_consistency_score'
    ]
    
    rolling_features = [col for col in df.columns if 'rolling_' in col]
    
    engagement_features = [
        'likes_per_view', 'comments_per_view', 'like_comment_ratio',
        'engagement_velocity', 'viral_coefficient'
    ]
    
    category_features = [
        'category_id', 'category_avg_views', 'category_avg_engagement',
        'views_vs_category_avg', 'engagement_vs_category_avg'
    ]
    
    target_variables = ['views', 'likes', 'comment_count', 'engagement_rate',
                       'high_performance', 'performance_category']
    
    # Combine all features
    all_features = (id_columns + temporal_features + text_features + 
                   channel_features + rolling_features + engagement_features +
                   category_features + target_variables)
    
    # Select only columns that exist in the dataframe
    available_features = [col for col in all_features if col in df.columns]
    
    df_features = df.select(available_features)
    
    logger.info(f"Selected {len(available_features)} features")
    
    return df_features


def write_feature_store(df):
    """
    Write features to feature store
    
    Args:
        df: Feature DataFrame
    """
    logger.info("Writing features to feature store")
    
    output_path = f"s3://{FEATURE_STORE_BUCKET}/features/youtube_video_features/"
    
    # Convert to DynamicFrame and write
    dynamic_frame = DynamicFrame.fromDF(df, glueContext, "features")
    
    glueContext.write_dynamic_frame.from_options(
        frame=dynamic_frame,
        connection_type="s3",
        connection_options={
            "path": output_path,
            "partitionKeys": ["publish_year", "publish_month"]
        },
        format="parquet",
        format_options={"compression": "snappy"}
    )
    
    logger.info(f"Features written to {output_path}")


def main():
    """Main feature engineering pipeline"""
    try:
        logger.info("Starting feature engineering job")
        
        # Load data
        df = load_curated_data()
        
        # Create features
        df = create_temporal_features(df)
        df = create_text_features(df)
        df = create_channel_features(df)
        df = create_rolling_features(df)
        df = create_engagement_features(df)
        df = create_category_features(df)
        df = create_target_variable(df)
        
        # Select final features
        df_features = select_feature_columns(df)
        
        # Write to feature store
        write_feature_store(df_features)
        
        logger.info("Feature engineering completed successfully")
        
        job.commit()
        
    except Exception as e:
        logger.error(f"Error in feature engineering: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
