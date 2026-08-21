import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask


app = FastAPI(title="YouTube Video & Audio Downloader API")


# ============================================================
# CORS
# ============================================================

FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "http://localhost:3000"
).rstrip("/")

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "https://frontend-gilt-beta-87.vercel.app",
]

if FRONTEND_URL and FRONTEND_URL not in ALLOWED_ORIGINS:
    ALLOWED_ORIGINS.append(FRONTEND_URL)


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


# ============================================================
# MODELS
# ============================================================

class InfoRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    quality: Optional[str] = "best"
    format_type: Optional[str] = "mp4"


# ============================================================
# HELPERS
# ============================================================

def safe_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()

    return name[:180] or "video"


def format_duration(seconds: Optional[int]) -> str:
    if not seconds:
        return "Unknown"

    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)

    if hours > 0:
        return f"{hours}:{mins:02d}:{secs:02d}"

    return f"{mins}:{secs:02d}"


def cleanup_temp_dir(dir_path: str):
    try:
        shutil.rmtree(dir_path, ignore_errors=True)
    except Exception:
        pass


def get_ffmpeg_path() -> Optional[str]:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()

    except Exception:
        return None


def get_base_ydl_opts() -> dict:

    ffmpeg_exe = get_ffmpeg_path()

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,

        "extractor_args": {
            "youtube": {
                # IMPORTANT: "android" must NOT come first.
                # The Android client only exposes formats up to
                # 1080p — it never returns the 1440p/2160p (4K)
                # adaptive streams at all, regardless of format
                # selector. "web" and "web_creator" are the clients
                # that actually expose high-res VP9/AV1 formats.
                "player_client": [
                    "web",
                    "web_creator",
                    "tv",
                    "android",
                ],
            }
        },

        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120.0.0.0 "
                "Safari/537.36"
            ),
        },
    }

    if ffmpeg_exe:
        opts["ffmpeg_location"] = ffmpeg_exe

    return opts


def build_video_format_selector(target_height: Optional[int] = None) -> str:
    """
    Build a yt-dlp format selector that strictly fetches maximum video quality:
      1. If target_height is None or >= 2160, uses unconstrained bestvideo+bestaudio/best for 4K/8K max quality.
      2. If target_height is specified (e.g. 1080, 720), tries exact height + bestaudio, falling back to <= target_height.
    """
    if not target_height or target_height >= 2160:
        return "bestvideo+bestaudio/best"

    return (
        f"bestvideo[height={target_height}]+bestaudio"
        f"/bestvideo[height<={target_height}]+bestaudio"
        f"/bestvideo+bestaudio"
        f"/best"
    )


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():
    return {
        "message": "YouTube Downloader API is running"
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }


# ============================================================
# VIDEO INFO
# ============================================================

@app.post("/api/info")
def get_video_info(payload: InfoRequest):

    url = payload.url.strip()

    if not url:
        raise HTTPException(
            status_code=400,
            detail="URL is required."
        )

    ydl_opts = get_base_ydl_opts()

    ydl_opts["skip_download"] = True

    try:

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(
                url,
                download=False
            )

            if info is None:
                raise HTTPException(
                    status_code=400,
                    detail="Could not extract video details."
                )

            title = info.get(
                "title",
                "Unknown Title"
            )

            uploader = (
                info.get("uploader")
                or info.get("channel")
                or "Unknown Uploader"
            )

            duration = info.get(
                "duration",
                0
            )

            duration_str = format_duration(
                duration
            )

            thumbnails = info.get(
                "thumbnails"
            ) or []

            thumbnail = (
                info.get("thumbnail")
                or (
                    thumbnails[-1].get("url")
                    if thumbnails
                    else ""
                )
            )

            view_count = info.get(
                "view_count",
                0
            )

            quality_options: List[Dict[str, Any]] = [
                {
                    "id": "best",
                    "label": "Max Quality 4K / Ultra HD (Auto)",
                    "badge": "🔥 MAX 4K/HD",
                    "type": "video",
                },
                {
                    "id": "1080",
                    "label": "1080p Full HD (60fps High Bitrate)",
                    "badge": "✨ 1080p FULL HD",
                    "type": "video",
                },
                {
                    "id": "720",
                    "label": "720p HD",
                    "badge": "🎬 720p HD",
                    "type": "video",
                },
                {
                    "id": "mp3_320",
                    "label": "MP3 Audio (320kbps Studio)",
                    "badge": "🎵 MP3 320k",
                    "type": "audio",
                },
                {
                    "id": "mp3_192",
                    "label": "MP3 Audio (192kbps Standard)",
                    "badge": "🎵 MP3 192k",
                    "type": "audio",
                },
            ]

            return {
                "title": title,
                "uploader": uploader,
                "duration": duration,
                "duration_str": duration_str,
                "thumbnail": thumbnail,
                "view_count": view_count,
                "quality_options": quality_options,
                "url": url,
            }

    except Exception as exc:

        raise HTTPException(
            status_code=400,
            detail=f"Failed to fetch video info: {str(exc)}"
        ) from exc


