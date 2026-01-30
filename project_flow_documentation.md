# YouTube Analytics Platform - Complete Data Flow Documentation

## Project Completeness Status

### ✅ Complete Files (13 core files)
1. Configuration files (2)
2. Data ingestion (2) 
3. ETL pipeline (2)
4. Feature engineering (1)
5. Machine learning (2)
6. Analytics (1)
7. Orchestration (1)
8. Infrastructure (1)
9. Documentation (1)

### 📝 Additional Files Created
10. Data source ingestion script
11. This flow documentation

### ⚠️ Missing/Optional Files (Not Critical)
- Unit tests (test files)
- Data quality validation module
- Model monitoring dashboard
- CI/CD pipeline configuration
- Terraform/CloudFormation IaC templates

---

## Complete Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DATA SOURCES                                 │
├─────────────────────────────────────────────────────────────────────┤
│ 1. Kaggle Dataset (YouTube Trending Videos)                         │
│ 2. YouTube Data API (Real-time)                                     │
│ 3. Sample Data Generator (Testing)                                  │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      INGESTION LAYER                                 │
├─────────────────────────────────────────────────────────────────────┤
│ FILE: ingestion_data_ingestion.py                                   │
│ PURPOSE: Download/fetch data from sources                           │
│ OUTPUT: CSV files uploaded to S3 Raw Bucket                         │
│ LOCATION: s3://youtube-analytics-raw-bronze/raw/youtube/            │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    VALIDATION LAYER                                  │
├─────────────────────────────────────────────────────────────────────┤
│ FILE: lambda_ingestion_trigger.py                                   │
│ TRIGGER: S3 PUT event on raw bucket                                 │
│ PURPOSE:                                                             │
│   - Validate file format (CSV/JSON/Parquet)                         │
│   - Check schema (required columns present)                         │
│   - Verify data quality (non-empty, valid types)                    │
│   - Trigger Glue Crawler to update catalog                          │
│ OUTPUT: Validation status + Glue Crawler execution                  │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     BRONZE LAYER (RAW)                               │
├─────────────────────────────────────────────────────────────────────┤
│ LOCATION: s3://youtube-analytics-raw-bronze/                        │
│ FORMAT: CSV (as uploaded)                                           │
│ CHARACTERISTICS:                                                     │
│   - Immutable source data                                           │
│   - Original format preserved                                       │
│   - Minimal processing                                              │
│ GLUE TABLE: youtube_raw                                             │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│              BRONZE → SILVER TRANSFORMATION                          │
├─────────────────────────────────────────────────────────────────────┤
│ FILE: glue_bronze_to_silver_etl.py                                  │
│ ENGINE: AWS Glue + Apache Spark                                     │
│ TRANSFORMATIONS:                                                     │
│   1. Remove duplicates (video_id + publish_time)                    │
│   2. Standardize column names (lowercase, underscores)              │
│   3. Handle null values (fill with 0 or defaults)                   │
│   4. Cast data types (views→Long, likes→Long, etc.)                 │
│   5. Parse timestamps (publish_time → timestamp)                    │
│   6. Extract date components (year, month, day, hour)               │
│   7. Calculate derived metrics:                                     │
│      - engagement_rate = (likes + comments) / views                 │
│      - like_ratio = likes / (likes + dislikes)                      │
│      - viral_score = views * engagement_rate / days_since_publish   │
│   8. Add data quality score                                         │
│   9. Filter low-quality records (quality_score < 0.8)               │
│ OUTPUT FORMAT: Parquet with Snappy compression                      │
│ PARTITIONING: By year, month, category_id                           │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    SILVER LAYER (PROCESSED)                          │
├─────────────────────────────────────────────────────────────────────┤
│ LOCATION: s3://youtube-analytics-processed-silver/                  │
│ FORMAT: Parquet (compressed)                                        │
│ CHARACTERISTICS:                                                     │
│   - Cleaned and standardized                                        │
│   - Type-safe data                                                  │
│   - Derived metrics included                                        │
│   - Partitioned for efficiency                                      │
│ GLUE TABLE: youtube_videos_silver                                   │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│              SILVER → GOLD TRANSFORMATION                            │
├─────────────────────────────────────────────────────────────────────┤
│ FILE: glue_silver_to_gold_etl.py                                    │
│ ENGINE: AWS Glue + Apache Spark                                     │
│ AGGREGATIONS CREATED:                                                │
│                                                                      │
│ 1. DAILY_METRICS                                                    │
│    - Group by: publish_date, category_id, channel_title            │
│    - Metrics: video_count, total_views, avg_views, etc.            │
│    - Partition: year, month                                         │
│                                                                      │
│ 2. CHANNEL_PERFORMANCE                                              │
│    - Group by: channel_title, category_id                           │
│    - Metrics: total_videos, total_views, avg_engagement, etc.      │
│    - Includes: posting_frequency, growth_rate                       │
│    - Partition: category_id                                         │
│                                                                      │
│ 3. CATEGORY_ANALYSIS                                                │
│    - Group by: category_id, publish_date                            │
│    - Metrics: avg_views, avg_engagement, unique_channels            │
│    - Includes: 7-day rolling averages                               │
│    - Partition: year, month, category_id                            │
│                                                                      │
│ 4. TRENDING_VIDEOS                                                  │
│    - Filter: High viral_score (top 10%)                             │
│    - Filter: Published within 7 days                                │
│    - Includes: trending_rank_in_category                            │
│    - Partition: publish_year, publish_month                         │
│                                                                      │
│ 5. POSTING_TIME_ANALYSIS                                            │
│    - Group by: publish_hour, day_of_week, category_id              │
│    - Metrics: avg_views, avg_engagement, viral_score               │
│    - Includes: is_optimal_time flag                                 │
│    - Partition: category_id                                         │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     GOLD LAYER (CURATED)                             │
├─────────────────────────────────────────────────────────────────────┤
│ LOCATION: s3://youtube-analytics-curated-gold/                      │
│ FORMAT: Parquet (compressed)                                        │
│ CHARACTERISTICS:                                                     │
│   - Business-level aggregations                                     │
│   - Analytics-ready tables                                          │
│   - ML-ready features                                               │
│   - Optimized for queries                                           │
│ GLUE TABLES:                                                         │
│   - daily_metrics                                                   │
│   - channel_performance                                             │
│   - category_analysis                                               │
│   - trending_videos                                                 │
│   - posting_time_analysis                                           │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    ↓                         ↓
┌──────────────────────────────┐  ┌──────────────────────────────┐
│     ANALYTICS PATH           │  │   MACHINE LEARNING PATH      │
└──────────────────────────────┘  └──────────────────────────────┘
                    │                         │
                    ↓                         ↓
