"""观察闭环中模拟交易来源字段与复盘的兼容性测试"""

from app.routers.paper import PlaceOrderRequest, _payload_source_fields


class TestPlaceOrderSourceCompatibility:
    def test_old_request_still_valid_without_source_fields(self):
        payload = PlaceOrderRequest(code="000001", side="buy", quantity=100)

        assert payload.source_type is None
        assert payload.source_observation_id is None
        assert payload.source_strategy_id is None
        assert payload.source_task_id is None
        assert payload.source_candidate is None
        assert _payload_source_fields(payload) == {}

    def test_source_fields_preserved_in_order_and_trade_documents(self):
        payload = PlaceOrderRequest(
            code="600519",
            side="buy",
            quantity=100,
            source_type="observation",
            source_observation_id="obs_123",
            source_strategy_id="strat_abc",
            source_task_id="task_xyz",
            source_candidate={"stock_code": "600519", "match_reasons": ["ROE高"]},
        )

        fields = _payload_source_fields(payload)

        assert fields == {
            "source_type": "observation",
            "source_observation_id": "obs_123",
            "source_strategy_id": "strat_abc",
            "source_task_id": "task_xyz",
            "source_candidate": {"stock_code": "600519", "match_reasons": ["ROE高"]},
        }

    def test_source_fields_are_included_in_outgoing_doc_keys_only_once_set(self):
        payload = PlaceOrderRequest(
            code="APPL",
            side="buy",
            quantity=10,
            source_observation_id="obs_999",
        )

        fields = _payload_source_fields(payload)

        assert fields == {"source_observation_id": "obs_999"}
