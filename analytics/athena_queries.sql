-- Athena SQL Queries for YouTube Analytics
-- Database: youtube_analytics_db

-- ============================================
-- 1. Top Performing Videos by Views
-- ============================================
SELECT 
    video_id,
    title,
    channel_title,
    category_id,
    views,
    likes,
    comment_count,
    engagement_rate,
    publish_date,
    RANK() OVER (ORDER BY views DESC) as view_rank
FROM youtube_videos_silver
WHERE publish_year = 2024
ORDER BY views DESC
LIMIT 100;

-- ============================================
-- 2. Channel Performance Metrics
-- ============================================
SELECT 
    channel_title,
    COUNT(DISTINCT video_id) as total_videos,
    SUM(views) as total_views,
    AVG(views) as avg_views_per_video,
    SUM(likes) as total_likes,
    AVG(engagement_rate) as avg_engagement_rate,
    MIN(publish_date) as first_video_date,
    MAX(publish_date) as latest_video_date
FROM youtube_videos_silver
GROUP BY channel_title
HAVING COUNT(DISTINCT video_id) >= 10
ORDER BY total_views DESC
LIMIT 50;

-- ============================================
-- 3. Daily Trending Videos
-- ============================================
SELECT 
    publish_date,
    video_id,
    title,
    channel_title,
    category_id,
    views,
    engagement_rate,
    viral_score,
    ROW_NUMBER() OVER (PARTITION BY publish_date ORDER BY viral_score DESC) as daily_rank
FROM youtube_videos_silver
WHERE days_since_publish <= 7
  AND viral_score > (SELECT PERCENTILE_APPROX(viral_score, 0.9) FROM youtube_videos_silver)
ORDER BY publish_date DESC, viral_score DESC;

-- ============================================
-- 4. Category Performance Comparison
-- ============================================
SELECT 
    category_id,
    COUNT(video_id) as video_count,
    AVG(views) as avg_views,
    AVG(likes) as avg_likes,
    AVG(comment_count) as avg_comments,
    AVG(engagement_rate) as avg_engagement,
    STDDEV(views) as views_stddev,
    PERCENTILE_APPROX(views, 0.5) as median_views,
    PERCENTILE_APPROX(views, 0.9) as p90_views
FROM youtube_videos_silver
WHERE publish_year = 2024
GROUP BY category_id
ORDER BY avg_views DESC;

-- ============================================
-- 5. Weekly Growth Trends
-- ============================================
WITH weekly_metrics AS (
    SELECT 
        DATE_TRUNC('week', publish_date) as week_start,
        COUNT(video_id) as videos_published,
        SUM(views) as total_views,
        AVG(engagement_rate) as avg_engagement
    FROM youtube_videos_silver
    GROUP BY DATE_TRUNC('week', publish_date)
),
growth_calc AS (
    SELECT 
        week_start,
        videos_published,
        total_views,
        avg_engagement,
        LAG(total_views) OVER (ORDER BY week_start) as prev_week_views,
        LAG(avg_engagement) OVER (ORDER BY week_start) as prev_week_engagement
    FROM weekly_metrics
)
SELECT 
    week_start,
    videos_published,
    total_views,
    avg_engagement,
    CASE 
        WHEN prev_week_views > 0 THEN 
            ((total_views - prev_week_views) / prev_week_views) * 100
        ELSE NULL
    END as views_growth_pct,
    CASE 
        WHEN prev_week_engagement > 0 THEN 
            ((avg_engagement - prev_week_engagement) / prev_week_engagement) * 100
        ELSE NULL
    END as engagement_growth_pct
FROM growth_calc
ORDER BY week_start DESC
LIMIT 52;

