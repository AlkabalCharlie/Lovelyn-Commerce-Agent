import pytest

from core.exceptions import SSRFError
from services.url_safety import check_url_safety


def test_blocks_localhost():
    with pytest.raises(SSRFError):
        check_url_safety("http://localhost:8501")


def test_blocks_loopback_ip():
    with pytest.raises(SSRFError):
        check_url_safety("http://127.0.0.1/admin")


def test_blocks_private_ip():
    with pytest.raises(SSRFError):
        check_url_safety("http://192.168.1.10/secret")


def test_blocks_cloud_metadata_ip():
    with pytest.raises(SSRFError):
        check_url_safety("http://169.254.169.254/latest/meta-data/")


def test_blocks_non_http_scheme():
    with pytest.raises(SSRFError):
        check_url_safety("ftp://example.com/file")


def test_accepts_public_https():
    assert check_url_safety("https://example.com/product") == "example.com"