# AI Foley Studio

**Turn silent video into context-aware Foley audio.**

AI Foley Studio is a local video-to-audio application that analyzes
visual events in a video and uses generative AI to create corresponding
sound effects. It combines **Qwen3-VL** for visual scene understanding
with **MMAudio** for video-conditioned audio generation, then assembles
and processes the generated audio into a soundtrack that can be
downloaded as WAV or optionally muxed into an MP4.

> **Project status:** Research / hackathon prototype. The application
> integrates pretrained models; it does not train the Qwen3-VL or
> MMAudio foundation models from scratch. Generated results require
> human review and may not always match every visual event.

------------------------------------------------------------------------

## What it does

Given a silent or muted video, AI Foley Studio:

1.  Reads the video metadata and samples frames at regular time
    intervals.
2.  Uses Qwen3-VL-2B-Instruct to interpret the sampled frames and
    produce structured scene and event descriptions.
3.  Converts the visual analysis into structured Foley context,
    including actions, objects, materials, environments and estimated
    timestamps.
4.  Builds sound-generation prompts from the context using the project's
    sound rules and prompt engine.
5.  Divides the source video into manageable, overlapping chunks and
    runs MMAudio inference sequentially for each chunk.
6.  Assigns events to the chunks whose time ranges they overlap, then
    combines the generated audio with short crossfades.
7.  Checks generated audio for validity and quality issues, applies the
    configured timing and duration handling, and optionally normalizes
    loudness.
8.  Optionally combines the processed soundtrack with the original video
    and validates the exported MP4.

The goal is to reduce repetitive sound-effect sourcing and
synchronization work in video post-production. It is an assistive
workflow, not a replacement for professional sound design or final human
quality control.

## How it works

### Processing pipeline

``` text
                 INPUT VIDEO
                      |
                      v
          Video inspection and frame sampling
                      |
                      v
              Qwen3-VL analysis
          (visual scene + event extraction)
                      |
                      v
        Structured scene/context JSON artifacts
                      |
                      v
          Context validation and event merging
                      |
                      v
          Foley sound-plan and prompt creation
                      |
                      v
           Video split into time chunks
                      |
                      v
         MMAudio inference, one chunk at a time
                      |
                      v
       Chunk waveform checks, retries and reports
                      |
                      v
             Crossfade / audio assembly
                      |
                      v
          Timing alignment and duration fitting
                      |
                      v
         Optional loudness normalization
                      |
             +--------+--------+
             |                 |
             v                 v
       Processed WAV       Optional MP4 export
                                 |
                                 v
                         FFprobe validation
```

### Model responsibilities

  -----------------------------------------------------------------------
  Component                           Role in this application
  ----------------------------------- -----------------------------------
  **Qwen3-VL-2B-Instruct**            Interprets sampled video frames and
                                      returns structured visual
                                      scene/event information. It does
                                      not generate audio.

  **MMAudio**                         Generates audio conditioned on
                                      video and the text prompt
                                      constructed for each chunk.

  **MMAudio supporting components**   The integrated MMAudio
                                      implementation uses its own
                                      feature-extraction and generation
                                      stack, including CLIP/Synchformer
                                      conditioning, flow matching, an
                                      audio VAE and a vocoder as required
                                      by the selected model
                                      configuration.
  -----------------------------------------------------------------------

Qwen3-VL and MMAudio are loaded in separate stages. The scene-analysis
model is released before MMAudio inference begins, reducing simultaneous
GPU memory use.

### Important timing detail

Event timestamps determine which generation chunks receive an event's
context. The current design does **not** claim sample-accurate placement
of each individual sound event inside a chunk. MMAudio generates a
chunk-level soundtrack conditioned on the chunk's video and prompt. The
assembled result is duration-fitted and can receive a global timing
offset.

## Features

-   Video upload and preview in a Streamlit interface.
-   Video metadata inspection and timestamped frame extraction.
-   Qwen3-VL scene and Foley-event analysis.
-   Downloadable scene-analysis and sound-context JSON.
-   Rule-based Foley categorization and prompt construction.
-   Sequential, chunk-based MMAudio generation for the full source-video
    timeline.
