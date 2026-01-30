SELECT
  channel_title,
  COUNT(video_id) AS total_videos,
  SUM(view_count) AS total_views
FROM youtube_curated.videos
GROUP BY channel_title;
