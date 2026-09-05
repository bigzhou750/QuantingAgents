from app.core import isolation_metrics


def test_metrics_record_and_snapshot_are_redacted():
    isolation_metrics.reset()
    isolation_metrics.record_auth_failure("bad_password", request_id="req-1")
    isolation_metrics.record_authorization_denial("user-a", "analysis_task", request_id="req-2")
    isolation_metrics.record_unscoped_persistence("save_memory", request_id="req-3")
    isolation_metrics.record_quarantine_growth("analysis_tasks", 2)
    isolation_metrics.record_cross_user_key_hit("user:b", request_id="req-4")
    isolation_metrics.record_queue_missing_owner("task-1", request_id="req-5")

    snap = isolation_metrics.snapshot()
    assert snap["auth_failures"]["bad_password"] == 1
    assert snap["authorization_denials"][("user-a", "analysis_task")] == 1
    assert snap["unscoped_persistence"]["save_memory"] == 1
    assert snap["quarantine_growth"]["analysis_tasks"] == 2
    assert snap["cross_user_key_hits"]["user:b"] == 1
    assert snap["queue_missing_owner"]["task-1"] == 1
    assert len(snap["recent_events"]) == 6
