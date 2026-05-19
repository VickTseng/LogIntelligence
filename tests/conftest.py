from pathlib import Path
import pytest
from logiq.config.settings import load_settings, Settings


@pytest.fixture
def settings() -> Settings:
    config_path = Path(__file__).parent.parent / "config.yaml"
    return load_settings(config_path)


@pytest.fixture
def sample_log_text() -> str:
    return (
        "2026-05-19 14:00:01.123 [ERROR] OrderService - Payment failed\n"
        "System.NullReferenceException: Object reference not set\n"
        "  at OrderService.ProcessPayment() in OrderService.cs:line 42\n"
        "  at Controller.Post() in OrderController.cs:line 18\n"
        "2026-05-19 14:00:02.456 [INFO] OrderService - Order rollback complete\n"
    )
