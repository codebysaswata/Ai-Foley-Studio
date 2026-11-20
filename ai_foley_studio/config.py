"""Portable configuration for the AI Foley Studio backend pipeline.

The package never embeds a machine-specific checkpoint path. Deployments may
point ``AI_FOLEY_CHECKPOINT_ROOT`` at an existing official MMAudio checkout
when model files are shared between clones.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = PACKAGE_DIR.parent
WORKSPACE_ROOT = PACKAGE_DIR
UPLOAD_DIR = WORKSPACE_ROOT / "uploads"
OUTPUT_DIR = WORKSPACE_ROOT / "outputs"
TEMP_DIR = WORKSPACE_ROOT / "temp"

SUPPORTED_VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".avi", ".webm"})
SUPPORTED_AUDIO_EXTENSIONS = frozenset({".flac", ".wav"})
SUPPORTED_MODEL_VARIANTS = frozenset(
    {"small_16k", "small_44k", "medium_44k", "large_44k", "large_44k_v2"}
)


def _environment_path(variable: str, fallback: Path) -> Path:
    """Resolve a configurable path without retaining an unresolved string."""
    value = os.getenv(variable)
    return Path(value).expanduser().resolve() if value else fallback.resolve()


@dataclass(frozen=True)
class FoleySettings:
    """Runtime configuration shared by the pipeline and MMAudio service."""

    repository_root: Path = field(
        default_factory=lambda: _environment_path("AI_FOLEY_REPOSITORY_ROOT", REPOSITORY_ROOT)
    )
    checkpoint_root: Path = field(
        default_factory=lambda: _environment_path("AI_FOLEY_CHECKPOINT_ROOT", REPOSITORY_ROOT)
    )
    output_dir: Path = field(
        default_factory=lambda: _environment_path("AI_FOLEY_OUTPUT_DIR", OUTPUT_DIR)
    )
    temp_dir: Path = field(
        default_factory=lambda: _environment_path("AI_FOLEY_TEMP_DIR", TEMP_DIR)
    )
    model_variant: str = field(
        default_factory=lambda: os.getenv("AI_FOLEY_MODEL_VARIANT", "small_16k")
    )
    device: str = field(default_factory=lambda: os.getenv("AI_FOLEY_DEVICE", "auto"))
    precision: str = field(default_factory=lambda: os.getenv("AI_FOLEY_PRECISION", "auto"))
    default_generation_duration: float = field(
        default_factory=lambda: float(os.getenv("AI_FOLEY_DEFAULT_DURATION", "4.0"))
    )
    max_generation_duration: float = field(
        default_factory=lambda: float(os.getenv("AI_FOLEY_MAX_DURATION", "8.0"))
    )
    default_num_steps: int = field(
        default_factory=lambda: int(os.getenv("AI_FOLEY_NUM_STEPS", "25"))
    )
    default_guidance_scale: float = field(
        default_factory=lambda: float(os.getenv("AI_FOLEY_GUIDANCE_SCALE", "4.5"))
    )

    @property
    def weights_dir(self) -> Path:
        return self.checkpoint_root / "weights"

    @property
    def external_weights_dir(self) -> Path:
        return self.checkpoint_root / "ext_weights"

    def validate(self) -> None:
        """Validate configuration before expensive model work begins."""
        if self.model_variant not in SUPPORTED_MODEL_VARIANTS:
            raise ValueError(
                f"Unsupported MMAudio variant {self.model_variant!r}; choose one of "
                f"{', '.join(sorted(SUPPORTED_MODEL_VARIANTS))}."
            )
        if self.default_generation_duration <= 0 or self.max_generation_duration <= 0:
            raise ValueError("Generation durations must be greater than zero.")
        if self.default_generation_duration > self.max_generation_duration:
            raise ValueError("default_generation_duration cannot exceed max_generation_duration.")
        if self.default_num_steps <= 0 or self.default_guidance_scale <= 0:
            raise ValueError("Inference steps and guidance scale must be greater than zero.")


def get_settings() -> FoleySettings:
    """Read and validate the current process configuration."""
    settings = FoleySettings()
    settings.validate()
    return settings
