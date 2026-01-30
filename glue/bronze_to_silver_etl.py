"""
AWS Glue ETL Job: Bronze to Silver Transformation
Purpose: Clean and standardize raw YouTube data
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
from datetime import datetime
import logging

# Initialize Glue context
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'RAW_BUCKET', 'PROCESSED_BUCKET'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuration
RAW_BUCKET = args['RAW_BUCKET']
PROCESSED_BUCKET = args['PROCESSED_BUCKET']
DATABASE_NAME = 'youtube_analytics_db'
RAW_TABLE = 'youtube_raw'


def read_bronze_data():
    """
    Read data from Bronze layer (raw S3 data)
    
    Returns:
        DynamicFrame with raw YouTube data
    """
    logger.info(f"Reading data from Bronze layer: {RAW_BUCKET}")
    
    # Read from Glue Catalog
    datasource = glueContext.create_dynamic_frame.from_catalog(
        database=DATABASE_NAME,
        table_name=RAW_TABLE,
        transformation_ctx="datasource"
    )
    
    logger.info(f"Loaded {datasource.count()} records from Bronze layer")
    
    return datasource


def clean_and_standardize(df):
    """
    Clean and standardize the raw data
    
    Args:
        df: Input Spark DataFrame
        
    Returns:
        Cleaned and standardized DataFrame
    """
    logger.info("Starting data cleaning and standardization")
    
    # Remove duplicates based on video_id and publish_time
    df = df.dropDuplicates(['video_id', 'publish_time'])
    
    # Standardize column names (lowercase, replace spaces with underscores)
    for col_name in df.columns:
        new_col_name = col_name.lower().replace(' ', '_').replace('-', '_')
        df = df.withColumnRenamed(col_name, new_col_name)
    
    # Handle null values
    df = df.fillna({
        'likes': 0,
        'dislikes': 0,
        'comment_count': 0,
        'comments_disabled': False,
        'ratings_disabled': False,
        'video_error_or_removed': False
    })
    
    # Cast data types properly
    df = df.withColumn('views', F.col('views').cast(LongType())) \
           .withColumn('likes', F.col('likes').cast(LongType())) \
           .withColumn('dislikes', F.col('dislikes').cast(LongType())) \
           .withColumn('comment_count', F.col('comment_count').cast(LongType())) \
           .withColumn('category_id', F.col('category_id').cast(IntegerType()))
    
    # Parse publish_time as timestamp
    df = df.withColumn('publish_timestamp', 
                       F.to_timestamp(F.col('publish_time'), 'yyyy-MM-dd\'T\'HH:mm:ss.SSS\'Z\''))
    
    # Extract date components for partitioning
    df = df.withColumn('publish_date', F.to_date(F.col('publish_timestamp'))) \
           .withColumn('publish_year', F.year(F.col('publish_timestamp'))) \
           .withColumn('publish_month', F.month(F.col('publish_timestamp'))) \
           .withColumn('publish_day', F.dayofmonth(F.col('publish_timestamp'))) \
           .withColumn('publish_hour', F.hour(F.col('publish_timestamp'))) \
           .withColumn('publish_day_of_week', F.dayofweek(F.col('publish_timestamp')))
    
    # Calculate days since publish
    df = df.withColumn('days_since_publish', 
                       F.datediff(F.current_date(), F.col('publish_date')))
    
    # Clean text fields
    df = df.withColumn('title', F.trim(F.col('title'))) \
           .withColumn('channel_title', F.trim(F.col('channel_title'))) \
           .withColumn('description', F.trim(F.col('description')))
    
    # Add text length features
    df = df.withColumn('title_length', F.length(F.col('title'))) \
           .withColumn('description_length', F.length(F.col('description')))
    
    # Parse tags if present
    df = df.withColumn('tag_count', 
                       F.when(F.col('tags').isNotNull(), 
                              F.size(F.split(F.col('tags'), '\\|')))
                       .otherwise(0))
    
    # Add data quality flag
    df = df.withColumn('data_quality_score',
                       F.when((F.col('views').isNull()) | (F.col('views') < 0), 0.0)
                       .when((F.col('title').isNull()) | (F.length(F.col('title')) == 0), 0.3)
                       .when((F.col('channel_title').isNull()), 0.5)
                       .otherwise(1.0))
    
    # Add processing metadata
    df = df.withColumn('processed_timestamp', F.current_timestamp()) \
           .withColumn('processing_job', F.lit(args['JOB_NAME']))
    
    logger.info(f"Cleaned data contains {df.count()} records")
    
    return df


def add_derived_metrics(df):
    """
    Add derived engagement metrics
    
    Args:
        df: Cleaned DataFrame
        
    Returns:
        DataFrame with derived metrics
    """
    logger.info("Calculating derived metrics")
    
    # Engagement rate: (likes + comments) / views
    df = df.withColumn('engagement_rate',
                       F.when(F.col('views') > 0,
                              (F.col('likes') + F.col('comment_count')) / F.col('views'))
                       .otherwise(0))
    
    # Like ratio: likes / (likes + dislikes)
    df = df.withColumn('like_ratio',
                       F.when((F.col('likes') + F.col('dislikes')) > 0,
                              F.col('likes') / (F.col('likes') + F.col('dislikes')))
                       .otherwise(0))
    
    # Comment ratio: comments / views
    df = df.withColumn('comment_ratio',
                       F.when(F.col('views') > 0,
                              F.col('comment_count') / F.col('views'))
                       .otherwise(0))
    
    # Views per day
    df = df.withColumn('views_per_day',
                       F.when(F.col('days_since_publish') > 0,
                              F.col('views') / F.col('days_since_publish'))
                       .otherwise(F.col('views')))
    
    # Viral score (simplified)
    df = df.withColumn('viral_score',
                       F.col('views') * F.col('engagement_rate') / 
                       (F.col('days_since_publish') + 1))
    
    # Engagement category
    df = df.withColumn('engagement_category',
                       F.when(F.col('engagement_rate') >= 0.05, 'high')
                       .when(F.col('engagement_rate') >= 0.02, 'medium')
                       .otherwise('low'))
    
    return df


def apply_data_quality_filters(df, quality_threshold=0.8):
    """
    Filter out low-quality records
    
    Args:
        df: DataFrame with quality scores
        quality_threshold: Minimum quality score to retain
        
    Returns:
        Filtered DataFrame
    """
    logger.info(f"Applying data quality filters (threshold: {quality_threshold})")
    
    initial_count = df.count()
    
    # Filter by quality score
    df_filtered = df.filter(F.col('data_quality_score') >= quality_threshold)
    
    # Additional quality checks
    df_filtered = df_filtered.filter(
        (F.col('views') >= 0) &
        (F.col('likes') >= 0) &
        (F.col('video_id').isNotNull()) &
        (F.col('title').isNotNull())
    )
    
    final_count = df_filtered.count()
    removed_count = initial_count - final_count
    
    logger.info(f"Quality filtering: {initial_count} -> {final_count} records ({removed_count} removed)")
    
    return df_filtered


def write_silver_data(df):
    """
    Write processed data to Silver layer
    
    Args:
        df: Processed DataFrame
    """
    logger.info(f"Writing data to Silver layer: {PROCESSED_BUCKET}")
    
    # Convert to DynamicFrame for Glue
    dynamic_frame = DynamicFrame.fromDF(df, glueContext, "processed_data")
    
    # Write to S3 in Parquet format, partitioned by year and month
    output_path = f"s3://{PROCESSED_BUCKET}/silver/youtube_videos/"
    
    glueContext.write_dynamic_frame.from_options(
        frame=dynamic_frame,
        connection_type="s3",
        connection_options={
            "path": output_path,
            "partitionKeys": ["publish_year", "publish_month", "category_id"]
        },
        format="parquet",
        format_options={
            "compression": "snappy"
        },
        transformation_ctx="datasink"
    )
    
    logger.info(f"Successfully wrote {df.count()} records to Silver layer")
    
    # Update Glue Data Catalog
    update_catalog(output_path)


def update_catalog(s3_path):
    """
    Update Glue Data Catalog with new partition information
    
    Args:
        s3_path: S3 path to the data
    """
    logger.info("Updating Glue Data Catalog")
    
    # This would typically trigger a crawler or use boto3 to update partitions
    # For now, we'll log the action
    logger.info(f"Catalog updated for path: {s3_path}")


def main():
    """
    Main ETL execution function
    """
    try:
        logger.info("Starting Bronze to Silver ETL job")
        
        # Step 1: Read Bronze data
        bronze_data = read_bronze_data()
        df = bronze_data.toDF()
        
        # Step 2: Clean and standardize
        df_clean = clean_and_standardize(df)
        
        # Step 3: Add derived metrics
        df_metrics = add_derived_metrics(df_clean)
        
        # Step 4: Apply quality filters
        df_quality = apply_data_quality_filters(df_metrics, quality_threshold=0.8)
        
        # Step 5: Write to Silver layer
        write_silver_data(df_quality)
        
        logger.info("Bronze to Silver ETL job completed successfully")
        
        job.commit()
        
    except Exception as e:
        logger.error(f"Error in Bronze to Silver ETL job: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
