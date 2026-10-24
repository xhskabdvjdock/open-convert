# Deployment and configuration

## Local development

From the repository root:

```sh
python3 -m pip install -r services/api/requirements.txt
python3 services/api/verify_registry.py
python3 services/api/standalone.py
```

Run the last command in one terminal. In another, run `npm ci --prefix apps/web` and `npm run dev`. Browse to `http://localhost:3000`. The browser API base is `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). The API only emits CORS headers for origins in `CORS_ORIGINS`.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Public API origin compiled into the web app; set before the web image build. |
| `CORS_ORIGINS` | local web origins | Comma-separated exact browser origins allowed by the API. |
| `API_HOST` / `API_PORT` | `127.0.0.1` / `8000` | API bind address and port. Compose sets `0.0.0.0`. |
| `MAX_UPLOAD_BYTES` | 104857600 | Maximum upload and platform result size (100 MiB). |
| `MAX_IMAGE_UPLOAD_BYTES` | 20971520 | Maximum image size (20 MiB). |
| `MAX_MEDIA_OUTPUT_BYTES` | 209715200 | Maximum converted media output (200 MiB). |
| `ENABLE_PLATFORM_DOWNLOADS` | `true` | Enables live yt-dlp analysis and downloads when yt-dlp and ffprobe are installed. Set `false` to disable. |

## Container profile

Copy `.env.example` to `.env`, set the browser-reachable HTTPS API address in `NEXT_PUBLIC_API_URL`, and set `CORS_ORIGINS` to the exact web origin. Then run:

```sh
docker compose build
docker compose up -d
docker compose logs -f api web
```

The API image installs FFmpeg and Python dependencies, runs the real conversion verification matrix during image build, and starts as a non-root user. Compose applies a 2 GiB memory and 2 CPU limit to the API container. Confirm `/api/health` and `/api/capabilities` from outside the host. Platform URL analysis is enabled by default when dependencies are present; set `ENABLE_PLATFORM_DOWNLOADS=false` to disable it. The API returns live options for each URL; there is no static promise that every upstream extractor works.

The current service is synchronous and buffers requests/results in memory. Use small test files and limit access while testing. A production public deployment still needs isolated durable workers, concurrency/rate limits, durable job metadata/history, storage retention/cleanup, monitoring, and a malware scanning decision. Configure reverse-proxy request body and timeout limits to match or undercut the API's configured caps. Never expose an unauthenticated high-resource service without abuse controls. TLS should terminate at a properly configured reverse proxy or hosting platform.

## Vercel profile

The repository's `vercel.json` declares two services: the Next.js app at `apps/web/` and a custom API container at `services/api/Dockerfile.vercel`. It routes `/api/*` to the API container and other paths to the web service. The frontend uses same-origin `/api` requests in production. Import the repository root in Vercel, then set the project's **Framework Preset** to **Services** under **Build & Development Settings**. Vercel ignores the multi-service configuration unless the project is set to Services. The API explicitly selects the `container` runtime. No `NEXT_PUBLIC_API_URL` is needed for this setup.

The Vercel container binds to the injected `PORT` (default 80) and has lower configured caps: 3 MiB images and 4 MiB for other uploads/results. Vercel documents a 4.5 MB request/response body limit for Functions; files and downloads above the configured cap are not suitable for this profile. This profile allows small-file and link-analysis experiments, not large media conversion. Vercel container services and `vercel.json` routing availability can depend on account/feature access. If the build rejects this service config, use the Compose profile or deploy the API separately to a Docker host. This Vercel configuration has not been deployed or verified from this workspace.

## External platform verification

The build environment could not resolve external DNS, so no real platform integration is marked passed. On the deployed host, check the yt-dlp version in `/api/capabilities`, paste a URL you are authorized to download, and verify all of the following: live analysis returns title/extractor/options, a selected option downloads a nonempty file, the API validates and decodes it, the browser receives it, and the saved file opens. Record the tested URL/service, date, engine version, selected format, and result for your release notes. A successful test for one URL does not establish support for every site or URL.

## Font

No authorized Thmanyah font source/license was available in the workspace. The application does not claim to bundle Thmanyah; its Arabic font family is configurable with a Noto Sans Arabic system fallback. If adding authorized self-hosted assets, retain the license and define local `@font-face` rules in `apps/web/app/globals.css`.
