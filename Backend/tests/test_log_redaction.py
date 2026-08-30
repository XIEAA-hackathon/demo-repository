import logging

from app.core.logging import SensitiveQueryRedactionFilter


def test_websocket_query_token_is_redacted_from_log_arguments():
    record = logging.LogRecord(
        name="uvicorn.error",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "WebSocket %s" [accepted]',
        args=(("127.0.0.1", 1234), "/ws/auction?token=secret.jwt.value&mode=live"),
        exc_info=None,
    )

    assert SensitiveQueryRedactionFilter().filter(record) is True
    rendered = record.getMessage()
    assert "secret.jwt.value" not in rendered
    assert "/ws/auction?token=[REDACTED]&mode=live" in rendered


def test_plain_log_records_are_unchanged():
    record = logging.LogRecord(
        name="uvicorn.error",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Round 1 bid timing bid_id=%s",
        args=(42,),
        exc_info=None,
    )

    SensitiveQueryRedactionFilter().filter(record)
    assert record.getMessage() == "Round 1 bid timing bid_id=42"
