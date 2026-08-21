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

    # Optional cookies support. On Render, set an env var
    # YOUTUBE_COOKIES containing the full contents of a
    # Netscape-format cookies.txt file (exported from a real
    # logged-in browser session — see the docstring below for
    # how to export one). We write it to a temp file at request
    # time so it works on Render's ephemeral filesystem.
    cookies_content = os.getenv("YOUTUBE_COOKIES")
    cookiefile_path = None

    if cookies_content:
        cookie_fd, cookiefile_path = tempfile.mkstemp(
            prefix="yt-cookies-", suffix=".txt"
        )
        with os.fdopen(cookie_fd, "w") as f:
            f.write(cookies_content)

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,

        "extractor_args": {
            "youtube": {
                # As of mid-2026, YouTube's bot check is largely
                # tied to *which client* yt-dlp claims to be, not
                # just whether cookies are present. "tv" and
                # "web_safari" currently pass the proof-of-origin
                # check without needing an account at all. Keep
                # "web"/"web_creator" after them since they expose
                # the 1440p/4K formats when they do work, and
                # "android" last as a final fallback (1080p cap,
                # but sometimes least likely to be challenged).
                "player_client": [
                    "tv",
                    "web_safari",
                    "web",
                    "web_creator",
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

    if cookiefile_path:
        opts["cookiefile"] = cookiefile_path

    return opts


def build_video_format_selector(target_height: Optional[int] = None) -> str:
    """
    Build a yt-dlp format selector that:
      1. Prefers native H.264 (avc1) MP4 at the requested height, for
         maximum compatibility.
      2. Falls back to VP9/AV1 (the codecs YouTube actually uses for
         1440p/2K and 2160p/4K — H.264 rarely exists at those heights).
      3. Falls back to whatever the single best pre-muxed stream is.

    yt-dlp evaluates selectors left-to-right and uses the first one
    that actually has matching formats available, so listing avc1
    first still gives you H.264 whenever it exists at that height.
    """

    height_filter = f"[height<={target_height}]" if target_height else ""

    return (
        # 1) H.264/AVC1 video + M4A audio (best compatibility)
        f"bestvideo{height_filter}[vcodec^=avc1]+bestaudio[ext=m4a]"
        # 2) VP9 or AV1 video (needed for 1440p/4K) + M4A audio
        f"/bestvideo{height_filter}[vcodec^=vp9]+bestaudio[ext=m4a]"
        f"/bestvideo{height_filter}[vcodec^=av01]+bestaudio[ext=m4a]"
        # 3) Same codecs, but don't require m4a — 4K streams are
        #    sometimes only paired with opus/webm audio
        f"/bestvideo{height_filter}[vcodec^=vp9]+bestaudio"
        f"/bestvideo{height_filter}[vcodec^=av01]+bestaudio"
        # 4) Any codec, any container, just respect the height cap
        f"/bestvideo{height_filter}+bestaudio"
        # 5) Last resort: best combined/pre-muxed stream
        f"/best{height_filter}"
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

            # ------------------------------------------------
            # Find real resolutions across ANY codec
            # (H.264, VP9, AV1) so 1440p/4K actually show up —
            # those are almost never available in H.264.
            # ------------------------------------------------

            formats = info.get(
                "formats"
            ) or []

            heights = set()

            for f in formats:

                height = f.get("height")

                codec = (
                    f.get("vcodec")
                    or ""
                )

                # Skip audio-only / storyboard entries
                if not height or not isinstance(height, int):
                    continue

                if codec in ("none", ""):
                    continue

                # Accept H.264, VP9, and AV1 video streams
                if (
                    codec.startswith("avc1")
                    or codec.startswith("vp9")
                    or codec.startswith("av01")
                ):
                    heights.add(height)

            # Only show these common HD-and-above options
            supported_heights = [
                h
                for h in heights
                if h >= 720
            ]

            supported_heights = sorted(
                supported_heights,
                reverse=True
            )

            quality_options: List[
                Dict[str, Any]
            ] = []

            # Best option
            if supported_heights:
                quality_options.append({
                    "id": "best",
                    "label": "Best Available Quality",
                    "badge": "⭐ BEST",
                    "type": "video",
                })

            # Specific resolutions
            for h in supported_heights:

                if h >= 2160:
                    label = f"{h}p 4K"
                    badge = f"🔥 {h}p 4K"

                elif h >= 1440:
                    label = f"{h}p 2K"
                    badge = f"🔥 {h}p 2K"

                elif h >= 1080:
                    label = f"{h}p Full HD"
                    badge = "✨ 1080p FULL HD"

                else:
                    label = f"{h}p HD"
                    badge = "🎬 720p HD"

                quality_options.append({
                    "id": str(h),
                    "label": label,
                    "badge": badge,
                    "type": "video",
                })

            # Audio
            quality_options.append({
                "id": "mp3_320",
                "label": "MP3 Audio (320kbps)",
                "badge": "🎵 MP3 320k",
                "type": "audio",
            })

            quality_options.append({
                "id": "mp3_192",
                "label": "MP3 Audio (192kbps)",
                "badge": "🎵 MP3 192k",
                "type": "audio",
            })

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
    # BEST QUALITY (no cap — allows 4K/8K if available)
    # ========================================================

    elif quality == "best":

        ydl_opts.update({

            # Try H.264 first for compatibility, then fall back
            # to VP9/AV1 so 1440p/4K actually download instead of
            # silently capping at 1080p.
            "format": build_video_format_selector(target_height=None),

            "merge_output_format": "mp4",

            # NOTE: no forced FFmpegVideoRemuxer here — when the
            # source is VP9/AV1, yt-dlp's merger already produces
            # an mp4 container via merge_output_format above.
            # Forcing a remux post-processor on top can fail/strip
            # streams when the codec isn't H.264.
        })

    # ========================================================
    # SPECIFIC QUALITY (720/1080/1440/2160 etc.)
    # ========================================================

    else:

        try:
            target_height = int(quality)

        except ValueError:

            cleanup_temp_dir(temp_dir)

            raise HTTPException(
                status_code=400,
                detail="Invalid video quality."
            )

        ydl_opts.update({

            "format": build_video_format_selector(
                target_height=target_height
            ),

            "merge_output_format": "mp4",
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

                # Accept mp4, and mkv as a fallback (yt-dlp will
                # produce mkv if merge_output_format=mp4 can't
                # safely contain the chosen codec combo).
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

                if quality in [
                    "1080",
                    "720",
                    "1440",
                    "2160",
                ]:

                    actual_filename = (
                        f"{clean_title}_{quality}p{out_ext}"
                    )

                else:

                    actual_filename = (
                        f"{clean_title}{out_ext}"
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