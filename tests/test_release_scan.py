from pathlib import Path

from scripts.validation.build_release_tree import build_release_tree
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


def test_release_scan_skips_baseline_scan_output(tmp_path: Path):
    baseline_dir = tmp_path / "docs" / "release"
    baseline_dir.mkdir(parents=True)
    (baseline_dir / "brand-migration-baseline-scan.json").write_text(
        '{"legacy_brand": "TradingAgents"}\n', encoding="utf-8"
    )

    result = scan(tmp_path)

    assert result["passed"] is True


def test_release_scan_allows_internal_package_name(tmp_path: Path):
    package_dir = tmp_path / "tradingagents"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text(
        "# tradingagents internal package\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        'name = "tradingagents"\n', encoding="utf-8"
    )

    result = scan(tmp_path)

    assert result["passed"] is True
    assert any(item["severity"] == "allowed-internal" for item in result["findings"])


def test_release_scan_rejects_real_env_secret(tmp_path: Path):
    (tmp_path / ".env.production").write_text(
        "DEEPSEEK_API_KEY=sk-0123456789abcdef0123456789abcdef\n", encoding="utf-8"
    )

    result = scan(tmp_path)

    assert result["passed"] is False
    assert any(item["category"] == "known_secret_env" for item in result["forbidden"])


def test_release_scan_ignores_python_variable_assignment(tmp_path: Path):
    (tmp_path / "config.py").write_text(
        "api_key = provider_data.get('api_key', '')\n", encoding="utf-8"
    )

    result = scan(tmp_path)

    assert result["passed"] is True


def test_build_release_tree_excludes_non_delivery_files(tmp_path: Path):
    source = tmp_path / "source"
    (source / "app").mkdir(parents=True)
    (source / "web").mkdir()
    (source / "app" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (source / "web" / "legacy.py").write_text("legacy\n", encoding="utf-8")
    (source / ".env").write_text("SECRET=abc\n", encoding="utf-8")
    (source / "README.md").write_text("# zhitouagent\n", encoding="utf-8")

    dest = tmp_path / "release"
    assert build_release_tree(source, dest) == 0

    assert (dest / "app" / "main.py").exists()
    assert not (dest / "web" / "legacy.py").exists()
    assert not (dest / ".env").exists()
    assert (dest / "README.md").exists()
