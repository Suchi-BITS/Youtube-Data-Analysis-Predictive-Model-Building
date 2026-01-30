import json
import requests

def fetch_youtube_data(api_key, channel_id):
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "maxResults": 50,
        "key": api_key
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

def save_raw_data(data, output_path):
    with open(output_path, "w") as f:
        json.dump(data, f)
