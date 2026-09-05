from app.core.auth_guard import AuthAttemptGuard


def test_auth_guard_limits_each_identity_without_cross_account_lockout():
    guard = AuthAttemptGuard(limit=2, window_seconds=60)
    assert guard.allow("ip:a", "account:a")
    assert guard.allow("ip:a", "account:a")
    assert not guard.allow("ip:a", "account:a")
    assert guard.allow("ip:b", "account:b")
