def load(df):
    df.write.mode("overwrite").parquet(
        "s3://youtube-curated-data/videos/"
    )
