"""Unavailable wiring point for Anthropic's official text-watermark API.

Anthropic's announcement, updated 1 September 2026 and reviewed 14 October,
confirms a private preview for eligible organizations. This application has
neither an approved access contract nor an implemented endpoint. A general
Anthropic API key does not establish watermark access.

Source: https://www.anthropic.com/news/claude-text-watermark
The signal concerns Claude involvement, not general AI/human authorship.
It remains separate from stylistic classifiers and hidden-character checks.
"""
from __future__ import annotations

import os

from models import TextBlock, TextSpan
from .base import Detector, DetectorUnavailable
from .factory import DetectorFactory


class ClaudeOfficialWatermarkDetector(Detector):
    name = "claude-official-watermark"
    display_name = "Claude official watermark API (private preview, unavailable here)"
    #: A vendor signature, if it is ever published, will not be per-language.

    def __init__(self, api_key: str | None = None, base_url: str | None = None, **config):
        super().__init__(**config)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.base_url = base_url or os.environ.get("ANTHROPIC_WATERMARK_API_BASE_URL")
        # Raised here, not in `analyze_block`. It was raised there, and
        # `Detector.analyze_blocks` turns an exception into an error span per
        # block - so choosing this detector produced one identical
        # "unavailable" finding for every passage on the site, at the end of a
        # full crawl, instead of one sentence before the crawl started. The
        # same reasoning as `ProviderLLMJudgeDetector._get_provider`: an
        # unusable backend is reported once, up front.
        self._unavailable()

    def analyze_block(self, block: TextBlock) -> list[TextSpan]:
        return self._call_official_api(block)

    def _call_official_api(self, block: TextBlock) -> list[TextSpan]:
        self._unavailable()
        return []  # unreachable; kept so the signature stays honest

    @staticmethod
    def _unavailable() -> None:
        raise DetectorUnavailable(
            "Anthropic's official text-watermark API is in private preview. "
            "Approved access and an endpoint contract are not configured in "
            "XBrain Audit. A general Anthropic API key is insufficient. "
            "Watermark evidence concerns Claude involvement; its absence "
            "does not prove human authorship."
        )


DetectorFactory.register(ClaudeOfficialWatermarkDetector.name, ClaudeOfficialWatermarkDetector)
