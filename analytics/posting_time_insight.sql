SELECT
  hour(published_at) AS publish_hour,
  AVG(engagement_rate) AS avg_engagement
FROM youtube_curated.videos
GROUP BY publish_hour
ORDER BY avg_engagement DESC;
