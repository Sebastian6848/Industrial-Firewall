import base64
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lib import nclink


class NCLinkTests(unittest.TestCase):
    def test_topic_detection(self):
        record = {'mqtt': {'topic': 'factory/nclink/machine/status'}}
        result = nclink.enrich(record)
        self.assertTrue(result['nclink_detected'])
        self.assertEqual(result['nclink_topic'], 'factory/nclink/machine/status')
        self.assertEqual(result['nclink_markers'], 'NC-Link')

    def test_client_id_detection(self):
        record = {'mqtt': {'client_id': 'NC-Link-Gateway-01'}}
        result = nclink.enrich(record)
        self.assertTrue(result['nclink_detected'])
        self.assertEqual(result['nclink_client_id'], 'NC-Link-Gateway-01')

    def test_json_payload_detection(self):
        payload = '{"REGMSG":{"deviceId":"cnc-01"},"PRK":"main"}'
        record = {'mqtt': {'payload': payload}}
        result = nclink.enrich(record)
        self.assertTrue(result['nclink_detected'])
        self.assertEqual(result['nclink_markers'], 'REGMSG,PRK')
        self.assertEqual(result['nclink_deviceid'], 'cnc-01')
        self.assertEqual(result['nclink_prk'], 'main')

    def test_base64_payload_detection(self):
        payload = base64.b64encode(b'{"REMSG":{"machineId":"lathe-02"}}').decode('ascii')
        record = {'mqtt': {'payload_base64': payload}}
        result = nclink.enrich(record)
        self.assertTrue(result['nclink_detected'])
        self.assertEqual(result['nclink_markers'], 'REMSG')
        self.assertEqual(result['nclink_machineid'], 'lathe-02')
        self.assertEqual(result['nclink_message_types'], 'REMSG')
        self.assertEqual(result['nclink_message_class'], 'resource')
        self.assertEqual(result['nclink_machine_id'], 'lathe-02')

    def test_business_semantics_are_flattened(self):
        payload = (
            '{"SPSK":{"deviceId":"cnc-01","timestamp":"2026-06-15T10:00:00Z",'
            '"seq":7,"points":[{"name":"load","value":81,"unit":"%"}],'
            '"alarms":["overload"]}}'
        )
        record = {'mqtt': {'topic': 'factory/nclink/device/cnc-01/data', 'payload': payload}}
        result = nclink.enrich(record)
        self.assertTrue(result['nclink_detected'])
        self.assertEqual(result['nclink_message_types'], 'SPSK')
        self.assertEqual(result['nclink_message_class'], 'sample')
        self.assertEqual(result['nclink_device_id'], 'cnc-01')
        self.assertEqual(result['nclink_timestamp'], '2026-06-15T10:00:00Z')
        self.assertEqual(result['nclink_sequence'], '7')
        self.assertEqual(result['nclink_data_points'], 1)
        self.assertEqual(result['nclink_alarms'], 1)

    def test_standard_interface_topic_is_detected(self):
        record = {
            'mqtt': {
                'topic': 'Query/Request/device-1/application-1',
                'payload': '{"@id":"query-7","guid":"device-1"}',
            }
        }
        result = nclink.enrich(record)
        self.assertTrue(result['nclink_detected'])
        self.assertEqual(result['nclink_interface'], 'Query/Request')
        self.assertEqual(result['nclink_message_class'], 'data_query')
        self.assertEqual(result['nclink_device_id'], 'device-1')
        self.assertEqual(result['nclink_client_id'], 'application-1')


if __name__ == '__main__':
    unittest.main()
