"""Tests unitaires pour le parsing et les calculs tarifaires d'Eaux Terre de Provence."""
from __future__ import annotations

import json
from pathlib import Path


def test_manifest_and_hacs_json() -> None:
    """Vérifie la validité de manifest.json et hacs.json."""
    root = Path(__file__).resolve().parent.parent
    manifest = json.loads(
        (root / "custom_components" / "eauxtdp" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    hacs = json.loads((root / "hacs.json").read_text(encoding="utf-8"))

    assert manifest["domain"] == "eauxtdp"
    assert manifest["config_flow"] is True
    assert "recorder" in manifest["dependencies"]
    assert hacs["name"] == "Eaux Terre de Provence"
    assert hacs["country"] == "FR"


def test_translations_match_strings() -> None:
    """Vérifie que strings.json, fr.json et en.json possèdent les mêmes clés."""
    root = Path(__file__).resolve().parent.parent / "custom_components" / "eauxtdp"
    strings = json.loads((root / "strings.json").read_text(encoding="utf-8"))
    fr = json.loads((root / "translations" / "fr.json").read_text(encoding="utf-8"))
    en = json.loads((root / "translations" / "en.json").read_text(encoding="utf-8"))

    assert set(strings["config"]["step"].keys()) == set(fr["config"]["step"].keys())
    assert set(strings["config"]["step"].keys()) == set(en["config"]["step"].keys())
    assert set(strings["options"]["step"]["init"]["data"].keys()) == set(
        fr["options"]["step"]["init"]["data"].keys()
    )
    assert set(strings["options"]["step"]["init"]["data"].keys()) == set(
        en["options"]["step"]["init"]["data"].keys()
    )
