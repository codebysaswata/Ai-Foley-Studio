# AI Foley Studio API v1 contract

The backend is a separate process. Local base URL is `http://127.0.0.1:8000`; over a trusted LAN replace the host with the backend laptop's private IPv4 address. The frontend must send `Authorization: Bearer <AI_FOLEY_API_TOKEN>` on every `/api/v1` call. Configure `AI_FOLEY_CORS_ORIGINS` to the exact frontend origin. CORS is a browser policy, not authentication. The API is plain HTTP by default and is intended only for a trusted private network.

## Endpoints

| Method and path | Purpose |
|---|---|
| `GET /health/live` | Process liveness; no model load or auth. |
| `GET /health/ready` | Storage, DB, worker, auth configuration and checkpoint readiness; 503 until ready. |
| `POST /api/v1/jobs` | Multipart upload; returns 202 with a UUID. |
| `GET /api/v1/jobs?limit=20&offset=0&status=queued` | Bounded pagination; status is optional. `limit` 1–100. |
| `GET /api/v1/jobs/{job_id}` | State, stage, progress, timestamps, chunk diagnostics, errors, artifacts. |
| `POST /api/v1/jobs/{job_id}/cancel` | Cancel queued immediately or request cooperative cancellation while running. |
| `GET /api/v1/jobs/{job_id}/artifacts` | List outputs after success. |
| `GET /api/v1/jobs/{job_id}/artifacts/{artifact_name}` | Download `processed_foley.wav` or, when requested, `final_video.mp4`. |

Multipart `POST /api/v1/jobs` fields: required `video`; optional paired `scene_analysis` and `sound_context` JSON files; optional `prompt_override` (1000 chars), `negative_prompt` (default `music, speech`, 500 chars), `chunk_seconds` (0.64–8, default 4), `num_steps` (1–100, default 25), `guidance_scale` (>0–20, default 4.5), `timing_offset_seconds` (-60–60, default 0), `target_lufs` (-40–0, optional; omitted means no loudness normalization), and `export_video` (default false). Upload size, duration and pixel caps are server-configurable. Context JSON is checked against the scene/context models and against the uploaded video by the existing context engine.

Minimal upload example:

```javascript
const form = new FormData();
form.append("video", file, file.name);
form.append("chunk_seconds", "4");
form.append("export_video", "true");
const accepted = await fetch(`${BASE_URL}/api/v1/jobs`, {
  method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form
}).then(r => r.json()); // { job_id, status, status_url, created_at }
```

Poll the returned status URL about every 2–3 seconds; use a longer interval for large jobs. States are `queued → running → succeeded | failed | cancelled`. `progress_percent` is approximate stage/chunk progress, not a time estimate. `current_chunk` and `total_chunks` may be null outside audio generation. A running cancellation is pending until the currently executing model or media operation returns. A failed job includes a safe `error_code` and message; server logs retain details.

On success, retrieve `artifacts`, then fetch each `download_url` with the same Authorization header. The WAV is always produced; MP4 is listed only if requested and exported successfully. Artifacts are available only for successful jobs and are removed after retention expiry.

Errors use `{ "error": { "code": "...", "message": "...", "request_id": "..." } }`. Common statuses: 400 invalid context; 401 unauthorized; 404 unknown job/artifact; 409 job not ready/cannot cancel terminal job; 413 upload/duration/resolution limit; 415 unsupported or corrupt media; 422 request validation; 429 queue full; 503 worker, media tools, or configuration unavailable; 500 unexpected failure. Do not retry a 4xx unchanged. For network failures or 5xx, query job status before resubmitting to avoid duplicate expensive generation. A 202 means durably queued, not completed.

## TypeScript response shapes

```typescript
type JobState = "queued" | "running" | "succeeded" | "failed" | "cancelled";
interface Artifact { name: string; media_type: string; size_bytes: number; duration_seconds: number | null; download_url: string; }
interface JobAccepted { job_id: string; status: JobState; status_url: string; created_at: string; }
interface JobStatus {
  job_id: string; status: JobState; processing_stage: string; progress_percent: number;
  current_chunk: number | null; total_chunks: number | null; creation_time: string;
  start_time: string | null; completion_time: string | null; cancellation_requested: boolean;
  chunk_details: Record<string, unknown> | null; error_code: string | null;
  error_message: string | null; artifacts: Artifact[];
}
interface JobList { items: JobStatus[]; limit: number; offset: number; total: number; }
interface ApiError { error: { code: string; message: string; request_id: string | null }; }
```

## LAN setup

Bind the backend to `0.0.0.0`, but call it from the frontend using `http://BACKEND_LAN_IP:8000` (never frontend `localhost`). Allow inbound TCP 8000 only on the trusted Windows Private network, preferably scoped to the frontend host. Configure the exact browser origin. Keep the bearer credential out of source control and public client bundles. If the frontend uses HTTPS, plain HTTP requests may be blocked as mixed content; terminate HTTPS on a trusted proxy. Do not expose the service directly to the public internet. See [backend deployment](BACKEND_DEPLOYMENT.md) for exact PowerShell setup.
