import pytest

from models.product import Product, ProductValidationError, validate_product_url


def test_accepts_https_url():
    assert validate_product_url(" https://example.com/p?x=1 ") == "https://example.com/p?x=1"


def test_rejects_non_http_scheme():
    with pytest.raises(ProductValidationError):
        validate_product_url("ftp://example.com/file")


def test_rejects_javascript_scheme():
    with pytest.raises(ProductValidationError):
        validate_product_url("javascript:alert(1)")


def test_rejects_missing_domain():
    with pytest.raises(ProductValidationError):
        validate_product_url("https://")


def test_product_defaults_and_normalisation():
    product = Product(url="https://example.com/p", name="   ", revenue_model="affiliate")
    assert product.name == "Unnamed product"
    assert product.status == "new"


def test_product_rejects_invalid_model():
    with pytest.raises(ProductValidationError):
        Product(url="https://example.com/p", name="x", revenue_model="magic")