-   Event-to-chunk assignment using timestamp overlap.
-   Short crossfades between adjacent generated chunks.
-   Waveform checks for malformed, non-finite, unexpectedly short,
    clipped or near-silent output, with bounded retries according to the
    quality policy.
-   Audio inspection, timing offset and duration matching.
-   Optional two-pass EBU R128 loudness normalization through FFmpeg.
-   WAV download and optional MP4 export.
-   Per-job metadata, logs and chunk-level generation diagnostics.
-   Local model/checkpoint configuration through environment variables.

## Technology stack

  -----------------------------------------------------------------------
  Area                                Technology
  ----------------------------------- -----------------------------------
  Main language                       Python

  User interface                      Streamlit

  HTTP backend                        FastAPI, Uvicorn, Pydantic

  Visual understanding                Hugging Face Transformers,
                                      Qwen3-VL-2B-Instruct,
                                      `qwen-vl-utils`

  Audio generation                    MMAudio

  Deep learning                       PyTorch, TorchAudio

  Video/frame processing              OpenCV, PyAV (through the MMAudio
                                      video pipeline)

  Audio/video tools                   FFmpeg, FFprobe

  Configuration                       Python environment variables and
                                      project settings

  Tests                               pytest
  -----------------------------------------------------------------------

**Architecture note:** The repository includes two application
interfaces:

-   **Streamlit** (`ai_foley_studio/app.py`) is the interactive
    video-to-Foley application.
-   **FastAPI** (`ai_foley_studio/api/main.py`) exposes a separate
    backend API for job-based integration.

The Streamlit workflow can be run independently. Start the FastAPI
service only when you need the HTTP API or an integration that uses it.

## Repository layout

``` text
ai_foley_studio/
├── app.py                       # Streamlit application
├── config.py                    # Runtime paths and generation settings
├── pipeline.py                  # Main post-analysis Foley orchestration
├── requirements-app.txt         # UI and Qwen application dependencies
├── requirements-api.txt         # FastAPI backend dependencies
├── api/
│   ├── main.py                   # FastAPI application entry point
│   ├── routes.py                 # API endpoints
│   ├── manager.py                # Job lifecycle and orchestration
│   ├── settings.py               # Environment-based API settings
│   ├── schemas.py                # Request/response schemas
│   ├── security.py               # API token handling
│   ├── storage.py                # API media/storage helpers
│   └── store.py                  # Job state storage
├── audio/
│   ├── chunked_generation.py    # Chunk planning, generation and assembly
│   ├── mmaudio_service.py       # MMAudio model lifecycle and inference adapter
│   ├── audio_processor.py       # Audio inspection and processing
│   └── synchronizer.py          # Timing and duration alignment
├── intelligence/
│   ├── context_engine.py        # Context parsing, validation and event merging
│   ├── prompt_engine.py         # Generation prompt construction
│   └── sound_rules.py           # Foley category and ambience rules
├── video/
│   ├── processor.py             # Metadata inspection and frame extraction
│   └── scene_analyzer.py        # Qwen3-VL loading and scene analysis
├── export/
│   └── video_exporter.py        # MP4 muxing and output validation
├── outputs/                     # Generated job artifacts (created at runtime)
└── temp/                        # Temporary analysis data (created at runtime)

mmaudio/                          # Integrated MMAudio source package
weights/                          # Local MMAudio checkpoints (not committed)
ext_weights/                      # Local supporting checkpoints (not committed)
docs/
├── FOLEY_PIPELINE.md             # Detailed pipeline contract and implementation notes
└── BACKEND_DEPLOYMENT.md         # FastAPI backend deployment notes
tests/                            # Current root-level automated tests
```

Exact contents may evolve; the tree above highlights the main
application modules.

## Requirements

The checked-in Windows dependency constraints currently specify:

-   Windows 10/11 (PowerShell commands are shown below).
-   Python 3.10 or newer is recommended for the application environment.
-   An NVIDIA GPU with a CUDA-compatible PyTorch installation is
    strongly recommended for practical local inference.
