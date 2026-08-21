import os
import re
import tempfile
from pathlib import Path

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl

app = FastAPI(title="Simple YouTube Downloader API")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DownloadRequest(BaseModel):
    url: HttpUrl


def safe_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return name[:180].strip() or "video"


@app.get("/")
def root():
    return {"message": "YouTube Downloader API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/download")
def download_video(payload: DownloadRequest):
    url = str(payload.url)
    temp_dir = tempfile.mkdtemp(prefix="yt-download-")

    output_template = str(Path(temp_dir) / "%(title)s.%(ext)s")

    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "noplaylist": True,
        "outtmpl": output_template,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }

    # imageio-ffmpeg supplies FFmpeg locally and on Render/Linux.
    try:
        import imageio_ffmpeg
        ydl_opts["ffmpeg_location"] = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            requested = ydl.prepare_filename(info)

            candidates = [
                Path(requested),
                Path(requested).with_suffix(".mp4"),
                Path(requested).with_suffix(".mkv"),
                Path(requested).with_suffix(".webm"),
            ]

            output_file = next((p for p in candidates if p.exists()), None)

            if output_file is None:
                files = list(Path(temp_dir).glob("*"))
                output_file = next((p for p in files if p.is_file()), None)

            if output_file is None:
                raise RuntimeError("Downloaded file was not found.")

            filename = safe_filename(info.get("title", "video"))
            suffix = output_file.suffix or ".mp4"

            return FileResponse(
                path=str(output_file),
                media_type="video/mp4" if suffix == ".mp4" else "application/octet-stream",
                filename=f"{filename}{suffix}",
                background=None,
            )

    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
