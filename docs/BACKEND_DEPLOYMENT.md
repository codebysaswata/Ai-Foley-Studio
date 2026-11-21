# Standalone backend deployment (Windows PowerShell)

Run commands from `D:\ju hackathon\ai_foley_studio`. The existing `.venv` and verified CUDA Torch family are retained. Install the pinned API dependencies under the repository constraints:

```powershell
.\.venv\Scripts\python.exe -m pip install -c constraints.txt -r ai_foley_studio\requirements-api.txt
```

Set a private random token and frontend origin in the current PowerShell session. These token-generation commands work with Windows PowerShell and PowerShell 7. Do not put real credentials in source control:

```powershell
$tokenBytes = New-Object 'Byte[]' 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($tokenBytes)
$env:AI_FOLEY_API_TOKEN = [Convert]::ToBase64String($tokenBytes)
$rng.Dispose()
$env:AI_FOLEY_API_HOST = "0.0.0.0"
$env:AI_FOLEY_API_PORT = "8000"
$env:AI_FOLEY_CORS_ORIGINS = "http://localhost:3000"
$env:AI_FOLEY_API_DATA_DIR = "ai_foley_studio/data"
$env:AI_FOLEY_FFMPEG = "D:\tools\ffmpeg\bin\ffmpeg.exe"
$env:AI_FOLEY_FFPROBE = "D:\tools\ffmpeg\bin\ffprobe.exe"
```

Launch the independent service (one process and one worker):

```powershell
.\.venv\Scripts\python.exe -m uvicorn ai_foley_studio.api.main:app --host $env:AI_FOLEY_API_HOST --port $env:AI_FOLEY_API_PORT --workers 1
```

Local base URL: `http://127.0.0.1:8000`; Swagger: `http://127.0.0.1:8000/docs`; liveness: `/health/live`; readiness: `/health/ready`. For a second computer, find the backend laptop's private IPv4 address with `ipconfig`, then use `http://BACKEND_LAN_IP:8000`. `localhost` on the frontend computer refers to that frontend computer, not this backend host.

Allow inbound TCP 8000 only on the Windows **Private** profile; where practical, scope the firewall rule's remote address to the frontend computer. Verify the active network is trusted/private first, find the backend address with `ipconfig`, then substitute the frontend computer's private address below:

```powershell
$frontendIP = "192.168.1.40"
New-NetFirewallRule -DisplayName "AI Foley Studio API (Private LAN)" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private -RemoteAddress $frontendIP
```

CORS must contain the frontend's exact browser origin, including scheme and port (for example `http://192.168.1.40:3000`). CORS does not authenticate callers; send `Authorization: Bearer <token>` over every API request. Avoid embedding a durable shared secret in a public browser bundle. For HTTPS-hosted frontends, browsers may block calls to this plain-HTTP backend as mixed content; use a trusted HTTPS reverse proxy/tunnel or serve both through HTTPS. Do not expose this service to the public internet.

The default job storage is `ai_foley_studio/data`, configurable with `AI_FOLEY_API_DATA_DIR`; it contains SQLite, uploads, generated artifacts, and a lock file. Keep adequate disk space and protect this directory. Retention defaults to 14 days. On restart, running jobs are marked interrupted and not repeated; queued jobs with intact files can resume. The lock prevents multiple service processes from sharing the same root.

If readiness is `not_ready`, check FFmpeg/FFprobe paths, write access and free disk, the configured token, and MMAudio checkpoint files. Scene analysis loads Qwen only when a job needs automatic analysis. Existing Streamlit launch remains separate: `.\.venv\Scripts\python.exe -m streamlit run ai_foley_studio\app.py`.
