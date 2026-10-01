# Linkdrop

Next.js frontend and API routes, with a separate Python/yt-dlp worker for video extraction and downloads. The frontend can deploy to Vercel; deploy the Docker worker to a host that supports long requests and FFmpeg (for example a container server).

## Run locally

1. Install Node.js 20.9+ and Python 3.12+, FFmpeg, and a current JavaScript runtime supported by yt-dlp.
2. `npm install`, then copy `.env.example` to `.env.local`. Set `VIDEO_WORKER_SECRET` to a random secret of at least 24 characters (e.g. `openssl rand -hex 32`).
3. In a second terminal, create a virtual environment, install `worker/requirements.txt`, and export the **same** `VIDEO_WORKER_SECRET`.
4. Start the worker: `uvicorn main:app --app-dir worker --port 8000`.
5. Run `npm run dev` and open http://localhost:3000.

## Deploy

1. Deploy `worker/` using its Dockerfile. Set `VIDEO_WORKER_SECRET` and `WORKER_PUBLIC_URL` (the worker's public HTTPS origin). The download URL must be reachable by visitors. Configure its reverse proxy for downloads that can take up to 10 minutes. Mount enough temporary disk and enforce disk/network quotas.
2. Import this repository into Vercel. Set `VIDEO_WORKER_URL` to the worker's HTTPS origin and `VIDEO_WORKER_SECRET` to the shared secret. Deploy using the Next.js preset. These are server-only variables; do not prefix them with NEXT_PUBLIC.
3. Before opening it to unrestricted public traffic, configure a durable edge rate limit/bot challenge on `/api/analyze` and `/api/download`, plus the worker's `/file/*` endpoint. The worker limits simultaneous operations to two per process; signed download links expire in 15 minutes but can be reused during that period. Multiple processes increase concurrency.
4. Restrict worker network egress to public internet destinations, blocking private, loopback, link-local, and cloud metadata addresses. Input domains are allowlisted, but extractor redirects and media URLs still require network-level egress protection.

Vercel handles only metadata and signed links. The worker sends video files directly to visitors, avoiding Vercel function payload limits. No video bytes pass through Vercel.

## Behavior and limits

- Public YouTube, Instagram, X/Twitter, and Facebook video URLs use yt-dlp. Site support is best effort: public visibility does not guarantee extraction. Platforms may block datacenter IPs, require authentication, or change their APIs. No private content, user login cookies, or DRM bypass is implemented.
- Pictory preview links display the original embedded preview. The supplied example is a scene-based project, not a finished MP4. Export in Pictory to obtain the original complete MP4. The page also offers Record preview: open the preview tab, share that tab with audio, play it, and stop to save a local WebM/MP4 recording. This captures visible playback, not the original file; quality depends on the display and browser. Chrome/Edge desktop with tab audio are recommended. Recordings are capped at 30 minutes / approximately 400 MB, and refresh cancels unsaved recordings. Stock clips inside a project are never presented as the finished download. Embedding may be refused by the source's frame policy.
- Resolution options come from actual source formats. Original means best available source quality, not upscaling. FFmpeg merges separate audio/video streams without re-encoding. Container can be WebM/MKV when codecs require it.
- Videos must be finished and under 30 minutes; downloaded files are limited to 500 MB. FFmpeg temporary inputs may occupy additional space, so enforce host disk quotas. An unavailable browser-compatible preview does not prevent download.
- Form input and results live only in React memory. Refresh and history restoration clear them. The app creates no cookies, localStorage, sessionStorage, or saved history. It cannot reset source-platform cookies or erase server/provider access logs. Previously issued download links remain valid until expiry.
- Temporary files are deleted after serving or failure. Abrupt container termination can leave files behind; configure host cleanup for stale `linkdrop-*` directories.
- Downloads start via the browser after preparation. A download-time source failure appears in the worker response, rather than in the page. Large downloads take time and consume worker bandwidth.

## Checks

`npm run typecheck` and `npm run build`. Python syntax: `python3 -m py_compile worker/main.py`.

## Reconstructed MP4 for the supplied Pictory preview

`worker/render_preview.py` assembles the public preview media from the supplied project into a new 1280×720 MP4, with its voiceover and background music. It preserves source watermarks. The title overlay is static and uses a substitute font; Pictory's motion effects are not reproduced. The output resolution does not increase the native detail of lower-resolution preview clips. This is a reconstruction, not an official Pictory export.

The local worker exposes the completed `output/pictory-preview-reconstructed-720p.mp4` through the normal analyze/download flow for preview ID `202610010546486168eaab2eba77e41e6b46c45c8fb2f9abd`. Other Pictory links still show the recording/export options. For deployment, place this MP4 on persistent worker storage and set `PICTORY_RECONSTRUCTED_FILE` to its absolute path. The Docker image does not include local output files.

To reproduce locally on macOS: install Pillow in the worker environment, obtain the public preview's matching `previewJson` data, save only its `output`, `elements`, and `sceneDurations` (no storage token is needed), then run:

```
worker/.venv/bin/python worker/render_preview.py output/pictory-render/project.json output/pictory-render
```

The renderer is for this project's specific scene types and continuous voiceover timeline. It validates media hosts and never accesses private storage APIs. It uses the macOS Helvetica font; porting it to Linux requires choosing an installed font path.
