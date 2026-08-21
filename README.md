# Simple Full-Stack Video Downloader

A minimal full-stack app using:

- Frontend: Next.js
- Backend: FastAPI
- Downloader: yt-dlp
- FFmpeg: imageio-ffmpeg
- Frontend deployment: Vercel
- Backend deployment: Render

## Project structure

```text
yt-downloader-fullstack/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── render.yaml
│   └── .gitignore
├── frontend/
│   ├── app/
│   │   ├── page.js
│   │   ├── layout.js
│   │   └── globals.css
│   ├── package.json
│   ├── next.config.mjs
│   └── .env.example
└── README.md
```

## Run backend locally

```bash
cd backend
C:\Python314\python.exe -m pip install -r requirements.txt
C:\Python314\python.exe -m uvicorn main:app --reload --port 8000 or 
python -m uvicorn main:app --reload --port 8000
```

Backend:
http://localhost:8000

Health:
http://localhost:8000/health

## Run frontend locally

```bash
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

Frontend:
http://localhost:3000

## Deploy backend to Render

Create a GitHub repository and push this project.

In Render, create a Web Service pointing to the repository.

Root Directory:
```text
backend
```

Build Command:
```text
pip install -r requirements.txt
```

Start Command:
```text
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Add Environment Variables in Render Dashboard:

```text
FRONTEND_URL=https://YOUR-VERCEL-DOMAIN.vercel.app
```

*(Optional - if YouTube blocks datacenter IPs)*: Export YouTube cookies from your browser (using an extension like "Get cookies.txt LOCALLY") and paste the cookie content into a Render environment variable:
```text
YOUTUBE_COOKIES=<paste-cookie-content-or-base64>
```

## Deploy frontend to Vercel

Import the same GitHub repository into Vercel.

Set Root Directory to:

```text
frontend
```

Add:

```text
NEXT_PUBLIC_API_URL=https://YOUR-RENDER-SERVICE.onrender.com
```

Then deploy.

## Important production limitation

This simple version downloads the whole video on the Render server and then sends it to the browser. Render instances have resource, timeout, and ephemeral-storage constraints, so this is suitable for a simple/demo app rather than a large-scale downloader.

For a production version, use a background job/queue and object storage (such as S3-compatible storage), then return a temporary download URL.

Use the application only for content you are authorized to download.
