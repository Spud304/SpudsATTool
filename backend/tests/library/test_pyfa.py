from apps.library.pyfa import parse_pyfa_summary

from .conftest import ABSO_PYFA


def test_sample_summary():
    s = parse_pyfa_summary(ABSO_PYFA)
    assert s.ok
    assert s.dps == 709 and s.volley == 2491
    assert s.ehp_k == 97.6
    assert s.speed_ms == 1230
    assert s.sig_radius_m == 1590
    assert s.cap_stable_pct == 57 and s.cap_lasts_s is None
    assert s.targeting_range_km == 93.8


def test_suffixes_and_unstable_cap():
    text = "DPS: 1,204 (Volley: 12.5k)\nEHP: 1.2M\nSpeed: 2,010 m/s\nSignature: 414 m\nCapacitor: 550 GJ (Not stable)\n"
    s = parse_pyfa_summary(text)
    assert s.dps == 1204 and s.volley == 12500 and s.ehp_k == 1200
    assert s.speed_ms == 2010 and s.sig_radius_m == 414
    assert s.cap_stable_pct is None and s.cap_lasts_s is None


def test_cap_lasts():
    s = parse_pyfa_summary("Capacitor: 1.2k GJ (Lasts 4m 12s)")
    assert s.cap_lasts_s == 252
    assert parse_pyfa_summary("Capacitor: 1.2k GJ (Lasts 1h 2s)").cap_lasts_s == 3602


def test_empty_and_partial():
    assert parse_pyfa_summary("") == parse_pyfa_summary("   ")
    assert not parse_pyfa_summary("").ok
    partial = parse_pyfa_summary("DPS: 100\nSpeed: 900 m/s")
    assert partial.dps == 100 and partial.ehp_k is None and not partial.ok
