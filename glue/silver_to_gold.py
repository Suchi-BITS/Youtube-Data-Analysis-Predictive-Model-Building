"""
AWS Glue ETL Job: Silver to Gold Transformation
Purpose: Create analytics-ready aggregations and curated datasets
"""

import sys
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

# Initialize Glue context
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'PROCESSED_BUCKET', 'CURATED_BUCKET'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuration
PROCESSED_BUCKET = args['PROCESSED_BUCKET']
CURATED_BUCKET = args['CURATED_BUCKET']
DATABASE_NAME = 'youtube_analytics_db'
SILVER_TABLE = 'youtube_videos_silver'


def read_silver_data():
    """
    Read processed data from Silver layer
    
    Returns:
        Spark DataFrame
    """
    logger.info(f"Reading data from Silver layer: {PROCESSED_BUCKET}")
    
    # Read from Glue Catalog
    datasource = glueContext.create_dynamic_frame.from_catalog(
        database=DATABASE_NAME,
        table_name=SILVER_TABLE,
        transformation_ctx="silver_datasource"
    )
    
    df = datasource.toDF()
    logger.info(f"Loaded {df.count()} records from Silver layer")
    
    return df


def create_daily_metrics(df):
    """
    Create daily aggregated metrics
    
    Args:
        df: Silver layer DataFrame
        
    Returns:
        DataFrame with daily metrics
    """
    logger.info("Creating daily metrics aggregation")
    
    daily_metrics = df.groupBy('publish_date', 'category_id', 'channel_title') \
        .agg(
            F.count('video_id').alias('video_count'),
            F.sum('views').alias('total_views'),
            F.avg('views').alias('avg_views'),
            F.sum('likes').alias('total_likes'),
            F.avg('likes').alias('avg_likes'),
            F.sum('comment_count').alias('total_comments'),
            F.avg('comment_count').alias('avg_comments'),
            F.avg('engagement_rate').alias('avg_engagement_rate'),
            F.avg('like_ratio').alias('avg_like_ratio'),
            F.max('views').alias('max_views'),
            F.min('views').alias('min_views'),
            F.stddev('views').alias('stddev_views')
        )
    
    # Add derived metrics
    daily_metrics = daily_metrics.withColumn('avg_views_per_video', 
                                            F.col('total_views') / F.col('video_count'))
    
    # Add time-based features
    daily_metrics = daily_metrics.withColumn('year', F.year('publish_date')) \
                                 .withColumn('month', F.month('publish_date')) \
                                 .withColumn('day_of_week', F.dayofweek('publish_date')) \
                                 .withColumn('is_weekend', 
                                           F.when(F.col('day_of_week').isin([1, 7]), True)
                                           .otherwise(False))
    
    logger.info(f"Created daily metrics with {daily_metrics.count()} records")
    
    return daily_metrics


def create_channel_performance(df):
    """
    Create channel-level performance metrics
    
    Args:
        df: Silver layer DataFrame
        
    Returns:
        DataFrame with channel metrics
    """
    logger.info("Creating channel performance aggregation")
    
    # Calculate overall channel metrics
    channel_metrics = df.groupBy('channel_title', 'category_id') \
        .agg(
            F.count('video_id').alias('total_videos'),
            F.sum('views').alias('total_channel_views'),
            F.avg('views').alias('avg_video_views'),
            F.sum('likes').alias('total_channel_likes'),
            F.avg('likes').alias('avg_video_likes'),
            F.sum('comment_count').alias('total_channel_comments'),
            F.avg('engagement_rate').alias('avg_engagement_rate'),
            F.avg('viral_score').alias('avg_viral_score'),
            F.min('publish_date').alias('first_video_date'),
            F.max('publish_date').alias('latest_video_date'),
            F.countDistinct('publish_date').alias('active_days')
        )
    
    # Calculate posting frequency
    channel_metrics = channel_metrics.withColumn('days_active',
                                                 F.datediff('latest_video_date', 'first_video_date') + 1) \
                                     .withColumn('posting_frequency',
                                               F.col('total_videos') / F.col('days_active'))
    
    # Add channel growth window (last 30 days vs previous period)
    window_30d = df.filter(F.col('publish_date') >= F.date_sub(F.current_date(), 30))
    recent_metrics = window_30d.groupBy('channel_title') \
        .agg(
            F.sum('views').alias('views_last_30d'),
            F.count('video_id').alias('videos_last_30d'),
            F.avg('engagement_rate').alias('engagement_rate_last_30d')
        )
    
    # Join recent metrics
    channel_metrics = channel_metrics.join(recent_metrics, 'channel_title', 'left')
    
    # Calculate growth rate
    channel_metrics = channel_metrics.withColumn('view_growth_rate',
                                                 (F.col('views_last_30d') / F.col('total_channel_views')))
    
    logger.info(f"Created channel performance with {channel_metrics.count()} records")
    
    return channel_metrics


