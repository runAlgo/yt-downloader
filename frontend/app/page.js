"use client";

import { useState } from "react";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function handleDownload(e) {
    e.preventDefault();
    setMessage("");
    setError("");

    if (!url.trim()) {
      setError("Please paste a video URL.");
      return;
    }

    try {
      setLoading(true);

      const response = await fetch(`${API_URL}/api/download`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ url: url.trim() }),
      });

      if (!response.ok) {
        let detail = "Download failed.";
        try {
          const data = await response.json();
          detail = data.detail || detail;
        } catch {}
        throw new Error(detail);
      }

      const blob = await response.blob();
      const disposition = response.headers.get("content-disposition") || "";
      const match = disposition.match(/filename="?([^"]+)"?/i);
      const filename = match?.[1] || "video.mp4";

      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(blobUrl);

      setMessage("Download started.");
    } catch (err) {
      setError(err.message || "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page">
      <section className="card">
        <div className="badge">YT-DLP</div>
        <h1>Simple Video Downloader</h1>
        <p className="subtitle">
          Paste a supported video URL and download it using your backend.
        </p>

        <form onSubmit={handleDownload}>
          <input
            type="url"
            placeholder="https://youtu.be/..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={loading}
            required
          />

          <button type="submit" disabled={loading}>
            {loading ? "Downloading..." : "Download Video"}
          </button>
        </form>

        {message && <p className="success">{message}</p>}
        {error && <p className="error">{error}</p>}

        <p className="note">
          Only download content you have permission to download and use.
        </p>
      </section>
    </main>
  );
}
