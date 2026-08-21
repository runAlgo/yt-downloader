"use client";

import { useState, useEffect } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const DEFAULT_VIDEO_QUALITIES = [
  { id: "best", label: "Max Quality 4K / Ultra HD", badge: "🔥 MAX 4K/HD", type: "video" },
  { id: "1080", label: "1080p Full HD (60fps)", badge: "✨ 1080p FULL HD", type: "video" },
  { id: "720", label: "720p HD", badge: "🎬 720p HD", type: "video" },
];

const DEFAULT_AUDIO_QUALITIES = [
  { id: "mp3_320", label: "MP3 Studio (320kbps)", badge: "🎵 MP3 320k HD", type: "audio" },
  { id: "mp3_192", label: "MP3 Standard (192kbps)", badge: "🎧 MP3 192k", type: "audio" },
];

// Translate raw backend/yt-dlp error text into something a user can
// actually act on, instead of showing internal tool output.
function friendlyErrorMessage(rawDetail) {
  const text = (rawDetail || "").toLowerCase();

  if (text.includes("sign in to confirm") || text.includes("not a bot")) {
    return "This video is temporarily unavailable for download — please try again in a few minutes.";
  }
  if (text.includes("private video") || text.includes("this video is private")) {
    return "This video is private and can't be downloaded.";
  }
  if (text.includes("video unavailable") || text.includes("removed")) {
    return "This video is unavailable — it may have been removed or region-restricted.";
  }
  if (text.includes("could not extract") || text.includes("unsupported url")) {
    return "That doesn't look like a valid YouTube link — please check the URL and try again.";
  }

  return rawDetail || "Something went wrong. Please try again.";
}

