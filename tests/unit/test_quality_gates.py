"""Unit tests for per-page quality metrics and status classification.

All fixtures are synthetic PageInfo objects — no corpus files needed, so the
suite is CI-safe. Statuses covered: ok, scanned, empty, low_text, gibberish.
"""

from rfp_analyzer.pipeline.models import PageInfo
from rfp_analyzer.pipeline.quality import gates
from rfp_analyzer.pipeline.quality.gates import (
    DEFAULT_THRESHOLDS,
    QualityThresholds,
    classify_page,
    compute_page_metrics,
)

PROSE = (
    "The contractor shall provide all personnel, equipment, and materials "
    "necessary to perform the services described in this Performance Work "
    "Statement. All deliverables shall conform to Section L instructions."
)


def make_page(
    text: str,
    *,
    char_count: int | None = None,
    has_images: float = 0.0,
    metrics: dict[str, float] | None = None,
) -> PageInfo:
    base = {
        "cid_count": float(text.count("(cid:")),
        "replacement_char_count": float(text.count("�")),
        "has_images": has_images,
    }
    if metrics:
        base.update(metrics)
    return PageInfo(
        page_number=1,
        quality="pending",
        char_count=len(text) if char_count is None else char_count,
        metrics=base,
        text=text,
    )


class TestScannedAndEmpty:
    def test_tiny_page_with_images_is_scanned(self):
        page = make_page("scan", char_count=5, has_images=1.0)
        assert classify_page(page) == "scanned"

    def test_tiny_page_without_images_is_empty(self):
        page = make_page("blank", char_count=5, has_images=0.0)
        assert classify_page(page) == "empty"


class TestLowText:
    def test_short_page_with_images_is_low_text(self):
        text = "Stamped approval page " * 4  # ~88 chars < LOW_TEXT_CHARS
        page = make_page(text, char_count=100, has_images=1.0)
        assert classify_page(page) == "low_text"


class TestGibberish:
    def test_symbol_soup_low_alpha_ratio_is_gibberish(self):
        text = "@#$%^&*()_+{}|:<>?~`" * 10
        page = make_page(text, has_images=0.0)
        assert classify_page(page) == "gibberish"

    def test_cid_ratio_over_threshold_is_gibberish(self):
        # 5 cid markers over char_count 200 -> 0.025 > GIBBERISH_CID_RATIO 0.02
        text = "(cid:101)" * 5 + "normal readable words follow here " * 4
        page = make_page(text, char_count=200, has_images=0.0)
        assert classify_page(page) == "gibberish"

    def test_replacement_chars_over_max_is_gibberish(self):
        text = PROSE + "�" * 6
        page = make_page(text, has_images=0.0)
        assert classify_page(page) == "gibberish"


class TestOk:
    def test_normal_prose_is_ok_with_ratio_metrics(self):
        page = make_page(PROSE, has_images=0.0)
        assert classify_page(page) == "ok"
        assert isinstance(page.metrics["alpha_ratio"], float)
        assert isinstance(page.metrics["printable_ratio"], float)
        assert 0.0 <= page.metrics["alpha_ratio"] <= 1.0
        assert 0.0 <= page.metrics["printable_ratio"] <= 1.0


class TestComputePageMetrics:
    def test_empty_string_alpha_ratio_is_zero_not_error(self):
        metrics = compute_page_metrics("")
        assert metrics["alpha_ratio"] == 0.0
        assert metrics["printable_ratio"] == 0.0

    def test_prose_ratios_in_unit_interval(self):
        metrics = compute_page_metrics(PROSE)
        assert 0.0 < metrics["alpha_ratio"] <= 1.0
        assert 0.0 < metrics["printable_ratio"] <= 1.0

    def test_cid_and_replacement_counts(self):
        metrics = compute_page_metrics("x (cid:12) y (cid:34) �")
        assert metrics["cid_count"] == 2.0
        assert metrics["replacement_char_count"] == 1.0


class TestThresholdsTunable:
    def test_named_constants_importable_with_documented_defaults(self):
        assert gates.SCANNED_MAX_CHARS == 20
        assert gates.LOW_TEXT_CHARS == 150
        assert gates.GIBBERISH_ALPHA_RATIO == 0.5
        assert gates.GIBBERISH_CID_RATIO == 0.02
        assert gates.GIBBERISH_REPLACEMENT_MAX == 5
        assert DEFAULT_THRESHOLDS.scanned_max_chars == 20

    def test_classify_respects_monkeypatched_default_thresholds(self, monkeypatch):
        # A 100-char imageless prose page is "ok" under defaults...
        text = PROSE[:100]
        page = make_page(text, char_count=100, has_images=0.0)
        assert classify_page(page) == "ok"
        # ...but "empty" once the scanned/empty cutoff is raised above it,
        # proving DEFAULT_THRESHOLDS is read at call time (corpus-tunable).
        raised = QualityThresholds(scanned_max_chars=120)
        monkeypatch.setattr(gates, "DEFAULT_THRESHOLDS", raised)
        assert classify_page(page) == "empty"

    def test_explicit_thresholds_injectable(self):
        text = PROSE[:100]
        page = make_page(text, char_count=100, has_images=0.0)
        custom = QualityThresholds(scanned_max_chars=120)
        assert classify_page(page, thresholds=custom) == "empty"
