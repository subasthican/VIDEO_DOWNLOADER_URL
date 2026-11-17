# Linkdrop

Next.js frontend and API routes, with a separate Python/yt-dlp worker for video extraction and downloads. The frontend can deploy to Vercel; the Docker worker needs a container runtime with FFmpeg and sufficient request time and temporary disk. Vercel also offers a [Container Runtime beta](https://vercel.com/docs/functions/runtimes/container), subject to its function limits.

## Run locally

1. Install Node.js 20.9+ and Python 3.12+, FFmpeg, and a current JavaScript runtime supported by yt-dlp.
2. `npm install`, then copy `.env.example` to `.env.local`. Set `VIDEO_WORKER_SECRET` to a random secret of at least 24 characters (e.g. `openssl rand -hex 32`).
3. In a second terminal, create the worker environment with `python3 -m venv worker/.venv`, then install dependencies with `worker/.venv/bin/python -m pip install -r worker/requirements.txt`.
4. Start the worker: `npm run worker`. This loads `.env.local` (including the shared secret and limits) and puts the worker environment's yt-dlp on PATH. Keep this terminal running alongside Next.js; restart it after changing worker code or configuration.
5. Run `npm run dev` and open http://localhost:3000.

The example local configuration supports finished videos of 9 hours or longer:

```dotenv
VIDEO_MAX_DURATION_SECONDS=0
VIDEO_MAX_FILESIZE_MB=0
VIDEO_DOWNLOAD_TIMEOUT_SECONDS=86400
```

`0` disables the duration or file-size limit; the timeout allows up to 24 hours for preparation, including queue time. Keep the worker running and the computer awake until the download finishes. Large videos need enough temporary disk space for separate video/audio streams and the merged result. The browser receives the file after downloading and merging on the worker, so preparation can take a long time. Lower source resolutions usually need less disk space and time. Live and upcoming streams are still rejected. Source-platform restrictions can still prevent extraction.

These settings apply to the local worker started with `npm run worker`. When running uvicorn directly, export the settings to that process yourself. Without overrides the worker retains limits of 30 minutes, 500 MB, and 240 seconds. Hosted function duration and disk limits still apply even if these application limits are disabled; long downloads need a worker host that permits long requests and sufficient disk space.

## Deploy to Vercel from `./`

The root `vercel.json` deploys the website and Docker downloader **together in one Vercel project**, on one domain. Keep the source folders as they are; Vercel builds the Next.js `app` service at the repository root and the Python `worker` service from `worker/Dockerfile`. The worker uses Vercel's [Container Runtime beta](https://vercel.com/docs/functions/runtimes/container).

1. Commit and push the project, then import `subasthican/VIDEO_DOWNLOADER_URL` in [Vercel](https://vercel.com/new), or redeploy the existing project.
2. Set **Root Directory** to `./` and use the **Services** application preset. Both `app` and `worker` belong to this single project. Leave dashboard build/install/output overrides unset; each service is configured in `vercel.json`.
3. Generate a secret with `openssl rand -hex 32` and save it in the project's environment variables as **`VIDEO_WORKER_SECRET`**. Enable it for Production and any Preview environments you use. Keep the value private. It must be at least 24 characters and must stay the same across worker instances.
4. Deploy or redeploy. Vercel automatically injects `VIDEO_WORKER_INTERNAL_URL` into the website using the service binding. You do **not** need to set `VIDEO_WORKER_URL`, `VIDEO_WORKER_INTERNAL_URL`, or `WORKER_PUBLIC_URL` for this setup; remove old URL overrides if present.
5. Check `https://your-project.vercel.app/health` for `{"ok":true}`, then analyze and download a short public video from the website.

The public `/api/analyze` and `/api/download` routes run in Next.js and call the worker privately. Signed `/file/*` download links and `/preview/*` media are routed directly to the worker on the same domain. The worker's raw `/analyze` and `/download` POST endpoints are not publicly routed. `.vercelignore` includes worker source and Docker configuration while excluding local secrets, Python environments, caches, and generated videos.

Worker preparation (including waiting for a free slot) times out after 240 seconds by default, leaving part of Vercel's default 300-second request budget for file transfer. The entire file response still has to finish within the project's configured function duration; long preparation or slow transfers can time out. On a plan with a longer duration, configure the worker's function duration in Vercel and optionally raise `VIDEO_DOWNLOAD_TIMEOUT_SECONDS` while leaving time for the transfer. Platform extraction can still fail when a video provider blocks datacenter IPs or restricts the video.

Before unrestricted public traffic, configure an edge rate limit/bot challenge for `/api/analyze`, `/api/download`, and `/file/*`, and enforce temporary disk/network quotas. The worker limits concurrent operations to two per instance; signed links expire in 15 minutes and can be reused before expiry. Restrict worker network egress to public destinations, including blocking private, loopback, link-local, and cloud metadata addresses, because extractor redirects and media URLs also need protection.

### Local development or a separate worker host

For local development, use `.env.example`: the website reads `VIDEO_WORKER_URL=http://localhost:8000`, and both processes need the same `VIDEO_WORKER_SECRET`. Relative file links returned by the worker are resolved to that worker origin by the Next.js API routes. Run the worker and Next.js as described above.

If you choose a separate worker host, deploy `worker/` with its Dockerfile and set `VIDEO_WORKER_URL` and the shared secret on the website. You can optionally set `WORKER_PUBLIC_URL` on the worker to its public HTTPS origin. Visitors must be able to reach that origin. Do not use localhost for a separately hosted production worker.

## Behavior and limits

- Public YouTube, Instagram, X/Twitter, and Facebook video URLs use yt-dlp. Site support is best effort: public visibility does not guarantee extraction. Platforms may block datacenter IPs, require authentication, or change their APIs. No private content, user login cookies, or DRM bypass is implemented.
- Pictory preview links display the original embedded preview. The supplied example is a scene-based project, not a finished MP4. Export in Pictory to obtain the original complete MP4. The page also offers Record preview: open the preview tab, share that tab with audio, play it, and stop to save a local WebM/MP4 recording. This captures visible playback, not the original file; quality depends on the display and browser. Chrome/Edge desktop with tab audio are recommended. Recordings are capped at 30 minutes / approximately 400 MB, and refresh cancels unsaved recordings. Stock clips inside a project are never presented as the finished download. Embedding may be refused by the source's frame policy.
- Resolution options come from actual source formats. Original means best available source quality, not upscaling. FFmpeg merges separate audio/video streams without re-encoding. Container can be WebM/MKV when codecs require it.
- Videos must be finished. Duration and size limits are configurable through `VIDEO_MAX_DURATION_SECONDS` and `VIDEO_MAX_FILESIZE_MB`; defaults are 30 minutes and 500 MB, while the example local configuration disables both limits. FFmpeg temporary inputs may occupy additional space. An unavailable browser-compatible preview does not prevent download.
- Form input and results live only in React memory. Refresh and history restoration clear them. The app creates no cookies, localStorage, sessionStorage, or saved history. It cannot reset source-platform cookies or erase server/provider access logs. Previously issued download links remain valid until expiry.
- Vercel Web Analytics counts site visits and page views. Pasted video links and download selections are not sent as custom analytics events.
- Temporary files are deleted after serving or failure. Abrupt container termination can leave files behind; configure host cleanup for stale `linkdrop-*` directories.
- Downloads start via the browser after preparation. A download-time source failure appears in the worker response, rather than in the page. Large downloads take time and consume worker bandwidth.

## Checks

`npm run typecheck` and `npm run build`. Python syntax: `python3 -m py_compile worker/main.py`.

Service integration checks: `node --test tests/worker-forward.test.cjs` and `worker/.venv/bin/python -m unittest discover -s worker -p 'test_*.py' -v` (after installing worker dependencies in the virtual environment). These exercise internal forwarding, same-domain signed downloads, streamed file cleanup, authentication, and queue timeouts without contacting a video platform.

## Reconstructed MP4 for the supplied Pictory preview

`worker/render_preview.py` assembles the public preview media from the supplied project into a new 1280×720 MP4, with its voiceover and background music. It preserves source watermarks. The title overlay is static and uses a substitute font; Pictory's motion effects are not reproduced. The output resolution does not increase the native detail of lower-resolution preview clips. This is a reconstruction, not an official Pictory export.

The local worker exposes the completed `output/pictory-preview-reconstructed-720p.mp4` through the normal analyze/download flow for preview ID `202610010546486168eaab2eba77e41e6b46c45c8fb2f9abd`. Other Pictory links still show the recording/export options. For deployment, place this MP4 on persistent worker storage and set `PICTORY_RECONSTRUCTED_FILE` to its absolute path. The Docker image does not include local output files.

To reproduce locally on macOS: install Pillow in the worker environment, obtain the public preview's matching `previewJson` data, save only its `output`, `elements`, and `sceneDurations` (no storage token is needed), then run:

```
worker/.venv/bin/python worker/render_preview.py output/pictory-render/project.json output/pictory-render
```

The renderer is for this project's specific scene types and continuous voiceover timeline. It validates media hosts and never accesses private storage APIs. It uses the macOS Helvetica font; porting it to Linux requires choosing an installed font path.
