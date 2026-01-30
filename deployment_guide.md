# YouTube Analytics Platform - Deployment Guide

## Prerequisites

- AWS Account with admin access
- AWS CLI configured
- Python 3.9 or higher
- Kaggle account (optional, for dataset)
- YouTube API key (optional, for real-time data)

## Step-by-Step Deployment

### Phase 1: Environment Setup

#### 1.1 Install Dependencies
```bash
pip install -r requirements.txt
pip install awscli boto3 kaggle
```

#### 1.2 Configure AWS CLI
```bash
aws configure
# Enter your AWS Access Key ID
# Enter your AWS Secret Access Key
# Default region: us-east-1
# Default output format: json
```

#### 1.3 Set Environment Variables
```bash
cp config_env.example .env
# Edit .env file with your AWS account ID and configurations
source .env
```

### Phase 2: Infrastructure Setup

#### 2.1 Create S3 Buckets
```bash
# Raw data bucket
aws s3 mb s3://${S3_RAW_BUCKET} --region ${AWS_REGION}
aws s3api put-bucket-encryption \
  --bucket ${S3_RAW_BUCKET} \
  --server-side-encryption-configuration '{"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}'

# Processed data bucket
aws s3 mb s3://${S3_PROCESSED_BUCKET} --region ${AWS_REGION}
aws s3api put-bucket-encryption \
  --bucket ${S3_PROCESSED_BUCKET} \
  --server-side-encryption-configuration '{"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}'

# Curated data bucket
aws s3 mb s3://${S3_CURATED_BUCKET} --region ${AWS_REGION}
aws s3api put-bucket-encryption \
  --bucket ${S3_CURATED_BUCKET} \
  --server-side-encryption-configuration '{"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}'

# Scripts bucket
aws s3 mb s3://${S3_SCRIPTS_BUCKET} --region ${AWS_REGION}

# Models bucket
aws s3 mb s3://${MODEL_BUCKET} --region ${AWS_REGION}

# Feature store bucket
aws s3 mb s3://${FEATURE_STORE_BUCKET} --region ${AWS_REGION}

# Athena results bucket
aws s3 mb s3://${ATHENA_OUTPUT_BUCKET} --region ${AWS_REGION}
```

#### 2.2 Create IAM Roles

**Glue ETL Role:**
```bash
# Create trust policy
cat > glue-assume-role-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "glue.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create role
aws iam create-role \
  --role-name GlueETLRole \
  --assume-role-policy-document file://glue-assume-role-policy.json

# Attach policies
aws iam put-role-policy \
  --role-name GlueETLRole \
  --policy-name GlueETLPolicy \
  --policy-document file://infra_iam_glue_etl_policy.json

aws iam attach-role-policy \
  --role-name GlueETLRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole
```

**Lambda Execution Role:**
```bash
cat > lambda-assume-role-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

aws iam create-role \
  --role-name LambdaIngestionRole \
  --assume-role-policy-document file://lambda-assume-role-policy.json

aws iam attach-role-policy \
  --role-name LambdaIngestionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

aws iam attach-role-policy \
  --role-name LambdaIngestionRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess

aws iam attach-role-policy \
  --role-name LambdaIngestionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole
```

#### 2.3 Create Glue Database
```bash
aws glue create-database \
  --database-input '{
    "Name": "youtube_analytics_db",
    "Description": "YouTube Analytics Database"
  }'
```

#### 2.4 Create SNS Topic for Notifications
```bash
aws sns create-topic --name youtube-analytics-alerts

# Subscribe to email
aws sns subscribe \
  --topic-arn arn:aws:sns:${AWS_REGION}:${AWS_ACCOUNT_ID}:youtube-analytics-alerts \
  --protocol email \
  --notification-endpoint your-email@example.com
```

### Phase 3: Deploy Lambda Functions