-   CUDA toolkit/runtime compatibility with the installed PyTorch wheel
    and NVIDIA driver.
-   FFmpeg and FFprobe on `PATH` for video chunk preparation, loudness
    normalization and MP4 export.
-   Sufficient disk space for model checkpoints, Hugging Face cache,
    temporary frames and generated outputs.

**GPU memory varies by selected MMAudio model, precision, video size and
generation settings.** The repository defaults to `small_16k`, but
actual compatibility and speed must be tested on the target machine. CPU
execution may be possible but can be extremely slow.

## Installation (Windows / PowerShell)

### 1. Clone the repository

``` powershell
git clone https://github.com/codebysaswata/ai_foley_studio.git
cd ai_foley_studio
```

### 2. Create and activate a virtual environment

``` powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

If PowerShell blocks activation, run this for the current terminal
session and activate again:

``` powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 3. Install the pinned PyTorch/CUDA dependencies

The repository's `constraints.txt` currently pins the PyTorch 2.7.1 CUDA
12.8 package set:

``` powershell
python -m pip install -c constraints.txt torch==2.7.1+cu128 torchvision==0.22.1+cu128 torchaudio==2.7.1+cu128 --index-url https://download.pytorch.org/whl/cu128
```

Verify that PyTorch can see the GPU:

``` powershell
python -c "import torch; print('Torch:', torch.__version__); print('CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

If the CUDA check fails, resolve the driver / PyTorch wheel
compatibility before continuing with model inference.

### 4. Install the Streamlit application dependencies

``` powershell
python -m pip install -c constraints.txt -r ai_foley_studio\requirements-app.txt
python -m pip install -e .
```

The editable install installs the MMAudio package and its declared
dependencies. Install the PyTorch CUDA packages first so pip does not
replace them with an unintended build.

### 5. Install the FastAPI dependencies (optional)

Only needed if you plan to run the HTTP API:

``` powershell
python -m pip install -c constraints.txt -r ai_foley_studio\requirements-api.txt
```

The Streamlit app does not require the FastAPI server to be running.

### 6. Install FFmpeg (for full video workflow)

Install an FFmpeg build that includes both `ffmpeg.exe` and
`ffprobe.exe`, then add its `bin` directory to the Windows PATH.

Verify:

``` powershell
ffmpeg -version
ffprobe -version
```

Audio WAV generation does not require final MP4 muxing, but this
pipeline uses FFmpeg to prepare video chunks. MP4 export and loudness
normalization also require FFmpeg/FFprobe.

### 7. Place the required model checkpoints

The application expects local model checkpoints. They are intentionally
not included in Git.

For the default `small_16k` configuration, place the files in the
following locations:

``` text
weights/
└── mmaudio_small_16k.pth

ext_weights/
├── v1-16.pth
├── best_netG.pt
└── synchformer_state_dict.pth
```

Obtain checkpoints only from the relevant official model release and
verify their terms before downloading or using them. Do not commit model
weights, Hugging Face caches, private datasets or generated user videos
to this repository.

Qwen3-VL is loaded through Hugging Face Transformers using model ID
`Qwen/Qwen3-VL-2B-Instruct`; its files are downloaded/cached on first
use unless already available locally.

### 8. Configure the model and paths (optional)

The default settings are project-relative. To override them in
PowerShell:

``` powershell
$env:AI_FOLEY_MODEL_VARIANT = "small_16k"
$env:AI_FOLEY_DEFAULT_DURATION = "4.0"
$env:AI_FOLEY_MAX_DURATION = "8.0"
$env:AI_FOLEY_NUM_STEPS = "25"
$env:AI_FOLEY_GUIDANCE_SCALE = "4.5"
$env:AI_FOLEY_DEVICE = "auto"
$env:AI_FOLEY_PRECISION = "auto"
```

See `ai_foley_studio/config.py` and `docs/FOLEY_PIPELINE.md` for
supported options and checkpoint path overrides.

## Run the application

From the repository root, with the virtual environment activated:

``` powershell
streamlit run .\ai_foley_studio\app.py
```

Streamlit prints a local URL (usually `http://localhost:8501`). Open it
in your browser.