┌─────────────────────────────────────────────────────────────────────┐
│                        ANALYTICS LAYER                               │
├─────────────────────────────────────────────────────────────────────┤
│ FILE: analytics_athena_queries.sql                                  │
│ ENGINE: Amazon Athena (Presto SQL)                                  │
│ DATABASE: youtube_analytics_db                                      │
│                                                                      │
│ QUERIES PROVIDED (12 total):                                        │
│ 1. Top performing videos by views                                   │
│ 2. Channel performance metrics                                      │
│ 3. Daily trending videos                                            │
│ 4. Category performance comparison                                  │
│ 5. Weekly growth trends                                             │
│ 6. Optimal posting time analysis                                    │
│ 7. High engagement videos analysis                                  │
│ 8. Channel consistency score                                        │
│ 9. Video performance by title characteristics                       │
│ 10. Month-over-month growth by category                             │
│ 11. Viral video identification                                      │
│ 12. Channel benchmark comparison                                    │
│                                                                      │
│ OUTPUT: Query results for dashboards                                │
└─────────────────────────────────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    VISUALIZATION LAYER                               │
├─────────────────────────────────────────────────────────────────────┤
│ TOOL: Amazon QuickSight                                             │
│ DASHBOARDS:                                                          │
│   - Channel Overview (KPIs, trends)                                 │
│   - Video Performance (scatter plots, distributions)                │
│   - Engagement Trends (time series, heatmaps)                       │
│   - Category Comparison (bar charts, benchmarks)                    │
│   - Posting Time Optimization (heatmap, recommendations)            │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                   FEATURE ENGINEERING                                │
├─────────────────────────────────────────────────────────────────────┤
│ FILE: features_engineering.py                                       │
│ INPUT: Gold layer tables                                            │
│ ENGINE: AWS Glue + Spark                                            │
│                                                                      │
│ FEATURES CREATED:                                                    │
│                                                                      │
│ 1. TEMPORAL FEATURES:                                               │
│    - Cyclical encoding (hour_sin, hour_cos, dow_sin, etc.)         │
│    - is_weekend, time_of_day categories                             │
│                                                                      │
│ 2. TEXT FEATURES:                                                   │
│    - title_length, title_word_count                                 │
│    - title_has_question, title_has_exclamation                      │
│    - description_length, tag_count                                  │
│                                                                      │
│ 3. CHANNEL FEATURES:                                                │
│    - channel_avg_views_historical                                   │
│    - channel_avg_engagement_historical                              │
│    - days_since_last_upload                                         │
│    - channel_consistency_score                                      │
│                                                                      │
│ 4. ROLLING FEATURES (7, 14, 30 day windows):                        │
│    - rolling_avg_views, rolling_avg_likes                           │
│    - rolling_avg_engagement                                         │
│    - rolling_sum_views, rolling_video_count                         │
│                                                                      │
│ 5. ENGAGEMENT FEATURES:                                             │
│    - likes_per_view, comments_per_view                              │
│    - engagement_velocity, viral_coefficient                         │
│                                                                      │
│ 6. CATEGORY FEATURES:                                               │
│    - category_avg_views, category_avg_engagement                    │
│    - views_vs_category_avg                                          │
│                                                                      │
│ OUTPUT LOCATION: s3://youtube-analytics-feature-store/              │
│ FORMAT: Parquet, partitioned by year/month                          │
└─────────────────────────────────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      FEATURE STORE                                   │
├─────────────────────────────────────────────────────────────────────┤
│ LOCATION: s3://youtube-analytics-feature-store/features/            │
│ FORMAT: Parquet                                                     │
│ CONTAINS: All engineered features + target variables                │
│ USED BY: ML training and inference                                  │
└─────────────────────────────────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      ML TRAINING                                     │
├─────────────────────────────────────────────────────────────────────┤
│ FILE: ml_model_training.py (Not created but documented)             │
│ ENGINE: Python + scikit-learn + XGBoost                             │
│                                                                      │
│ PROCESS:                                                             │
│ 1. Load features from feature store                                 │
│ 2. Split data (80% train, 10% val, 10% test)                        │
│ 3. Train multiple models:                                           │
│    - Linear Regression (baseline)                                   │
│    - Random Forest Regressor                                        │
│    - Gradient Boosting Regressor                                    │
│    - XGBoost Regressor (typically best)                             │
│ 4. Evaluate on validation set                                       │
│ 5. Select best model (highest R² score)                             │
│ 6. Final evaluation on test set                                     │
│ 7. Extract feature importance                                       │
│ 8. Save model + scaler + metadata to S3                             │
│                                                                      │
│ TARGET VARIABLE: views (video views count)                          │
│ METRICS: RMSE, MAE, R², MAPE                                        │
│ OUTPUT: s3://youtube-analytics-models/models/{model_name}/          │
└─────────────────────────────────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      MODEL REGISTRY                                  │
├─────────────────────────────────────────────────────────────────────┤
│ LOCATION: s3://youtube-analytics-models/                            │
│ STRUCTURE:                                                           │
│   models/                                                           │
│   └── {model_name}/                                                 │
│       └── {timestamp}/                                              │
│           ├── model.pkl         (trained model)                     │
│           ├── scaler.pkl        (feature scaler)                    │
│           └── metadata.json     (metrics, config)                   │
└─────────────────────────────────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      ML INFERENCE                                    │
├─────────────────────────────────────────────────────────────────────┤
│ FILE: ml_inference.py                                               │
│ ENGINE: AWS Lambda (for real-time) or Batch (for bulk)             │
│                                                                      │
│ PROCESS:                                                             │
│ 1. Load latest model from S3                                        │
│ 2. Receive video metadata (title, category, publish_time, etc.)    │
│ 3. Prepare features (same as training)                              │
│ 4. Scale features using saved scaler                                │
│ 5. Generate prediction (predicted views)                            │
│ 6. Add confidence intervals (if applicable)                         │
│ 7. Save predictions to S3 and/or DynamoDB                           │
│                                                                      │
│ INPUT: Video metadata (JSON)                                        │
│ OUTPUT: Predicted views + confidence + metadata                     │
└─────────────────────────────────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────────────────────────┐
│                  RECOMMENDATION ENGINE                               │
├─────────────────────────────────────────────────────────────────────┤
│ FILE: ml_recommendation_engine.py                                   │
│ ENGINE: Python + Pandas + Athena queries                            │
│                                                                      │
│ CAPABILITIES:                                                        │
│                                                                      │
│ 1. OPTIMAL POSTING TIMES BY CATEGORY:                               │
│    - Analyze historical performance by hour/day                     │
│    - Calculate composite score (views + engagement + viral)         │
│    - Return top N time slots                                        │
│                                                                      │
│ 2. OPTIMAL POSTING TIMES BY CHANNEL:                                │
│    - Channel-specific historical analysis                           │
│    - Personalized recommendations                                   │
│                                                                      │
│ 3. POSTING SCHEDULE GENERATION:                                     │
│    - Create weekly schedule (e.g., 3 videos/week)                   │
│    - Diversify across days and times                                │
│    - Maximize expected performance                                  │
│                                                                      │
│ 4. STRATEGY COMPARISON:                                             │
│    - Weekday vs Weekend                                             │
│    - Morning vs Afternoon vs Evening                                │
│    - Data-driven insights                                           │
│                                                                      │
│ OUTPUT: JSON with recommended times + expected metrics              │
└─────────────────────────────────────────────────────────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    PREDICTIONS & RECOMMENDATIONS                     │
├─────────────────────────────────────────────────────────────────────┤
│ LOCATION: s3://youtube-analytics-curated-gold/predictions/          │
│ LOCATION: s3://youtube-analytics-curated-gold/recommendations/      │
│ FORMAT: JSON                                                        │
│ CONSUMERS:                                                           │
│   - QuickSight dashboards                                           │
│   - External applications via API                                   │
│   - Business stakeholders                                           │
└─────────────────────────────────────────────────────────────────────┘

