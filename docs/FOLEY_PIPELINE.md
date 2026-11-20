# AI Foley Studio backend pipeline

`ai_foley_studio.pipeline` begins **after** video analysis. It consumes the original video and the two JSON artifacts produced by the separate video-analysis implementation. It does not extract frames or perform visual inference itself.

## Integration contract

The observed `scene_analysis.json` structure contains a `scene_summary` plus an `events` array. Events use `timestamp_start` / `timestamp_end` in seconds and may include `action`, `objects`, `source_object`, `environment`, `surroundings`, `material`, `intensity`, `rhythm`, `texture`, `potential_sound`, `confidence`, and `visual_evidence`.

The companion `sound_context.json` contains a `scene_summary`, `total_events`, and `sound_contexts`. Each sound context uses the same optional event fields, with `source` in place of (or alongside) `source_object`.

The context engine validates both documents, combines matching events by action and timestamp (within 0.25 seconds), retains raw evidence in metadata, and rejects meaningful conflicting facts. The observed artifacts did not carry an original-video identifier, so the pipeline can only verify video/JSON association when either JSON adds a `video_path`, `source_video`, `video`, or `input_video` field.

## Runtime configuration

The default configuration is project-relative: it uses this checkout's
`mmaudio/`, `weights/`, and `ext_weights/` directories. It does not require
`D:\mmaudio\MMAudio` at runtime. Environment variables remain available only
when deliberately sharing another local checkout:

```powershell
$env:AI_FOLEY_REPOSITORY_ROOT = "D:\ju hackathon\ai_foley_studio"
$env:AI_FOLEY_CHECKPOINT_ROOT = (Get-Location).Path
$env:AI_FOLEY_MODEL_VARIANT = "small_16k"
$env:AI_FOLEY_OUTPUT_DIR = "$PWD\ai_foley_studio\outputs"
```

`AI_FOLEY_REPOSITORY_ROOT` must identify the checkout containing the original `mmaudio` package. `AI_FOLEY_CHECKPOINT_ROOT` identifies the checkpoint root, where `weights/mmaudio_small_16k.pth`, `ext_weights/v1-16.pth`, `ext_weights/best_netG.pt`, and `ext_weights/synchformer_state_dict.pth` reside. The adapter rejects an MMAudio import outside the configured repository and does not call a checkpoint downloader.

## Commands

From the repository root, use the environment that already has the verified CUDA-compatible MMAudio dependencies:

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m ai_foley_studio.pipeline `
  --video "C:\path\to\input.mp4" `
  --scene-json "C:\path\to\scene_analysis.json" `
  --sound-json "C:\path\to\sound_context.json" `
  --duration 4 --num-steps 25 --guidance-scale 4.5
```

This creates one collision-resistant `ai_foley_studio/outputs/job_<timestamp>_<id>/` directory containing `generated_foley.flac`, `processed_foley.wav`, `metadata.json`, and `logs/pipeline.log`. Audio-only output is the default.

Add `--export-video` to mux a duration-matched `final_video.mp4`. Add `--timing-offset 0.15` to delay audio; use a negative value to advance it. Add `--target-lufs -16` to apply two-pass FFmpeg `loudnorm`; FFmpeg and FFprobe must be on `PATH` for normalization or final MP4 validation.

## Guarantees and limitations

The MMAudio adapter directly uses the original project’s `get_my_mmaudio`, `FeaturesUtils`, `load_video`, `FlowMatching`, and `generate` inference functions. It retains one model instance per process and serializes inference. It never fabricates an audio fallback.

MMAudio conditions each chunk on the events overlapping that chunk; it does not place individual sounds at sample-accurate positions inside the chunk. Event timestamps therefore guide chunk selection at chunk-level resolution. Timing adjustment shifts the assembled track exactly once before final duration fitting.

## RTX 2050 4 GB lifecycle

The Streamlit workflow loads Qwen3-VL only for analysis, then drops its model
and processor references, runs garbage collection, and clears unused CUDA
allocator memory before MMAudio starts. MMAudio is explicitly closed after a
Streamlit generation job. Do not keep Qwen loaded while starting MMAudio.

The verified initial setting is `small_16k`, four seconds, 25 sampling steps.
The four-second setting is now the maximum inference chunk length. The pipeline
walks the complete source video in sequential chunks, so videos longer than
eight seconds receive generated audio throughout instead of a short clip padded
with silence.

## Full-video chunk generation

`audio/chunked_generation.py` calculates contiguous core ranges and extracts a
video segment for each MMAudio call. Each scene event is assigned to every core
range its timestamps overlap. MMAudio receives a prompt built from that chunk's
events; chunks without assigned events receive a sparse ambience prompt based
on the scene summary. Chunks are generated sequentially through the retained local model,
keeping GPU memory use bounded to one inference at a time.

Neighboring extracted segments include a short overlap. Their generated audio
is joined with a linear crossfade, then checked against the original video
duration. A failed, missing, empty, silent, or materially short chunk fails the
job with its chunk number; generation never substitutes silence for a failed
chunk. The existing synchronization step applies any requested timing offset
once to the assembled track, and export still validates the resulting MP4 with
FFprobe.

## FFmpeg prerequisite

Audio-only output works without FFmpeg. MP4 export and loudness normalization
require both `ffmpeg.exe` and `ffprobe.exe` on `PATH`; the UI disables MP4
export until both are discoverable. The Python package `ffmpeg-python` is not a
replacement for those executables.