#### 3.1 Package and Deploy Ingestion Trigger
```bash
cd /path/to/lambda
zip ingestion_trigger.zip lambda_ingestion_trigger.py

aws lambda create-function \
  --function-name youtube-ingestion-trigger \
  --runtime python3.9 \
  --role arn:aws:iam::${AWS_ACCOUNT_ID}:role/LambdaIngestionRole \
  --handler lambda_ingestion_trigger.lambda_handler \
  --zip-file fileb://ingestion_trigger.zip \
  --timeout 300 \
  --memory-size 512 \
  --environment Variables="{
    GLUE_DATABASE_NAME=youtube_analytics_db,
    SNS_TOPIC_ARN=arn:aws:sns:${AWS_REGION}:${AWS_ACCOUNT_ID}:youtube-analytics-alerts,
    S3_PROCESSED_BUCKET=${S3_PROCESSED_BUCKET}
  }"
```

#### 3.2 Add S3 Trigger
```bash
aws s3api put-bucket-notification-configuration \
  --bucket ${S3_RAW_BUCKET} \
  --notification-configuration '{
    "LambdaFunctionConfigurations": [
      {
        "LambdaFunctionArn": "arn:aws:lambda:'${AWS_REGION}':'${AWS_ACCOUNT_ID}':function:youtube-ingestion-trigger",
        "Events": ["s3:ObjectCreated:*"],
        "Filter": {
          "Key": {
            "FilterRules": [
              {
                "Name": "prefix",
                "Value": "raw/youtube/"
              },
              {
                "Name": "suffix",
                "Value": ".csv"
              }
            ]
          }
        }
      }
    ]
  }'

# Grant S3 permission to invoke Lambda
aws lambda add-permission \
  --function-name youtube-ingestion-trigger \
  --statement-id s3-invoke-permission \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn arn:aws:s3:::${S3_RAW_BUCKET}
```

### Phase 4: Deploy Glue Jobs

#### 4.1 Upload Glue Scripts to S3
```bash
aws s3 cp glue_bronze_to_silver_etl.py s3://${S3_SCRIPTS_BUCKET}/glue/
aws s3 cp glue_silver_to_gold_etl.py s3://${S3_SCRIPTS_BUCKET}/glue/
aws s3 cp features_engineering.py s3://${S3_SCRIPTS_BUCKET}/glue/
```

#### 4.2 Create Glue Crawler
```bash
aws glue create-crawler \
  --name youtube-raw-crawler \
  --role arn:aws:iam::${AWS_ACCOUNT_ID}:role/GlueETLRole \
  --database-name youtube_analytics_db \
  --targets '{
    "S3Targets": [
      {
        "Path": "s3://'${S3_RAW_BUCKET}'/raw/youtube/"
      }
    ]
  }'
```