---

## ORCHESTRATION

┌─────────────────────────────────────────────────────────────────────┐
│                    STEP FUNCTIONS WORKFLOW                           │
├─────────────────────────────────────────────────────────────────────┤
│ FILE: orchestration_step_functions_workflow.json                    │
│                                                                      │
│ WORKFLOW STAGES:                                                     │
│                                                                      │
│ 1. ValidateInput                                                    │
│    └→ Lambda: Validate input parameters                             │
│                                                                      │
│ 2. ParallelIngestion (Parallel branches)                            │
│    ├→ TriggerGlueCrawler: Update data catalog                       │
│    └→ DataQualityCheck: Validate data quality                       │
│                                                                      │
│ 3. BronzeToSilverETL                                                │
│    └→ Glue Job: bronze_to_silver_etl                                │
│                                                                      │
│ 4. SilverToGoldETL                                                  │
│    └→ Glue Job: silver_to_gold_etl                                  │
│                                                                      │
│ 5. ParallelAnalytics (Parallel branches)                            │
│    ├→ FeatureEngineering: Glue job                                  │
│    ├→ UpdateAthenaCatalog: Lambda                                   │
│    └→ RefreshDashboards: Lambda (QuickSight)                        │
│                                                                      │
│ 6. CheckMLTrainingSchedule                                          │
│    └→ Conditional: Trigger ML if scheduled                          │
│                                                                      │
│ 7. MLPipeline (Parallel branches, if triggered)                     │
│    ├→ ModelTraining: SageMaker training job                         │
│    │  └→ ModelEvaluation: Lambda                                    │
│    │     └→ RegisterModel: Lambda (if quality acceptable)           │
│    └→ GenerateRecommendations: Lambda                               │
│                                                                      │
│ 8. NotifySuccess/Failure                                            │
│    └→ SNS: Send notification                                        │
│                                                                      │
│ RETRY STRATEGY:                                                      │
│   - Max attempts: 3                                                 │
│   - Backoff rate: 2.0                                               │
│   - Interval: 60-120 seconds                                        │
│                                                                      │
│ ERROR HANDLING:                                                      │
│   - Catch blocks for each major stage                               │
│   - SNS notifications on failures                                   │
│   - Partial success handling                                        │
└─────────────────────────────────────────────────────────────────────┘

