import pytest

from core.local_http import validate_endpoint


@pytest.mark.parametrize("url", ["http://example.com", "http://127.0.0.1.evil.test", "https://127.0.0.1", "http://user@127.0.0.1"])
def test_nonlocal_endpoint_rejected(url):
    with pytest.raises(ValueError):
        validate_endpoint(url)


def test_numeric_loopback_accepted():
    assert validate_endpoint("http://127.0.0.1:11434/api/generate")
    assert validate_endpoint("http://[::1]:8080/v1/chat/completions")
