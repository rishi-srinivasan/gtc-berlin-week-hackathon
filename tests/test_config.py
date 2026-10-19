import os

from pii import config


def write(tmp_path, monkeypatch):
    (tmp_path / "config.toml").write_text(
        'profile = "a"\n[profiles.a]\nX_MODEL = "m1"\nX_URL = "<placeholder>"\nX_EMPTY = ""\n'
        '[profiles.b]\nX_MODEL = "m2"\n')
    monkeypatch.chdir(tmp_path)
    for k in ("X_MODEL", "X_URL", "X_EMPTY", "PII_PROFILE"):
        monkeypatch.delenv(k, raising=False)


def test_profile_applied_placeholders_skipped(tmp_path, monkeypatch):
    write(tmp_path, monkeypatch)
    assert config.apply() == "a"
    assert os.environ["X_MODEL"] == "m1" and "X_URL" not in os.environ and "X_EMPTY" not in os.environ


def test_env_beats_profile_and_profile_switch(tmp_path, monkeypatch):
    write(tmp_path, monkeypatch)
    monkeypatch.setenv("X_MODEL", "from-env")
    config.apply()
    assert os.environ["X_MODEL"] == "from-env"
    monkeypatch.delenv("X_MODEL")
    monkeypatch.setenv("PII_PROFILE", "b")
    config.apply()
    assert os.environ["X_MODEL"] == "m2"
