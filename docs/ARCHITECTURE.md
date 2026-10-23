# Architecture

The repository separates the Next.js interface (`apps/web`) from a Python standard-library HTTP service (`services/api/standalone.py`). The web client submits a file to `/api/inspect` to obtain its content-detected format and verified outputs, then submits it to `/api/convert`. Pillow or FFmpeg performs the conversion and the validated output streams back as a download response. The API provides `/api/health`, `/api/capabilities`, and `/api/formats`.

This is intentionally a synchronous local development architecture. It has no database, durable queue, background worker, persistent history, or object storage. The response itself is the only result delivery mechanism. Future asynchronous jobs must use persistent state and a private storage capability rather than presenting this request model as durable.

Platform links are analyzed by a separate yt-dlp child process. It returns a short list of live format choices; the browser submits only a constrained quality key, and the worker resolves that key against fresh extractor metadata. The worker has no cookies or arbitrary CLI flags, applies a public-IP connection guard, caps response/download size and runtime, and validates the result with ffprobe/FFmpeg before returning it. Platform downloads are disabled unless `ENABLE_PLATFORM_DOWNLOADS=true` is set on the API host.