-- ============================================
-- 6. Optimal Posting Time Analysis
-- ============================================
SELECT 
    publish_hour,
    publish_day_of_week,
    CASE publish_day_of_week
        WHEN 1 THEN 'Sunday'
        WHEN 2 THEN 'Monday'
        WHEN 3 THEN 'Tuesday'
        WHEN 4 THEN 'Wednesday'
        WHEN 5 THEN 'Thursday'
        WHEN 6 THEN 'Friday'
        WHEN 7 THEN 'Saturday'
    END as day_name,
    COUNT(video_id) as videos_published,
    AVG(views) as avg_views,
    AVG(engagement_rate) as avg_engagement,
    AVG(viral_score) as avg_viral_score,
    PERCENTILE_APPROX(views, 0.75) as p75_views
FROM youtube_videos_silver
GROUP BY publish_hour, publish_day_of_week
ORDER BY avg_viral_score DESC
LIMIT 50;

-- ============================================
-- 7. High Engagement Videos Analysis
-- ============================================
SELECT 
    video_id,
    title,
    channel_title,
    category_id,
    views,
    likes,
    comment_count,
    engagement_rate,
    like_ratio,
    comment_ratio,
    title_length,
    description_length,
    tag_count,
    publish_hour,
    publish_day_of_week
FROM youtube_videos_silver
WHERE engagement_rate >= (SELECT PERCENTILE_APPROX(engagement_rate, 0.9) FROM youtube_videos_silver)
  AND views >= 10000
ORDER BY engagement_rate DESC
LIMIT 100;

-- ============================================
-- 8. Channel Consistency Score
-- ============================================
WITH channel_posting_pattern AS (
    SELECT 
        channel_title,
        publish_date,
        LAG(publish_date) OVER (PARTITION BY channel_title ORDER BY publish_date) as prev_publish_date
    FROM youtube_videos_silver
),
channel_consistency AS (
    SELECT 
        channel_title,
        AVG(DATE_DIFF('day', prev_publish_date, publish_date)) as avg_days_between_posts,
        STDDEV(DATE_DIFF('day', prev_publish_date, publish_date)) as stddev_days_between_posts,
        COUNT(DISTINCT publish_date) as posting_days
    FROM channel_posting_pattern
    WHERE prev_publish_date IS NOT NULL
    GROUP BY channel_title
)
SELECT 
    c.channel_title,
    c.avg_days_between_posts,
    c.stddev_days_between_posts,
    c.posting_days,
    CASE 
        WHEN c.stddev_days_between_posts IS NULL OR c.stddev_days_between_posts = 0 THEN 1.0
        ELSE 1.0 / (1.0 + c.stddev_days_between_posts)
    END as consistency_score,
    v.total_videos,
    v.avg_views
FROM channel_consistency c
JOIN (
    SELECT 
        channel_title,
        COUNT(video_id) as total_videos,
        AVG(views) as avg_views
    FROM youtube_videos_silver
    GROUP BY channel_title
) v ON c.channel_title = v.channel_title
WHERE v.total_videos >= 10
ORDER BY consistency_score DESC, v.avg_views DESC
LIMIT 100;

-- ============================================
-- 9. Video Performance by Title Characteristics
-- ============================================
SELECT 
    CASE 
        WHEN title_has_question = 1 THEN 'Has Question'
        WHEN title_has_exclamation = 1 THEN 'Has Exclamation'
        WHEN title_has_numbers = 1 THEN 'Has Numbers'
        ELSE 'Standard'
    END as title_type,
    COUNT(video_id) as video_count,
    AVG(views) as avg_views,
    AVG(engagement_rate) as avg_engagement,
    PERCENTILE_APPROX(views, 0.5) as median_views,
    PERCENTILE_APPROX(views, 0.9) as p90_views
FROM youtube_videos_silver
WHERE title_length BETWEEN 20 AND 100
GROUP BY 
    CASE 
        WHEN title_has_question = 1 THEN 'Has Question'
        WHEN title_has_exclamation = 1 THEN 'Has Exclamation'
        WHEN title_has_numbers = 1 THEN 'Has Numbers'
        ELSE 'Standard'
    END
