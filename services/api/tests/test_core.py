import numpy as np
import pytest
from resonant_common import scoring as sc
from resonant_common.timeutil import parse_timestamp, format_timestamp, validate_range, make_windows, cache_key
from resonant_common.permissions import availability, UNAVAILABLE
from resonant_common.manifest import validate_entry


# ---- timestamps ----
def test_parse_formats():
    assert parse_timestamp("83.5") == 83.5
    assert parse_timestamp("1:23.5") == 83.5
    assert parse_timestamp("1:01:23") == 3683
    with pytest.raises(ValueError):
        parse_timestamp("abc")

def test_format_roundtrip():
    assert format_timestamp(83.5) == "1:23.5"

def test_range_validation():
    assert validate_range(10, 30, 200, 5, 60) == (10, 30)
    for bad in [(10, 12, 200), (10, 100, 200), (30, 20, 200), (190, 205, 200)]:
        with pytest.raises(ValueError):
            validate_range(*bad, 5, 60)

def test_windows_cover_track_and_end_anchor():
    w = make_windows(100, 12, 6)
    assert w[0] == (0, 12) and w[-1][1] == 100
    assert all(b - a == 12 for a, b in w)
    assert make_windows(8, 12, 6) == [(0.0, 8.0)]

def test_cache_key_changes_with_range_and_versions():
    a = cache_key("h", 1, 13, "pp1", "m1")
    assert a != cache_key("h", 1, 14, "pp1", "m1") and a != cache_key("h", 1, 13, "pp2", "m1") and a != cache_key("h", 1, 13, "pp1", "m2")


# ---- permissions ----
def test_metadata_only_has_no_analysis_or_playback():
    av = availability(False, False, False)
    assert not av["audio_analysis"] and not av["playback"] and av["message"] == UNAVAILABLE

def test_analysis_and_playback_are_separate():
    av = availability(True, True, False)
    assert av["audio_analysis"] and not av["playback"]

def test_manifest_requires_explicit_permissions_and_blocks_streaming_sources():
    base = {"source": "artist", "source_id": "1", "title": "t", "artist": "a", "license": "CC BY", "attribution": "x",
            "source_url": "u", "file": "f", "permissions": {"analysis": True, "playback": True, "storage": True},
            "permission_evidence": "https://example.com/proof"}
    assert validate_entry(base) == []
    assert validate_entry({**base, "permission_evidence": ""})
    assert validate_entry({**base, "permissions": {"analysis": True}})
    assert validate_entry({**base, "source": "spotify"})


# ---- scoring / retrieval logic ----
def _seq(rng, n=24):
    base = rng.random((4, 12)) ** 3
    return np.repeat(base, n // 4, axis=0)

def test_harmonic_detects_consistent_transposition():
    rng = np.random.default_rng(0)
    a = _seq(rng)
    score, shift = sc.harmonic_similarity(a, np.roll(a, -3, axis=1))
    assert score > 0.95 and shift == 3

def test_harmonic_prefers_same_over_random():
    rng = np.random.default_rng(1)
    a = _seq(rng)
    assert sc.harmonic_similarity(a, a)[0] > sc.harmonic_similarity(a, _seq(rng))[0]

def test_rhythm_handles_double_time_but_penalises_it():
    same, _ = sc.rhythm_similarity(120, .8, 120, .8, 2, 2)
    double, _ = sc.rhythm_similarity(120, .8, 60, .8, 2, 2)
    far, _ = sc.rhythm_similarity(120, .8, 95, .8, 2, 2)
    assert same > double > far

def test_low_confidence_components_pull_less():
    w = {"embedding": .45, "harmonic": .30, "rhythm": .15, "timbre": .10}
    sure = sc.combine({"embedding": (.5, 1), "harmonic": (1, 1), "rhythm": (.5, 1), "timbre": (.5, 1)}, w)
    unsure = sc.combine({"embedding": (.5, 1), "harmonic": (1, .05), "rhythm": (.5, 1), "timbre": (.5, 1)}, w)
    assert unsure["score"] < sure["score"]

def test_weak_evidence_is_flagged_low():
    w = {"embedding": .45, "harmonic": .30, "rhythm": .15, "timbre": .10}
    r = sc.combine({"embedding": (.2, 1), "harmonic": (.2, 0), "rhythm": (.2, 0), "timbre": (.2, 1)}, w)
    assert r["confidence"] == "low"

def test_whole_song_one_short_match_cannot_dominate():
    one_hit = sc.aggregate_whole_song([0.95] + [None] * 19)
    broad = sc.aggregate_whole_song([0.7] * 20)
    assert broad["score"] > one_hit["score"] and broad["coverage"] == 1.0

def test_collapse_keeps_one_per_recording_group():
    ms = [{"track_id": "a", "group_id": "g1", "score": .9}, {"track_id": "b", "group_id": "g1", "score": .8},
          {"track_id": "c", "group_id": "g2", "score": .7}]
    out = sc.collapse_by_recording(ms)
    assert [m["track_id"] for m in out] == ["a", "c"]

def test_explanations_only_cite_measured_evidence():
    comps = {"embedding": (.5, 1), "harmonic": (.9, .1), "rhythm": (.2, .9), "timbre": (.3, 1)}
    assert sc.explanations(comps, 0) == ["Moderate similarity across several measured features."]
