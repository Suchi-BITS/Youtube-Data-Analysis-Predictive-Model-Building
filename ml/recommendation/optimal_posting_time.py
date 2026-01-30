def recommend(df):
    return (
        df.groupby("publish_hour")["engagement_rate"]
        .mean()
        .sort_values(ascending=False)
        .head(3)
    )
