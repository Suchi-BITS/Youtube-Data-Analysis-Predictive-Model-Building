def detect_drift(reference_mean, current_mean, threshold=0.2):
    return abs(reference_mean - current_mean) > threshold