# ============================================================
# DOWNLOAD
# ============================================================

@app.post("/api/download")
def download_video(payload: DownloadRequest):

    url = payload.url.strip()

    if not url:
        raise HTTPException(
            status_code=400,
            detail="URL is required."
        )

    quality = (
        payload.quality
        or payload.format_type
        or "best"
    ).lower().replace("p", "")

    temp_dir = tempfile.mkdtemp(
        prefix="yt-download-"
    )

    output_template = str(
        Path(temp_dir) / "%(id)s.%(ext)s"
    )

    ydl_opts = get_base_ydl_opts()

    ydl_opts.update({
        "outtmpl": output_template,
    })

    # ========================================================
    # AUDIO
    # ========================================================

    is_audio = (
        "mp3" in quality
        or payload.format_type == "mp3"
    )

    if is_audio:

        bitrate = (
            "320"
            if "320" in quality
            else "192"
        )

        ydl_opts.update({

            "format": "bestaudio/best",

            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": bitrate,
                }
            ],
        })

    # ========================================================
    # MAXIMUM QUALITY VIDEO DOWNLOAD
    # ========================================================

    else:

        target_h = None
        if quality not in ["best", "auto", "max"]:
            try:
                target_h = int(quality)
            except ValueError:
                target_h = None

        ydl_opts.update({
            "format": build_video_format_selector(target_height=target_h),
            "merge_output_format": "mp4",
            "postprocessors": [
                {
                    "key": "FFmpegVideoRemuxer",
                    "preferedformat": "mp4",
                }
            ],
        })

    # ========================================================
    # DOWNLOAD
    # ========================================================

    try:

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

            if info is None:

                raise RuntimeError(
                    "Failed to extract video info."
                )

            raw_title = info.get(
                "title",
                "video"
            )

            clean_title = safe_filename(
                raw_title
            )

            # Find downloaded files
            files = [
                p
                for p in Path(temp_dir).glob("*")
                if (
                    p.is_file()
                    and not p.name.endswith(
                        (".part", ".ytdl")
                    )
                )
            ]

            if not files:

                raise RuntimeError(
                    "Downloaded file was not found."
                )

            # ------------------------------------------------
            # Select final file
            # ------------------------------------------------

            if is_audio:

                target_ext = ".mp3"

                matching_file = next(
                    (
                        f
                        for f in files
                        if f.suffix.lower()
                        == target_ext
                    ),
                    None
                )

                if matching_file is None:

                    raise RuntimeError(
                        "MP3 file was not created."
                    )

                actual_filename = (
                    f"{clean_title}.mp3"
                )

                media_type = "audio/mpeg"

            else:

                matching_file = next(
                    (
                        f
                        for f in files
                        if f.suffix.lower() == ".mp4"
                    ),
                    None
                )

                if matching_file is None:
                    matching_file = next(
                        (
                            f
                            for f in files
                            if f.suffix.lower() == ".mkv"
                        ),
                        None
                    )

                if matching_file is None:

                    raise RuntimeError(
                        "Video file was not created."
                    )

                out_ext = matching_file.suffix.lower()

                actual_filename = (
                    f"{clean_title}_1080p{out_ext}"
                )

                media_type = (
                    "video/mp4"
                    if out_ext == ".mp4"
                    else "video/x-matroska"
                )

            # ------------------------------------------------
            # Return file
            # ------------------------------------------------

            return FileResponse(

                path=str(matching_file),

                media_type=media_type,

                filename=actual_filename,

                background=BackgroundTask(
                    cleanup_temp_dir,
                    temp_dir
                ),
            )

    except Exception as exc:

        cleanup_temp_dir(
            temp_dir
        )

        raise HTTPException(
            status_code=400,
            detail=str(exc)
        ) from exc