ORDER BY avg_views DESC;

-- ============================================
-- 10. Month-over-Month Growth by Category
-- ============================================
WITH monthly_category_metrics AS (
    SELECT 
        category_id,
        publish_year,
        publish_month,
        COUNT(video_id) as video_count,
        SUM(views) as total_views,
        AVG(engagement_rate) as avg_engagement
    FROM youtube_videos_silver
    GROUP BY category_id, publish_year, publish_month
),
growth_calculation AS (
    SELECT 
        category_id,
        publish_year,
        publish_month,
        video_count,
        total_views,
        avg_engagement,
        LAG(total_views) OVER (PARTITION BY category_id ORDER BY publish_year, publish_month) as prev_month_views
    FROM monthly_category_metrics
)
SELECT 
    category_id,
    publish_year,
    publish_month,
    video_count,
    total_views,
    avg_engagement,
    CASE 
        WHEN prev_month_views > 0 THEN 
            ((total_views - prev_month_views) / prev_month_views) * 100
        ELSE NULL
    END as mom_growth_pct
FROM growth_calculation
WHERE publish_year = 2024
ORDER BY category_id, publish_year DESC, publish_month DESC;

-- ============================================
-- 11. Viral Video Identification
-- ============================================
SELECT 
    v.video_id,
    v.title,
    v.channel_title,
    v.category_id,
    v.views,
    v.engagement_rate,
    v.viral_score,
    v.days_since_publish,
    v.views / NULLIF(v.days_since_publish, 0) as views_per_day,
    c.avg_views as channel_avg_views,
    v.views / NULLIF(c.avg_views, 0) as performance_vs_channel_avg
FROM youtube_videos_silver v
JOIN (
    SELECT 
        channel_title,
        AVG(views) as avg_views
    FROM youtube_videos_silver
    GROUP BY channel_title
) c ON v.channel_title = c.channel_title
WHERE v.viral_score > (SELECT PERCENTILE_APPROX(viral_score, 0.95) FROM youtube_videos_silver)
  AND v.days_since_publish <= 30
  AND v.views / NULLIF(c.avg_views, 0) >= 2.0
ORDER BY v.viral_score DESC
LIMIT 50;

-- ============================================
-- 12. Channel Benchmark Comparison
-- ============================================
WITH channel_metrics AS (
    SELECT 
        channel_title,
        category_id,
        COUNT(video_id) as total_videos,
        AVG(views) as avg_views,
        AVG(engagement_rate) as avg_engagement,
        AVG(viral_score) as avg_viral_score
    FROM youtube_videos_silver
    GROUP BY channel_title, category_id
    HAVING COUNT(video_id) >= 5
),
category_benchmarks AS (
    SELECT 
        category_id,
        PERCENTILE_APPROX(avg_views, 0.25) as p25_views,
        PERCENTILE_APPROX(avg_views, 0.5) as p50_views,
        PERCENTILE_APPROX(avg_views, 0.75) as p75_views,
        PERCENTILE_APPROX(avg_engagement, 0.5) as p50_engagement
    FROM channel_metrics
    GROUP BY category_id
)
SELECT 
    cm.channel_title,
    cm.category_id,
    cm.total_videos,
    cm.avg_views,
    cb.p50_views as category_median_views,
    cm.avg_engagement,
    cb.p50_engagement as category_median_engagement,
    CASE 
        WHEN cm.avg_views >= cb.p75_views THEN 'Top Performer'
        WHEN cm.avg_views >= cb.p50_views THEN 'Above Average'
        WHEN cm.avg_views >= cb.p25_views THEN 'Average'
        ELSE 'Below Average'
    END as performance_tier
FROM channel_metrics cm
JOIN category_benchmarks cb ON cm.category_id = cb.category_id
ORDER BY cm.avg_views DESC
LIMIT 100;