---

## DATA SOURCE DETAILS

### 1. KAGGLE DATASET
- **Source**: datasnaek/youtube-new
- **File**: ingestion_data_ingestion.py (download_kaggle_dataset method)
- **Format**: CSV files
- **Regions**: US, GB, CA, DE, FR, etc.
- **Columns**: video_id, title, channel_title, category_id, publish_time, views, 
              likes, dislikes, comment_count, tags, thumbnail_link, etc.
- **Update Frequency**: Daily (when dataset is updated)
- **Requires**: Kaggle API credentials (~/.kaggle/kaggle.json)

### 2. YOUTUBE DATA API v3
- **Source**: Google YouTube Data API
- **File**: ingestion_data_ingestion.py (ingest_from_youtube_api method)
- **Endpoint**: videos().list(chart='mostPopular')
- **Requires**: YouTube API key (YOUTUBE_API_KEY env variable)
- **Quota**: 10,000 units/day (free tier)
- **Update Frequency**: Real-time
- **Limitation**: No longer provides dislike count

### 3. SAMPLE DATA GENERATOR
- **Source**: Synthetic data
- **File**: ingestion_data_ingestion.py (load_sample_data method)
- **Purpose**: Testing and development
- **Records**: 1000 sample videos
- **Distributions**: Log-normal for views, likes, comments
- **Categories**: 14 different categories
- **Time Range**: 365 days from 2024-01-01

