from brf_alert_agent.config import load_config


def test_load_config_parses_telegram_and_summary_options(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "BOT_TOKEN_VALUE")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "112233")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
state_db_path: ".data/test.db"
sources:
  - name: "source-a"
    type: "hemnet"
    search_urls:
      - "https://www.hemnet.se/bostader"
notifications:
  telegram:
    enabled: "true"
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    chat_id: "${TELEGRAM_CHAT_ID}"
run:
  send_summary_after_run: "yes"
  summary_max_matches: 8
  summary_max_errors: 2
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.notifications.telegram.enabled is True
    assert config.notifications.telegram.bot_token == "BOT_TOKEN_VALUE"
    assert config.notifications.telegram.chat_id == "112233"
    assert config.run.send_summary_after_run is True
    assert config.run.summary_max_matches == 8
    assert config.run.summary_max_errors == 2

