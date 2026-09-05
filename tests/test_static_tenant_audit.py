from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
SCAN_DIRS = (
    PROJECT_ROOT / "app" / "routers",
    PROJECT_ROOT / "app" / "services",
    PROJECT_ROOT / "vibe_agent_runtime" / "runtime.py",
    PROJECT_ROOT / "app" / "middleware",
)

DANGEROUS_PATTERNS = (
    'user.get("username", "admin")',
    '=="admin"',
    '"id": "admin"',
    '"username": "admin"',
)


def _scan_files():
    for root in SCAN_DIRS:
        if root.is_dir():
            yield from root.rglob("*.py")
        elif root.exists():
            yield root


def test_no_hardcoded_admin_auth_identity_in_tenant_boundary():
    findings = []
    for path in _scan_files():
        text = path.read_text(encoding="utf-8")
        for pattern in DANGEROUS_PATTERNS:
            if pattern in text:
                findings.append(f"{path.relative_to(PROJECT_ROOT)} contains {pattern}")
    assert findings == [], "\n".join(findings)
