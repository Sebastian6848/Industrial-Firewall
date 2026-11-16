import sys
import unittest
from argparse import Namespace
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import log_query
from nclink_semantics import classify_topic, payload_audit


class NCLinkSemanticsTest(unittest.TestCase):
    def test_standard_request_topic(self):
        result = classify_topic("Set/Request/machine-01")
        self.assertEqual(result["nclink_operation"], "data_set")
        self.assertEqual(result["nclink_direction"], "request")
        self.assertEqual(result["nclink_device_uuid"], "machine-01")

    def test_longer_sample_registration_precedes_sample(self):
        result = classify_topic("Register/Sample/Request/machine-01")
        self.assertEqual(result["nclink_operation"], "sample_register")

    def test_unknown_or_nested_device_topic_is_not_claimed(self):
        self.assertEqual(classify_topic("vendor/custom/machine-01"), {})
        self.assertEqual(classify_topic("Set/Request/group/machine-01/extra"), {})

    def test_safe_payload_audit_fields(self):
        result = payload_audit({
            "requestId": "req-1",
            "operation": "set_value",
            "body": {"objectId": "spindle-speed", "value": 1200},
        })
        self.assertEqual(result["nclink_request_id"], "req-1")
        self.assertEqual(result["nclink_pdu_operation"], "set_value")
        self.assertEqual(result["nclink_object_id"], "spindle-speed")
        self.assertNotIn("value", result)

    def test_eve_alert_is_normalized_as_nclink_not_generic_mqtt(self):
        result = log_query.normalize({
            "timestamp": "2026-07-11T10:00:00+08:00",
            "event_type": "alert",
            "app_proto": "mqtt",
            "alert": {
                "signature": "IndProto test BLOCK NC-LINK DATA_SET",
                "action": "blocked",
            },
            "mqtt": {
                "publish": {
                    "topic": "Set/Request/machine-01",
                    "message": '{"requestId":"req-2","operation":"set_value"}',
                }
            },
        })
        self.assertEqual(result["proto"], "nclink")
        self.assertEqual(result["nclink_operation"], "data_set")
        self.assertEqual(result["nclink_device_uuid"], "machine-01")
        self.assertEqual(result["nclink_request_id"], "req-2")
        self.assertEqual(result["action"], "drop")

    def test_signature_fallback_works_without_eve_mqtt_metadata(self):
        result = log_query.normalize({
            "app_proto": "mqtt",
            "alert": {"signature": "IndProto x BLOCK NC-LINK MODEL_QUERY"},
        })
        self.assertEqual(result["proto"], "nclink")
        self.assertEqual(result["nclink_operation"], "model_query")

    def test_pass_audit_signature_overrides_eve_alert_action(self):
        result = log_query.normalize({
            "event_type": "alert",
            "alert": {
                "signature": "IndProto x PASS AUDIT NC-LINK DATA_QUERY",
                "action": "allowed",
            },
        })
        self.assertEqual(result["action"], "pass")

    def test_block_signature_is_visible_when_eve_action_is_missing(self):
        result = log_query.normalize({
            "event_type": "alert",
            "alert": {"signature": "IndProto x BLOCK NC-LINK DATA_SET"},
        })
        self.assertEqual(result["action"], "drop")

    def test_log_only_remains_alert(self):
        result = log_query.normalize({
            "event_type": "alert",
            "alert": {
                "signature": "IndProto x [LOG_ONLY] BLOCK NC-LINK DATA_SET",
                "action": "blocked",
            },
        })
        self.assertEqual(result["action"], "alert")

    def test_nclink_filter_uses_product_protocol_before_mqtt_transport(self):
        row = {
            "event_type": "alert",
            "app_proto": "mqtt",
            "alert": {
                "signature": "IndProto x BLOCK NC-LINK DATA_SET",
                "action": "blocked",
            },
        }
        args = Namespace(proto="nclink", src_ip="-", dst_ip="-")
        self.assertTrue(log_query.match(row, args, None, None))
        args.proto = "mqtt"
        self.assertFalse(log_query.match(row, args, None, None))


if __name__ == "__main__":
    unittest.main()
