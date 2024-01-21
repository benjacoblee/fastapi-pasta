import os
import asyncio
import subprocess
from fastapi import BackgroundTasks
from sqlalchemy.orm import Session
from models.base import Job
from models.db import VideoItem


async def async_compress_video(
    orig_file_path: str,
    new_file_path: str,
    jobs: list[Job],
    db: Session,
):
    try:
        await asyncio.to_thread(
            subprocess.run,
            f"ffmpeg -i {orig_file_path} -c:v libx264 -crf 30 {new_file_path}",
            shell=True,
            check=True,
        )
        os.remove(orig_file_path)
        video_item = (
            db.query(VideoItem).filter(VideoItem.filename == new_file_path).first()
        )
        assert video_item is not None
        job_item = next(
            iter([job for job in jobs if job.video_id == video_item.id]), None
        )
        assert job_item is not None
        job_item.completed = True
    except subprocess.CalledProcessError as e:
        print(e)


def add_compress_task(
    orig_file_path: str,
    new_file_path: str,
    bg_tasks: BackgroundTasks,
    jobs: list[Job],
    db: Session,
):
    bg_tasks.add_task(async_compress_video, orig_file_path, new_file_path, jobs, db)
