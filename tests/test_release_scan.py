from pathlib import Path

from scripts.validation.release_scan import scan


def test_release_scan_rejects_legacy_product_identity(tmp_path: Path):
    (tmp_path / "app.py").write_text("name = 'TradingAgents-CN'\n", encoding="utf-8")

    result = scan(tmp_path)

    assert result["passed"] is False
    assert any(item["category"] == "legacy_brand" for item in result["forbidden"])


def test_release_scan_allows_required_license_attribution(tmp_path: Path):
    (tmp_path / "LICENSE").write_text(
        "Copyright TradingAgents contributors\n", encoding="utf-8"
    )

    result = scan(tmp_path)

    assert result["passed"] is True
    assert result["findings"][0]["severity"] == "allowed-license"


def test_release_scan_rejects_secret_like_values(tmp_path: Path):
    (tmp_path / "config.toml").write_text(
        "api_key = '0123456789abcdef'\n", encoding="utf-8"
    )

    result = scan(tmp_path)

    assert result["passed"] is False
    assert any(item["category"] == "secret_like_value" for item in result["forbidden"])
