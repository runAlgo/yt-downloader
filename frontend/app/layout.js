import "./globals.css";

export const metadata = {
  title: "YouTube Video & Audio Downloader - HD MP4 & MP3 Extractor",
  description: "Fast, high-quality YouTube video and audio downloader supporting HD MP4 downloads and crystal clear MP3 extraction.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
