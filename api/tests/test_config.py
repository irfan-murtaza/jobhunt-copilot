from jobhunt.core.config import Settings


def test_csv_lists_are_parsed_from_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    monkeypatch.setenv("GREENHOUSE_BOARDS", "stripe,gitlab")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.cors_origins == ["http://a.test", "http://b.test"]
    assert settings.greenhouse_boards == ["stripe", "gitlab"]


def test_secrets_are_redacted_in_dumps(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert "sk-ant-secret" not in repr(settings)
    assert settings.langfuse_enabled is False