## Run the FastAPI backend (optional)

The FastAPI backend is a separate service from the Streamlit interface.
Install the API dependencies first, then set a strong local bearer
token. The token must contain at least 24 characters.

``` powershell
$env:AI_FOLEY_API_HOST = "127.0.0.1"
$env:AI_FOLEY_API_PORT = "8000"
$env:AI_FOLEY_API_TOKEN = "replace-this-with-a-random-secret-of-at-least-24-characters"
$env:AI_FOLEY_CORS_ORIGINS = "http://localhost:3000"
$env:AI_FOLEY_API_DATA_DIR = "ai_foley_studio/data"

python -m uvicorn ai_foley_studio.api.main:app --host $env:AI_FOLEY_API_HOST --port $env:AI_FOLEY_API_PORT
```

For local development, the API is then available at
`http://127.0.0.1:8000`.

Useful endpoints:

  Endpoint              Purpose
  --------------------- -------------------------------
  `GET /health/live`    Liveness check
  `GET /health/ready`   Readiness check
  `/docs`               Interactive API documentation

API requests that require authentication use the configured bearer
token. Keep the token private; do not commit it or place it in frontend
source code. For additional deployment and configuration details, see
`docs/BACKEND_DEPLOYMENT.md` and `.env.example`.

The API service is intended to be started separately. Running Streamlit
does not automatically start Uvicorn, and running Uvicorn does not
launch the Streamlit interface.

## Using AI Foley Studio

1.  Upload a supported video file: MP4, MOV, AVI or MKV.
2.  Preview the original video.
3.  Select **Analyze Video**. The app inspects the video, samples frames
    and asks Qwen3-VL to return a scene summary and timestamped
    sound-producing events.
4.  Review or download the Scene Analysis JSON and Sound Context JSON.
5.  Choose the maximum MMAudio chunk length and, optionally, provide a
    prompt override.
6.  Select **Generate Foley**. The application validates the context,
    builds prompts, generates audio chunks sequentially, checks and
    assembles them, and processes the resulting soundtrack.
7.  Preview and download the processed WAV.
8.  Enable **Export final MP4** to mux the processed soundtrack into the
    source video. This option is available only when both FFmpeg and
    FFprobe are found.

Each generation job writes a separate output directory with its audio
artifacts, metadata and log. Inspect the job metadata and chunk reports
when diagnosing a result.

## Output artifacts

A completed job can contain:

  -----------------------------------------------------------------------
  Artifact                            Description
  ----------------------------------- -----------------------------------
  `generated_foley.flac`              Raw assembled audio generated by
                                      MMAudio

  `processed_foley.wav`               Duration-adjusted / processed audio

  `final_video.mp4`                   Optional video with the processed
                                      soundtrack

  `metadata.json`                     Job configuration, context,
                                      prompts, stage results and chunk
                                      diagnostics

  `logs/pipeline.log`                 Per-job processing log
  -----------------------------------------------------------------------

The Streamlit analysis stage also saves `scene_analysis.json` and
`sound_context.json` in its temporary/persistent analysis workspace.

## Configuration and quality controls

The pipeline exposes controls for:

-   Maximum generation chunk duration.
-   Optional positive or negative timing offset (through the pipeline
    CLI/configuration).
-   Optional prompt override and negative prompt.
-   MMAudio inference steps and guidance scale.
-   Optional target loudness (LUFS) and true-peak limit.
-   Chunk waveform acceptance thresholds and bounded retries.

The quality checks are guards against malformed or obviously poor
waveform output; they do not prove that a generated sound is
semantically correct, realistic or professionally mixed. Always listen
to and review the result.

For the detailed input JSON contract, chunk strategy, runtime settings
and known timing constraints, see
[docs/FOLEY_PIPELINE.md](docs/FOLEY_PIPELINE.md).

## Testing

Run the current root-level automated test suite from the repository
root:

``` powershell
python -m pytest .\tests -q
```

Install the application and API dependencies before running the full
suite. Some scene-analysis tests import the Transformers/Qwen
integration, so the application requirements must be installed.

