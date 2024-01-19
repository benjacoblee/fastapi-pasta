import os
import asyncio
import subprocess
from fastapi import BackgroundTasks
from sqlalchemy.orm import Session
from models.db import VideoItem


async def async_compress_video(orig_file_path: str, new_file_path: str, db: Session):
    try:
        await asyncio.to_thread(
            subprocess.run,
            f"ffmpeg -i {orig_file_path} -c:v libx264 -crf 30 {new_file_path} -progress - -nostats",
            shell=True,
            check=True,
        )
        os.remove(orig_file_path)
        video_item = (
            db.query(VideoItem).filter(VideoItem.filename == new_file_path).first()
        )
        if video_item:
            video_item.completed = True
            db.commit()
    except subprocess.CalledProcessError as e:
        video_item = (
            db.query(VideoItem).filter(VideoItem.filename == new_file_path).first()
        )
        if video_item:
            video_item.failed = True
            db.commit()


def add_compress_task(
    orig_file_path: str, new_file_path: str, bg_tasks: BackgroundTasks, db: Session
):
    bg_tasks.add_task(async_compress_video, orig_file_path, new_file_path, db)
