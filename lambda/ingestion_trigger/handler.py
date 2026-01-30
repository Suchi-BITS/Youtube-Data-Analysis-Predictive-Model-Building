import json
import boto3

def lambda_handler(event, context):
    glue = boto3.client("glue")
    glue.start_job_run(JobName="youtube_etl_job")
    return {
        "statusCode": 200,
        "body": json.dumps("Glue job triggered")
    }