The repository also contains older scripts under
`ai_foley_studio/tests/`. They include manual or legacy tests with
outdated import paths and are not part of the root-level pytest command
above. Do not use `python -m pytest -q` as a blanket discovery command
unless those legacy scripts have first been migrated or excluded through
pytest configuration.

Tests cover areas such as API/backend contracts, context and prompt
generation, scene-analysis parsing, model lifecycle, chunked generation,
audio processing and export. They do not replace an end-to-end quality
evaluation using representative real videos and the required model
checkpoints.

## Known limitations

-   Visual analysis is based on sampled frames, not continuous,
    frame-by-frame video understanding. Brief actions between sampled
    frames can be missed.
-   Qwen3-VL estimates event timing from sampled timestamps; event times
    are not guaranteed to be exact.
-   MMAudio generates a chunk-level soundtrack. Event timestamps select
    relevant chunk context but do not guarantee sample-accurate sound
    placement within each chunk.
-   Generated audio can contain incorrect, missing, unexpected or
    low-quality sounds. Human review is required.
-   Crossfades reduce hard joins but cannot guarantee perfect acoustic
    continuity across chunk boundaries.
-   Longer videos increase inference time and may increase storage and
    processing requirements.
-   Results depend on the selected checkpoint, GPU, precision, sampling
    settings and input video.
-   The current application is a prototype and has not been established
    as a production-grade commercial service.

## Privacy and data handling

The primary workflow runs locally. Video frames, analysis JSON files,
generated audio and job outputs are written to local working
directories. Qwen3-VL model files may be downloaded from Hugging Face on
first use and cached locally. Review the model-loading and environment
configuration before using confidential footage, and do not upload
private media or credentials to public repositories.

## Model, dataset and licensing notice

This repository contains an integration of third-party software and
pretrained models. Their licences are separate and must be followed
independently.

-   **MMAudio source code:** See the upstream [MMAudio
    repository](https://github.com/hkchengrex/MMAudio) and its licence.
-   **MMAudio pretrained checkpoints:** The upstream project identifies
    its released checkpoints as **CC BY-NC 4.0**. This is a
    non-commercial licence; do not assume that the checkpoints can be
    used in a paid product or commercial deployment. Obtain separate
    permission or a commercially suitable model/checkpoint before
    commercial use.
-   **Qwen3-VL:** Review the [Qwen3-VL model
    card](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct) and the
    applicable model licence for the exact checkpoint and use case.
-   **Datasets:** Upstream models may have been trained on datasets with
    different terms. This project does not claim that all training data
    or generated outputs are copyright-free.
-   **Other dependencies:** Review the licence of each third-party
    package, model, vocoder and supporting component distributed or used
    with this project.

The top-level MIT licence in this repository does **not** override
third-party model, checkpoint, dataset or dependency licences. This
README is not legal advice.

## Research reference

MMAudio: *Taming Multimodal Joint Training for High-Quality
Video-to-Audio Synthesis*, CVPR 2025.

-   [Paper](https://arxiv.org/abs/2412.15322)
-   [Official MMAudio repository](https://github.com/hkchengrex/MMAudio)
-   [Official MMAudio model
    releases](https://huggingface.co/hkchengrex/MMAudio)
-   [Qwen3-VL model](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct)

If you use the MMAudio research implementation, cite the original work:

``` bibtex
@inproceedings{cheng2025taming,
  title={{MMAudio}: Taming Multimodal Joint Training for High-Quality Video-to-Audio Synthesis},
  author={Cheng, Ho Kei and Ishii, Masato and Hayakawa, Akio and Shibuya, Takashi and Schwing, Alexander and Mitsufuji, Yuki},
  booktitle={CVPR},
  year={2025}
}
```

## Acknowledgements

This project builds on the work of the MMAudio authors and the
developers of Qwen3-VL, PyTorch, Transformers, Streamlit, OpenCV, FFmpeg
and the other open-source dependencies used in the pipeline. Please
consult the upstream projects for their publications, licences and
attribution requirements.

------------------------------------------------------------------------

**AI Foley Studio --- from visual events to generated Foley sound.**