---

## FILE USAGE MAPPING

| File | Purpose | Input | Output | Data Source Used |
|------|---------|-------|--------|------------------|
| ingestion_data_ingestion.py | Download/fetch data | Kaggle/API/Generator | CSV to S3 raw | ALL 3 sources |
| lambda_ingestion_trigger.py | Validate uploads | S3 PUT event | Glue crawler trigger | S3 raw bucket |
| glue_bronze_to_silver_etl.py | Clean data | Bronze layer | Silver layer | Bronze S3 |
| glue_silver_to_gold_etl.py | Create aggregations | Silver layer | Gold layer | Silver S3 |
| features_engineering.py | Generate ML features | Gold layer | Feature store | Gold S3 |
| ml_inference.py | Predict views | Video metadata | Predictions | Feature store |
| ml_recommendation_engine.py | Recommend times | Posting analysis | Recommendations | Gold S3 |
| analytics_athena_queries.sql | Query data | Gold tables | Query results | Gold S3 via Athena |

---

## CONFIGURATION FILES

| File | Contains | Used By |
|------|----------|---------|
| config_env.example | AWS config, bucket names, API keys | All scripts |
| config_pipeline_config.yaml | ETL config, ML config, schedules | Glue jobs, Step Functions |
| infra_iam_glue_etl_policy.json | IAM permissions | AWS IAM roles |
| requirements.txt | Python dependencies | All Python scripts |

---

## EXECUTION ORDER

1. **Initial Setup** (One-time)
   - Create S3 buckets
   - Deploy IAM roles
   - Create Glue database
   - Deploy Lambda functions
   - Upload Glue scripts
   - Create Glue jobs
   - Deploy Step Functions

2. **Data Ingestion** (Daily)
   - Run: ingestion_data_ingestion.py
   - Triggers: lambda_ingestion_trigger.py (automatic)

3. **ETL Pipeline** (Scheduled)
   - Step Functions orchestrates:
     - Bronze → Silver ETL
     - Silver → Gold ETL
     - Feature Engineering

4. **Analytics** (On-demand)
   - Run Athena queries
   - View QuickSight dashboards

5. **ML Pipeline** (Monthly or triggered)
   - Feature engineering
   - Model training
   - Model evaluation
   - Generate recommendations

---

## MISSING COMPONENTS (Optional)

These are not critical for the core functionality but would enhance production readiness:

1. **Testing**
   - test_ingestion.py
   - test_etl_pipeline.py
   - test_ml_models.py

2. **Monitoring**
   - CloudWatch dashboard configuration
   - Custom metrics collection
   - Anomaly detection

3. **Infrastructure as Code**
   - Terraform files for AWS resources
   - CloudFormation templates

4. **CI/CD**
   - GitHub Actions / Jenkins pipeline
   - Deployment automation

5. **Data Catalog**
   - Glue crawler configuration files
   - Table schema definitions

6. **Advanced Features**
   - Real-time streaming (Kinesis)
   - Advanced NLP for content analysis
   - Computer vision for thumbnails
   - Multi-model ensemble

---

## NEXT STEPS TO RUN

1. Set environment variables from config_env.example
2. Run ingestion_data_ingestion.py to load initial data
3. Deploy Lambda and Glue jobs to AWS
4. Execute Step Functions workflow
5. Query results using Athena queries
6. View dashboards in QuickSight