#### 4.3 Create Glue ETL Jobs
```bash
# Bronze to Silver
aws glue create-job \
  --name bronze-to-silver-etl \
  --role arn:aws:iam::${AWS_ACCOUNT_ID}:role/GlueETLRole \
  --command '{
    "Name": "glueetl",
    "ScriptLocation": "s3://'${S3_SCRIPTS_BUCKET}'/glue/glue_bronze_to_silver_etl.py",
    "PythonVersion": "3"
  }' \
  --default-arguments '{
    "--TempDir": "s3://'${S3_SCRIPTS_BUCKET}'/temp/",
    "--job-language": "python",
    "--RAW_BUCKET": "'${S3_RAW_BUCKET}'",
    "--PROCESSED_BUCKET": "'${S3_PROCESSED_BUCKET}'"
  }' \
  --max-retries 3 \
  --timeout 2880 \
  --glue-version "3.0" \
  --number-of-workers 5 \
  --worker-type G.1X

# Silver to Gold
aws glue create-job \
  --name silver-to-gold-etl \
  --role arn:aws:iam::${AWS_ACCOUNT_ID}:role/GlueETLRole \
  --command '{
    "Name": "glueetl",
    "ScriptLocation": "s3://'${S3_SCRIPTS_BUCKET}'/glue/glue_silver_to_gold_etl.py",
    "PythonVersion": "3"
  }' \
  --default-arguments '{
    "--TempDir": "s3://'${S3_SCRIPTS_BUCKET}'/temp/",
    "--job-language": "python",
    "--PROCESSED_BUCKET": "'${S3_PROCESSED_BUCKET}'",
    "--CURATED_BUCKET": "'${S3_CURATED_BUCKET}'"
  }' \
  --max-retries 3 \
  --timeout 2880 \
  --glue-version "3.0" \
  --number-of-workers 5 \
  --worker-type G.1X

# Feature Engineering
aws glue create-job \
  --name feature-engineering \
  --role arn:aws:iam::${AWS_ACCOUNT_ID}:role/GlueETLRole \
  --command '{
    "Name": "glueetl",
    "ScriptLocation": "s3://'${S3_SCRIPTS_BUCKET}'/glue/features_engineering.py",
    "PythonVersion": "3"
  }' \
  --default-arguments '{
    "--TempDir": "s3://'${S3_SCRIPTS_BUCKET}'/temp/",
    "--job-language": "python",
    "--CURATED_BUCKET": "'${S3_CURATED_BUCKET}'",
    "--FEATURE_STORE_BUCKET": "'${FEATURE_STORE_BUCKET}'"
  }' \
  --max-retries 2 \
  --timeout 2880 \
  --glue-version "3.0" \
  --number-of-workers 5 \
  --worker-type G.1X
```

### Phase 5: Deploy Step Functions

#### 5.1 Create Step Functions Role
```bash
cat > stepfunctions-assume-role-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "states.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

aws iam create-role \
  --role-name StepFunctionsRole \
  --assume-role-policy-document file://stepfunctions-assume-role-policy.json

aws iam attach-role-policy \
  --role-name StepFunctionsRole \
  --policy-arn arn:aws:iam::aws:policy/AWSGlueConsoleFullAccess

aws iam attach-role-policy \
  --role-name StepFunctionsRole \
  --policy-arn arn:aws:iam::aws:policy/AWSLambda_FullAccess

aws iam attach-role-policy \
  --role-name StepFunctionsRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonSNSFullAccess
```

#### 5.2 Create State Machine
```bash
# Update workflow JSON with actual ARNs
sed -i "s/\${AWS_REGION}/${AWS_REGION}/g" orchestration_step_functions_workflow.json
sed -i "s/\${ACCOUNT_ID}/${AWS_ACCOUNT_ID}/g" orchestration_step_functions_workflow.json

aws stepfunctions create-state-machine \
  --name youtube-analytics-pipeline \
  --definition file://orchestration_step_functions_workflow.json \
  --role-arn arn:aws:iam::${AWS_ACCOUNT_ID}:role/StepFunctionsRole
```

#### 5.3 Schedule Execution (Optional)
```bash
aws events put-rule \
  --name youtube-analytics-daily \
  --schedule-expression "cron(0 2 * * ? *)" \
  --state ENABLED

aws events put-targets \
  --rule youtube-analytics-daily \
  --targets "Id"="1","Arn"="arn:aws:states:${AWS_REGION}:${AWS_ACCOUNT_ID}:stateMachine:youtube-analytics-pipeline","RoleArn"="arn:aws:iam::${AWS_ACCOUNT_ID}:role/StepFunctionsRole"
```

### Phase 6: Initial Data Ingestion

#### 6.1 Run Ingestion Script
```bash
python ingestion_data_ingestion.py
```

This will:
- Generate sample data (or download from Kaggle if configured)
- Upload to S3 raw bucket
- Trigger Lambda validation
- Start Glue crawler

