from pyspark.sql.functions import col, to_timestamp

def transform(df):
    return (
        df
        .withColumn("published_at", to_timestamp(col("publishedAt")))
        .withColumn("engagement_rate",
                    (col("likeCount") + col("commentCount")) / col("viewCount"))
        .dropna()
    )
