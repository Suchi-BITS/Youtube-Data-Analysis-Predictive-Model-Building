REQUIRED_FIELDS = ["video_id", "published_at", "title"]

def validate_record(record):
    missing = [f for f in REQUIRED_FIELDS if f not in record]
    return len(missing) == 0
