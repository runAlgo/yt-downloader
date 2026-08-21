import "./globals.css";

export const metadata = {
  title: "Simple Video Downloader",
  description: "Download videos through your own yt-dlp backend",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
