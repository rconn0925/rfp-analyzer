"""The one-command `run` flow and capabilities-profile loading (Phase 4)."""

from __future__ import annotations

import argparse
import json

import pytest

from rfp_analyzer.cli import _load_profile, build_parser
from rfp_analyzer.pipeline.analysis.judge import DEMO_PROFILE
from rfp_analyzer.pipeline.models import CapabilityProfile


class TestRunParser:
    def test_drafts_is_optional_so_a_first_run_can_stop_at_the_handoff(self):
        args = build_parser().parse_args(["run", "pkg"])
        assert args.command == "run"
        assert args.drafts is None
        assert args.out == "artifacts"

    def test_accepts_the_full_recording_set(self):
        args = build_parser().parse_args(
            ["run", "pkg", "--drafts", "d.jsonl", "--verdicts", "v.jsonl",
             "--profile", "p.json", "--out", "o"]
        )
        assert args.drafts == "d.jsonl"
        assert args.verdicts == "v.jsonl"
        assert args.profile == "p.json"
        assert args.out == "o"


class TestProfileLoading:
    def test_defaults_to_the_fictional_demo_profile(self):
        assert _load_profile(None) is DEMO_PROFILE

    def test_loads_a_real_profile_from_disk(self, tmp_path):
        profile = CapabilityProfile(
            profile_id="acme", company_name="Acme Corp", is_fictional=False,
            capabilities=["CAP-01 does things"],
        )
        path = tmp_path / "p.json"
        path.write_text(profile.model_dump_json(), encoding="utf-8")
        loaded = _load_profile(str(path))
        assert loaded is not None
        assert loaded.company_name == "Acme Corp"
        assert loaded.is_fictional is False

    def test_unreadable_profile_fails_rather_than_silently_using_the_demo(self, tmp_path):
        """Falling back to the fictional profile on a typo would export verdicts
        that look real but were judged against invented capabilities."""
        assert _load_profile(str(tmp_path / "missing.json")) is None

    def test_malformed_profile_fails(self, tmp_path):
        path = tmp_path / "p.json"
        path.write_text("{not json", encoding="utf-8")
        assert _load_profile(str(path)) is None


class TestAnalyzeParser:
    def test_profile_flag_is_available(self):
        args = build_parser().parse_args(["analyze", "a", "--profile", "p.json"])
        assert args.profile == "p.json"

    def test_verdicts_stay_optional(self):
        """A matrix with no judgments is still a useful matrix; it just says so."""
        args = build_parser().parse_args(["analyze", "a"])
        assert args.verdicts is None


def test_run_stops_cleanly_when_no_drafts_are_supplied(tmp_path, monkeypatch, capsys):
    """A first run must parse, emit chunks, and explain the handoff — exit 0, not an error."""
    from rfp_analyzer import cli

    monkeypatch.setattr(cli, "_run_parse_quiet", lambda args: 0)
    monkeypatch.setattr(cli, "_run_chunks_quiet", lambda args: 0)

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    args = argparse.Namespace(
        package_dir=str(pkg), drafts=None, verdicts=None, profile=None, out=str(tmp_path / "a")
    )
    assert cli._run_all(args) == 0
    out = capsys.readouterr().out
    assert "Stopping here" in out
    assert "drafts.jsonl" in out


def test_run_rejects_a_missing_package_directory(tmp_path):
    from rfp_analyzer import cli

    args = argparse.Namespace(
        package_dir=str(tmp_path / "nope"), drafts=None, verdicts=None,
        profile=None, out=str(tmp_path),
    )
    assert cli._run_all(args) == 2


@pytest.mark.parametrize("command", ["parse", "chunks", "extract", "judgments", "analyze", "run"])
def test_every_documented_subcommand_is_registered(command):
    parser = build_parser()
    actions = [a for a in parser._actions if hasattr(a, "choices") and a.choices]
    assert any(command in (a.choices or {}) for a in actions)


def test_profile_round_trips_through_json(tmp_path):
    profile = CapabilityProfile(company_name="X", capabilities=["a", "b"])
    path = tmp_path / "p.json"
    path.write_text(profile.model_dump_json(), encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8"))["capabilities"] == ["a", "b"]