def create_category_analysis(df):
    """
    Create category-level analysis
    
    Args:
        df: Silver layer DataFrame
        
    Returns:
        DataFrame with category insights
    """
    logger.info("Creating category analysis")
    
    category_metrics = df.groupBy('category_id', 'publish_date') \
        .agg(
            F.count('video_id').alias('video_count'),
            F.sum('views').alias('total_views'),
            F.avg('views').alias('avg_views'),
            F.avg('engagement_rate').alias('avg_engagement_rate'),
            F.avg('viral_score').alias('avg_viral_score'),
            F.countDistinct('channel_title').alias('unique_channels')
        )
    
    # Add rolling averages for trend analysis
    window_spec = Window.partitionBy('category_id').orderBy('publish_date').rowsBetween(-6, 0)
    
    category_metrics = category_metrics.withColumn('rolling_avg_views_7d',
                                                   F.avg('total_views').over(window_spec)) \
                                       .withColumn('rolling_avg_engagement_7d',
                                                 F.avg('avg_engagement_rate').over(window_spec))
    
    # Add month and year for partitioning
    category_metrics = category_metrics.withColumn('year', F.year('publish_date')) \
                                       .withColumn('month', F.month('publish_date'))
    
    logger.info(f"Created category analysis with {category_metrics.count()} records")
    
    return category_metrics


def create_trending_analysis(df):
    """
    Identify trending videos and patterns
    
    Args:
        df: Silver layer DataFrame
        
    Returns:
        DataFrame with trending insights
    """
    logger.info("Creating trending analysis")
    
    # Define trending criteria: high viral score, recent publish, high engagement
    trending_threshold = df.select(F.expr('percentile_approx(viral_score, 0.9)')).collect()[0][0]
    
    trending_videos = df.filter(
        (F.col('viral_score') >= trending_threshold) &
        (F.col('days_since_publish') <= 7) &
        (F.col('engagement_rate') >= 0.03)
    )
    
    # Add trending rank per category
    window_category = Window.partitionBy('category_id').orderBy(F.desc('viral_score'))
    
    trending_videos = trending_videos.withColumn('trending_rank_in_category',
                                                 F.row_number().over(window_category))
    
    # Select key columns for trending table
    trending_videos = trending_videos.select(
        'video_id', 'title', 'channel_title', 'category_id', 
        'publish_date', 'views', 'likes', 'comment_count',
        'engagement_rate', 'viral_score', 'trending_rank_in_category',
        'publish_year', 'publish_month'
    )
    
    logger.info(f"Identified {trending_videos.count()} trending videos")
    
    return trending_videos


def create_posting_time_analysis(df):
    """
    Analyze optimal posting times
    
    Args:
        df: Silver layer DataFrame
        
    Returns:
        DataFrame with posting time insights
    """
    logger.info("Creating posting time analysis")
    
    posting_analysis = df.groupBy('publish_hour', 'publish_day_of_week', 'category_id') \
        .agg(
            F.count('video_id').alias('video_count'),
            F.avg('views').alias('avg_views'),
            F.avg('engagement_rate').alias('avg_engagement_rate'),
            F.avg('viral_score').alias('avg_viral_score')
        )
    
    # Calculate performance percentile for each time slot
    window_category = Window.partitionBy('category_id')
    
    posting_analysis = posting_analysis.withColumn('views_percentile',
                                                   F.percent_rank().over(
                                                       window_category.orderBy('avg_views'))) \
                                       .withColumn('engagement_percentile',
                                                 F.percent_rank().over(
                                                     window_category.orderBy('avg_engagement_rate')))
    
    # Identify optimal posting windows (top 20% performance)
    posting_analysis = posting_analysis.withColumn('is_optimal_time',
                                                   F.when((F.col('views_percentile') >= 0.8) &
                                                         (F.col('engagement_percentile') >= 0.8), True)
                                                   .otherwise(False))
    
    logger.info(f"Created posting time analysis with {posting_analysis.count()} records")
    
    return posting_analysis


def write_gold_data(df, table_name, partition_keys):
    """
    Write curated data to Gold layer
    
    Args:
        df: Curated DataFrame
        table_name: Name of the output table
        partition_keys: List of partition column names
    """
    logger.info(f"Writing {table_name} to Gold layer")
    
    # Convert to DynamicFrame
    dynamic_frame = DynamicFrame.fromDF(df, glueContext, table_name)
    
    # Write to S3
    output_path = f"s3://{CURATED_BUCKET}/gold/{table_name}/"
    
    glueContext.write_dynamic_frame.from_options(
        frame=dynamic_frame,
        connection_type="s3",
        connection_options={
            "path": output_path,
            "partitionKeys": partition_keys
        },
        format="parquet",
        format_options={
            "compression": "snappy"
        }
    )
    
    logger.info(f"Successfully wrote {table_name} to Gold layer")


def main():
    """
    Main ETL execution function
    """
    try:
        logger.info("Starting Silver to Gold ETL job")
        
        # Step 1: Read Silver data
        df_silver = read_silver_data()
        
        # Step 2: Create daily metrics
        df_daily = create_daily_metrics(df_silver)
        write_gold_data(df_daily, 'daily_metrics', ['year', 'month'])
        
        # Step 3: Create channel performance
        df_channel = create_channel_performance(df_silver)
        write_gold_data(df_channel, 'channel_performance', ['category_id'])
        
        # Step 4: Create category analysis
        df_category = create_category_analysis(df_silver)
        write_gold_data(df_category, 'category_analysis', ['year', 'month', 'category_id'])
        
        # Step 5: Create trending analysis
        df_trending = create_trending_analysis(df_silver)
        write_gold_data(df_trending, 'trending_videos', ['publish_year', 'publish_month'])
        
        # Step 6: Create posting time analysis
        df_posting = create_posting_time_analysis(df_silver)
        write_gold_data(df_posting, 'posting_time_analysis', ['category_id'])
        
        logger.info("Silver to Gold ETL job completed successfully")
        
        job.commit()
        
    except Exception as e:
        logger.error(f"Error in Silver to Gold ETL job: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
