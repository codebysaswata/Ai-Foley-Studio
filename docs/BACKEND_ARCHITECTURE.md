# AI Foley Studio HTTP backend architecture

The standalone service is `ai_foley_studio.api.main:app`; it does not start or depend on Streamlit. FastAPI handles authenticated REST requests, SQLite stores job state, and a bounded in-process queue feeds exactly one background inference worker. That worker owns one reusable `FoleyPipeline` and therefore serializes GPU work while reusing the MMAudio service lifecycle. Qwen scene analysis remains lazy and uses the existing analyzer.

Each accepted UUID has `input/`, `working/`, `output/`, and `metadata/` directories below the configured data root. Uploads are streamed with a byte cap, named by the server, probed with FFprobe, and decoded with FFmpeg before queue registration. Only successful outputs recorded in SQLite can be downloaded; canonical-path checks keep artifacts inside their job directory. Completed job directories are removed after the retention period.

The SQLite registry uses short-lived connections and a bounded queue reservation. On startup, interrupted `running` rows are marked failed and are never rerun; unstarted queued jobs are restored only when their files exist and capacity permits. A process-wide OS file lock prevents a second Uvicorn process from owning the same service storage. Run one Uvicorn worker. Shutdown stops accepting jobs, leaves not-yet-started queued rows recoverable, waits for the active operation, and closes the shared pipeline. Cancellation is cooperative between inference stages; an in-flight model/FFmpeg operation is allowed to finish first.

All `/api/v1` routes require a bearer token. CORS uses an explicit configured origin allowlist and is not authentication. `/health/live` does not load models; `/health/ready` checks storage, SQLite, worker, token configuration, and MMAudio checkpoints without loading weights. OpenAPI and Swagger are served by FastAPI.

The service is intended for a trusted local network. It does not provide TLS, user accounts, per-user quotas, or a distributed queue. Keep the bearer token private, restrict Windows Firewall to the trusted private network, and do not expose this HTTP listener directly to the public internet.