#### 6.2 Verify Data
```bash
# Check S3
aws s3 ls s3://${S3_RAW_BUCKET}/raw/youtube/

# Check Glue tables
aws glue get-tables --database-name youtube_analytics_db
```

### Phase 7: Run ETL Pipeline

#### 7.1 Manual Execution
```bash
# Start Step Functions
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:${AWS_REGION}:${AWS_ACCOUNT_ID}:stateMachine:youtube-analytics-pipeline \
  --input '{
    "trigger_ml_training": false
  }'
```

#### 7.2 Monitor Execution
```bash
# Get execution ARN from previous command, then:
aws stepfunctions describe-execution \
  --execution-arn <execution-arn>
```

### Phase 8: Query and Visualize

#### 8.1 Setup Athena
```bash
# Create workgroup
aws athena create-work-group \
  --name youtube-analytics-workgroup \
  --configuration ResultConfigurationUpdates={OutputLocation=s3://${ATHENA_OUTPUT_BUCKET}/}
```

#### 8.2 Run Sample Query
```bash
# Copy analytics_athena_queries.sql queries to Athena console
# Or use AWS CLI:
aws athena start-query-execution \
  --query-string "SELECT * FROM youtube_analytics_db.youtube_videos_silver LIMIT 10;" \
  --result-configuration OutputLocation=s3://${ATHENA_OUTPUT_BUCKET}/ \
  --work-group youtube-analytics-workgroup
```

#### 8.3 Setup QuickSight (Optional)
- Navigate to QuickSight console
- Create new dataset from Athena
- Select youtube_analytics_db
- Build dashboards using curated tables

### Phase 9: ML Pipeline (Optional)

#### 9.1 Train Model
```bash
# This would typically be triggered by Step Functions
# For manual execution:
python ml_model_training.py
```

#### 9.2 Generate Recommendations
```bash
python ml_recommendation_engine.py
```

## Validation Checklist

- [ ] S3 buckets created and encrypted
- [ ] IAM roles created with proper permissions
- [ ] Glue database created
- [ ] Lambda function deployed and triggered by S3
- [ ] Glue crawler created
- [ ] Glue ETL jobs created
- [ ] Step Functions state machine created
- [ ] Initial data uploaded to S3
- [ ] Bronze layer populated
- [ ] Silver layer created with cleaned data
- [ ] Gold layer created with aggregations
- [ ] Athena queries work
- [ ] SNS notifications received

## Troubleshooting

### Lambda Not Triggering
```bash
# Check Lambda logs
aws logs tail /aws/lambda/youtube-ingestion-trigger --follow

# Verify S3 event configuration
aws s3api get-bucket-notification-configuration --bucket ${S3_RAW_BUCKET}
```

### Glue Job Failures
```bash
# Check Glue job logs in CloudWatch
aws logs tail /aws-glue/jobs/logs-v2 --follow

# Check job run details
aws glue get-job-runs --job-name bronze-to-silver-etl
```

### Step Functions Errors
```bash
# Describe execution
aws stepfunctions describe-execution --execution-arn <arn>

# Get execution history
aws stepfunctions get-execution-history --execution-arn <arn>
```

## Cost Estimation

Monthly cost estimate (approximate):

- S3 Storage (100 GB): $2.30
- Glue ETL (10 DPU-hours/day): $13.20
- Athena Queries (100 GB scanned): $5.00
- Lambda (1M requests): $0.20
- Step Functions (1000 executions): $0.25
- CloudWatch Logs: $0.50

**Total: ~$21.45/month**

## Next Steps

1. Configure Kaggle API for real data
2. Set up QuickSight dashboards
3. Implement ML model training
4. Add data quality monitoring
5. Set up alerting rules
6. Implement cost optimization
7. Add unit tests
8. Document business logic
9. Train team on system usage
10. Plan for scaling

## Support

For issues:
- Check CloudWatch logs
- Review Step Functions execution history
- Validate IAM permissions
- Check S3 bucket policies
