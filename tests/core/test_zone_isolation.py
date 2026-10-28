"""Stratul 1 al zidului: procesul unei zone nu poate obține calea bazei celeilalte zone."""

import pytest

from versoml.config import Settings


def test_client_process_cannot_reach_aml_db(tmp_path):
    s = Settings(versoml_zone="client", versoml_var_dir=tmp_path)
    assert s.client_db.name == "client_zone.db"
    with pytest.raises(PermissionError):
        _ = s.aml_db


def test_aml_process_cannot_reach_client_db(tmp_path):
    s = Settings(versoml_zone="aml", versoml_var_dir=tmp_path)
    assert s.aml_db.name == "aml_zone.db"
    with pytest.raises(PermissionError):
        _ = s.client_db


def test_zone_urls_honour_overrides(tmp_path):
    s = Settings(versoml_host="0.0.0.0", versoml_var_dir=tmp_path, versoml_aml_url="http://aml:8001/")
    assert s.aml_url == "http://aml:8001"
    assert s.client_url == "http://127.0.0.1:8000"
