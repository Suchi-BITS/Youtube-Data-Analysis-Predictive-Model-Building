import pandas as pd
from sklearn.ensemble import RandomForestRegressor

def train(df):
    X = df.drop(columns=["views"])
    y = df["views"]
    model = RandomForestRegressor()
    model.fit(X, y)
    return model