export default function Home() {
  const [activeTab, setActiveTab] = useState("video"); // "video" or "mp3"
  const [url, setUrl] = useState("");
  const [selectedQuality, setSelectedQuality] = useState("best");
  const [selectedAudioQuality, setSelectedAudioQuality] = useState("mp3_320");
  const [loadingInfo, setLoadingInfo] = useState(false);
  const [loadingDownload, setLoadingDownload] = useState(false);
  const [downloadStep, setDownloadStep] = useState("");
  const [videoInfo, setVideoInfo] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  // Update selected quality default when tab changes
  useEffect(() => {
    if (activeTab === "mp3") {
      setSelectedQuality(selectedAudioQuality);
    } else {
      setSelectedQuality("best");
    }
  }, [activeTab]);

  useEffect(() => {
    if (!url.trim()) {
      setVideoInfo(null);
      setError("");
      setMessage("");
      setDownloadStep("");
    }
  }, [url]);

  async function handleFetchInfo(e) {
    if (e) e.preventDefault();
    if (!url.trim()) {
      setError("Please paste a valid YouTube video or audio link.");
      return;
    }

    setError("");
    setMessage("");
    setLoadingInfo(true);
    setVideoInfo(null);

    try {
      const response = await fetch(`${API_URL}/api/info`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim() }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(friendlyErrorMessage(data.detail || "Failed to fetch media details."));
      }

      setVideoInfo(data);
      if (activeTab === "mp3") {
        const mp3Opt = (data.quality_options || []).find((q) => q.type === "audio") || DEFAULT_AUDIO_QUALITIES[0];
        setSelectedQuality(mp3Opt.id);
      } else {
        setSelectedQuality("best");
      }
    } catch (err) {
      setError(err.message || "Could not fetch video info. Check the URL and try again.");
    } finally {
      setLoadingInfo(false);
    }
  }

  async function handleDownload(e, customQuality = null) {
    if (e) e.preventDefault();
    if (!url.trim()) {
      setError("Please paste a video or audio URL.");
      return;
    }

    setError("");
    setMessage("");
    setLoadingDownload(true);

    const targetQuality = customQuality || (activeTab === "mp3" ? selectedAudioQuality : selectedQuality);
    const isMp3 = activeTab === "mp3" || targetQuality.startsWith("mp3");

    let qualityLabel = targetQuality === "best" ? "Max Quality 4K / Ultra HD" : `${targetQuality}p HD`;
    if (isMp3) {
      qualityLabel = targetQuality.includes("320") ? "320kbps MP3 Audio" : "192kbps MP3 Audio";
    }

    setDownloadStep(`Extracting ${isMp3 ? "MP3 Audio" : "Maximum Ultra HD Video"} stream...`);

    try {
      const formatType = isMp3 ? "mp3" : "mp4";

      const response = await fetch(`${API_URL}/api/download`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: url.trim(),
          quality: targetQuality,
          format_type: formatType,
        }),
      });

      if (!response.ok) {
        let detail = "Download failed.";
        try {
          const data = await response.json();
          detail = data.detail || detail;
        } catch {}
        throw new Error(friendlyErrorMessage(detail));
      }

      setDownloadStep(isMp3 ? "Converting audio to 320kbps MP3..." : "Merging unconstrained ultra high bitrate video & audio...");

      const blob = await response.blob();

      // Backend picks the real container based on the source codec:
      // most videos come back as .mp4, but 4K/2K sources that yt-dlp
      // can't losslessly remux into mp4 come back as .mkv instead.
      // Content-Disposition (when present) already has the correct
      // extension — only fall back to guessing from the blob's mime
      // type if that header is ever missing.
      const disposition = response.headers.get("content-disposition") || "";
      let filename = null;
      const match = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)["']?/i);
      if (match && match[1]) {
        filename = decodeURIComponent(match[1]);
      } else {
        const simpleMatch = disposition.match(/filename="?([^"]+)"?/i);
        if (simpleMatch && simpleMatch[1]) {
          filename = simpleMatch[1];
        }
      }

      if (!filename) {
        const guessedExt = isMp3
          ? "mp3"
          : blob.type === "video/x-matroska"
          ? "mkv"
          : "mp4";
        const baseName = (videoInfo && videoInfo.title) || "media";
        filename = `${baseName}.${guessedExt}`;
      }

      setDownloadStep("Finalizing download & saving file...");
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(blobUrl);

      setMessage(`Successfully downloaded (${qualityLabel}): ${filename}`);
    } catch (err) {
      setError(err.message || "Failed to download media. Please try again.");
    } finally {
      setLoadingDownload(false);
      setDownloadStep("");
    }
  }

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        setUrl(text);
      }
    } catch (err) {
      console.error("Clipboard permission denied", err);
    }
  };

  const videoQualities = (videoInfo?.quality_options || []).filter((q) => q.type === "video");
  const audioQualities = (videoInfo?.quality_options || []).filter((q) => q.type === "audio");

  const displayVideoQualities = videoQualities.length > 0 ? videoQualities : DEFAULT_VIDEO_QUALITIES;
  const displayAudioQualities = audioQualities.length > 0 ? audioQualities : DEFAULT_AUDIO_QUALITIES;

  return (
    <div className="page-wrapper">
      {/* Dynamic Background Glows */}
      <div className={`ambient-glow-1 ${activeTab === "mp3" ? "glow-mp3" : ""}`}></div>
      <div className={`ambient-glow-2 ${activeTab === "mp3" ? "glow-mp3-secondary" : ""}`}></div>

      <main className="main-container">
        {/* Header Section */}
        <header className="header">
          <div className="brand-badge">
            <svg className="brand-icon" viewBox="0 0 24 24">
              <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
            </svg>
            Ultra HD 4K & MP3 Downloader
          </div>

          <h1 className="title">
            {activeTab === "mp3" ? (
              <>URL to <span className="gradient-text-audio">MP3 Converter</span></>
            ) : (
              <>Download <span className="gradient-text-video">Max Quality 4K & HD</span> Videos</>
            )}
          </h1>
          <p className="subtitle">
            {activeTab === "mp3"
              ? "Convert YouTube video links directly into 320kbps MP3 audio files."
              : "Download unconstrained maximum quality 4K, 2K, and 1080p60 videos with highest bitrate audio."}
          </p>

          {/* Mode Switcher Tabs */}
          <div className="tab-container">
            <button
              type="button"
              className={`mode-tab ${activeTab === "video" ? "active" : ""}`}
              onClick={() => setActiveTab("video")}
            >
              <span className="tab-icon">🎬</span>
              <span>Ultra HD 4K Video</span>
            </button>
            <button
              type="button"
              className={`mode-tab ${activeTab === "mp3" ? "active active-mp3" : ""}`}
              onClick={() => setActiveTab("mp3")}
            >
              <span className="tab-icon">🎵</span>
              <span>URL to MP3</span>
            </button>
          </div>
        </header>

        {/* Main Downloader Card */}
        <section className={`glass-card ${activeTab === "mp3" ? "card-mp3-theme" : ""}`}>
          <form onSubmit={videoInfo ? (e) => handleDownload(e) : handleFetchInfo}>
            <div className="input-group">
              <div className="url-input-wrapper">
                <span className="input-icon">
                  {activeTab === "mp3" ? (
                    <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 .895-2 3-2 3 .895 3 2zm12 0c0 1.105-1.343 2-3 2s-3-.895-3-2 .895-2 3-2 3 .895 3 2zM9 10l12-3" />
                    </svg>
                  ) : (
                    <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                    </svg>
                  )}
                </span>
                <input
                  type="url"
                  className="url-input"
                  placeholder={
                    activeTab === "mp3"
                      ? "Paste link to convert to MP3..."
                      : "Paste video link (e.g. https://www.youtube.com/watch?v=...)"
                  }
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  disabled={loadingInfo || loadingDownload}
                  required
                />
                {url ? (
                  <button
                    type="button"
                    className="clear-btn"
                    onClick={() => setUrl("")}
                    title="Clear input"
                  >
                    ✕
                  </button>
                ) : (
                  <button
                    type="button"
                    className="paste-btn"
                    onClick={handlePaste}
                    title="Paste from clipboard"
                  >
                    <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                    </svg>
                    PASTE
                  </button>
                )}
              </div>
            </div>

            {/* Quick Action Controls before video info fetch */}
            {!videoInfo && (
              <div className="action-row">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={handleFetchInfo}
                  disabled={loadingInfo || loadingDownload || !url.trim()}
                >
                  {loadingInfo ? (
                    <>
                      <div className="spinner"></div> Fetching Info...
                    </>
                  ) : (
                    "Preview Video"
                  )}
                </button>

                <button
                  type="submit"
                  className={`btn ${activeTab === "mp3" ? "btn-mp3-primary" : "btn-primary"}`}
                  disabled={loadingInfo || loadingDownload || !url.trim()}
                >
                  {loadingDownload ? (
                    <>
                      <div className="spinner"></div> Downloading...
                    </>
                  ) : activeTab === "mp3" ? (
                    `Convert & Download MP3`
                  ) : (
                    `Download Max Quality 4K / HD Video`
                  )}
                </button>
              </div>
            )}

            {/* Video / Audio Preview Card */}
            {videoInfo && (
              <div className="preview-card">
                <div className="video-meta">
                  <div className="thumbnail-wrapper">
                    {videoInfo.thumbnail ? (
                      <img
                        src={videoInfo.thumbnail}
                        alt={videoInfo.title}
                        className="thumbnail-img"
                      />
                    ) : (
                      <div className="no-thumbnail">No Thumbnail</div>
                    )}
                    {videoInfo.duration_str && (
                      <span className="duration-tag">{videoInfo.duration_str}</span>
                    )}
                    {activeTab === "mp3" && (
                      <div className="mp3-overlay-badge">
                        <span>🎵 MP3 Mode</span>
                      </div>
                    )}
                  </div>
                  <div className="meta-details">
                    <h3 className="video-title">{videoInfo.title}</h3>
                    <p className="video-uploader">
                      <span>👤 {videoInfo.uploader}</span>
                    </p>
                    {videoInfo.view_count > 0 && (
                      <span className="view-count">
                        👁️ {videoInfo.view_count.toLocaleString()} views
                      </span>
                    )}
                  </div>
                </div>

                {/* Quality Selection Section */}
                <div className="quality-section">
                  <div className="quality-header-row">
                    <label className="quality-label">
                      {activeTab === "mp3" ? "Select MP3 Quality:" : "Select Video Quality:"}
                    </label>
                  </div>

                  {activeTab === "video" ? (
                    <div className="quality-grid">
                      {displayVideoQualities.map((q) => {
                        const isSelected = selectedQuality === q.id;
                        const isBest = q.id === "best";
                        return (
                          <button
                            key={q.id}
                            type="button"
                            className={`quality-pill ${isSelected ? (isBest ? "active pill-4k" : "active pill-1080p") : ""}`}
                            onClick={() => setSelectedQuality(q.id)}
                          >
                            <span className="pill-badge">{q.badge || q.label}</span>
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="quality-grid">
                      {displayAudioQualities.map((q) => {
                        const isSelected = selectedAudioQuality === q.id || selectedQuality === q.id;
                        return (
                          <button
                            key={q.id}
                            type="button"
                            className={`quality-pill pill-mp3 ${isSelected ? "active-mp3" : ""}`}
                            onClick={() => {
                              setSelectedAudioQuality(q.id);
                              setSelectedQuality(q.id);
                            }}
                          >
                            <span className="pill-badge">{q.badge || q.label}</span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Live Download Progress Indicator */}
                {downloadStep && (
                  <div className={`download-step-bar ${activeTab === "mp3" ? "step-bar-mp3" : ""}`}>
                    <div className="spinner"></div>
                    <span>{downloadStep}</span>
                  </div>
                )}

                {/* Main Download Button */}
                <div className="action-row">
                  <button
                    type="button"
                    className={`btn btn-large-download ${activeTab === "mp3" ? "btn-mp3-primary" : "btn-primary"}`}
                    onClick={(e) => handleDownload(e)}
                    disabled={loadingDownload}
                  >
                    {loadingDownload ? (
                      <>
                        <div className="spinner"></div> Processing & Downloading...
                      </>
                    ) : activeTab === "mp3" ? (
                      `⬇️ Download MP3 Audio (${selectedAudioQuality.includes("320") ? "320kbps HD" : "192kbps"})`
                    ) : (
                      `⬇️ Download Video (${selectedQuality === "best" ? "Max Quality 4K / Ultra HD" : selectedQuality + "p HD"})`
                    )}
                  </button>
                </div>
              </div>
            )}
          </form>

          {/* Success Notification Alert */}
          {message && (
            <div className="alert alert-success">
              <span className="alert-icon">✅</span>
              <div>{message}</div>
            </div>
          )}

          {/* Error Notification Alert */}
          {error && (
            <div className="alert alert-error">
              <span className="alert-icon">⚠️</span>
              <div>{error}</div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
