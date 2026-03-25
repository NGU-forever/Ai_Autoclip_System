from datetime import timedelta, datetime
from pathlib import Path

from src.uploader.conf import BASE_DIR


def get_absolute_path(relative_path: str, base_dir: str = None) -> str:
    if base_dir:
        absolute_path = Path(BASE_DIR) / base_dir / relative_path
    else:
        absolute_path = Path(BASE_DIR) / relative_path
    return str(absolute_path)


def get_title_and_hashtags(filename):
    """
    获取视频标题和 hashtag
    Args:
        filename: 视频文件名
    Returns:
        视频标题和 hashtag 列表
    """
    txt_filename = filename.replace(".mp4", ".txt")
    with open(txt_filename, "r", encoding="utf-8") as f:
        content = f.read()
    splite_str = content.strip().split("\n")
    title = splite_str[0]
    hashtags = splite_str[1].replace("#", "").split(" ")
    return title, hashtags


def generate_schedule_time_next_day(total_videos, videos_per_day=1, daily_times=None, timestamps=False, start_days=0):
    if videos_per_day <= 0:
        raise ValueError("videos_per_day should be a positive integer")
    if daily_times is None:
        daily_times = [6, 11, 14, 16, 22]
    if videos_per_day > len(daily_times):
        raise ValueError("videos_per_day should not exceed the length of daily_times")

    schedule = []
    current_time = datetime.now()
    for video in range(total_videos):
        day = video // videos_per_day + start_days + 1
        daily_video_index = video % videos_per_day
        hour = daily_times[daily_video_index]
        time_offset = timedelta(
            days=day, hours=hour - current_time.hour,
            minutes=-current_time.minute, seconds=-current_time.second,
            microseconds=-current_time.microsecond
        )
        timestamp = current_time + time_offset
        schedule.append(timestamp)
    if timestamps:
        import time
        schedule = [int(t.timestamp()) for t in schedule]
    return schedule
