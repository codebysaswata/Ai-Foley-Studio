# AI Foley Studio application layer

This package provides the backend stage after video analysis: it validates the source video plus `scene_analysis.json` and `sound_context.json`, creates a scene-level MMAudio prompt, generates genuine MMAudio audio, synchronizes it, and can export an MP4 with FFmpeg.

It does not duplicate the separately owned frame-extraction or visual-analysis components. Use the CLI entry point instead of treating the compact Streamlit page as the full workflow:

```powershell
python -m ai_foley_studio.pipeline --help
```

See [`docs/FOLEY_PIPELINE.md`](../docs/FOLEY_PIPELINE.md) for the JSON contract, checkpoint configuration, runtime commands, duration policy, and operational limits.
