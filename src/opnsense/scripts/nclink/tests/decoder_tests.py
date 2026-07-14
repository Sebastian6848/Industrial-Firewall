import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lib.decoder import MQTTDecodeError, decode_packet, decode_stream, split_packets


def mqtt_string(value):
    data = value.encode()
    return len(data).to_bytes(2, 'big') + data


def mqtt_packet(packet_type, flags, body):
    remaining = len(body)
    encoded = bytearray()
    while True:
        digit = remaining % 128
        remaining //= 128
        if remaining > 0:
            digit |= 128
        encoded.append(digit)
        if remaining == 0:
            break
    return bytes([(packet_type << 4) | flags]) + bytes(encoded) + body


class DecoderTests(unittest.TestCase):
    def test_connect_client_id(self):
        body = mqtt_string('MQTT') + bytes([4, 2]) + (60).to_bytes(2, 'big') + mqtt_string('NC-Link-GW')
        record = decode_packet(mqtt_packet(1, 0, body))
        self.assertEqual(record['packet_type'], 'CONNECT')
        self.assertEqual(record['client_id'], 'NC-Link-GW')
        self.assertTrue(record['nclink_detected'])

    def test_publish_payload(self):
        payload = json.dumps({'REGMSG': {'deviceId': 'cnc-01'}, 'PRK': 'axis'})
        body = mqtt_string('factory/nclink/status') + payload.encode()
        record = decode_packet(mqtt_packet(3, 0, body))
        self.assertEqual(record['packet_type'], 'PUBLISH')
        self.assertEqual(record['topic'], 'factory/nclink/status')
        self.assertEqual(record['nclink']['deviceid'], 'cnc-01')
        self.assertEqual(record['nclink']['prk'], 'axis')
        self.assertEqual(record['nclink_semantics']['message_types'], ['REGMSG', 'PRK'])
        self.assertEqual(record['nclink_semantics']['message_class'], 'registration')
        self.assertEqual(record['nclink_semantics']['identities']['device_id'], 'cnc-01')

    def test_publish_business_semantics(self):
        payload = json.dumps({
            'SPSK': {
                'machineId': 'lathe-02',
                'timestamp': '2026-06-15T10:00:00Z',
                'seq': 42,
                'points': [
                    {'name': 'spindle_speed', 'value': 1200, 'unit': 'rpm', 'quality': 'good'},
                    {'tag': 'feed_rate', 'val': 320, 'unit': 'mm/min'},
                ],
                'alarms': [{'code': 'A01', 'message': 'door open'}],
            }
        })
        body = mqtt_string('factory/nclink/machine/lathe-02/data') + payload.encode()
        record = decode_packet(mqtt_packet(3, 0, body))
        semantics = record['nclink_semantics']
        self.assertEqual(semantics['message_types'], ['SPSK'])
        self.assertEqual(semantics['message_class'], 'sample')
        self.assertEqual(semantics['identities']['machine_id'], 'lathe-02')
        self.assertEqual(semantics['timestamp'], '2026-06-15T10:00:00Z')
        self.assertEqual(semantics['sequence'], '42')
        self.assertEqual(len(semantics['data_points']), 2)
        self.assertEqual(len(semantics['alarms']), 1)

    def test_subscribe_topics(self):
        body = (7).to_bytes(2, 'big') + mqtt_string('factory/nclink/#') + bytes([0])
        record = decode_packet(mqtt_packet(8, 2, body))
        self.assertEqual(record['packet_type'], 'SUBSCRIBE')
        self.assertEqual(record['topics'][0]['topic'], 'factory/nclink/#')
        self.assertTrue(record['nclink_detected'])

    def test_subscribe_standard_interface_topic(self):
        body = (8).to_bytes(2, 'big') + mqtt_string('Event/device-1/application-1') + bytes([0])
        record = decode_packet(mqtt_packet(8, 2, body))
        self.assertTrue(record['nclink_detected'])
        self.assertEqual(record['nclink_semantics']['message_class'], 'event')

    def test_standard_register_topic_semantics(self):
        payload = json.dumps({'@id': 'message-1', 'cli_uuid': 'adapter-1'})
        body = mqtt_string('Register/Request') + payload.encode()
        record = decode_packet(mqtt_packet(3, 0, body))
        semantics = record['nclink_semantics']
        self.assertTrue(record['nclink_detected'])
        self.assertEqual(semantics['interface']['family'], 'registration')
        self.assertEqual(semantics['interface']['operation'], 'request')
        self.assertEqual(semantics['identities']['client_id'], 'adapter-1')
        self.assertEqual(semantics['sequence'], 'message-1')

    def test_standard_sample_topic_semantics(self):
        payload = json.dumps({'value': 42, 'timestamp': '2026-07-14T10:00:00Z'})
        body = mqtt_string('Sample/device-1/client-1/channel-7') + payload.encode()
        record = decode_packet(mqtt_packet(3, 0, body))
        semantics = record['nclink_semantics']
        self.assertEqual(semantics['message_class'], 'sample')
        self.assertEqual(semantics['identities']['device_id'], 'device-1')
        self.assertEqual(semantics['identities']['client_id'], 'client-1')
        self.assertEqual(semantics['identities']['sample_channel_id'], 'channel-7')

    def test_non_nclink_topic_is_not_marked(self):
        body = mqtt_string('ordinary/mqtt/topic') + b'{"temperature":21}'
        record = decode_packet(mqtt_packet(3, 0, body))
        self.assertNotIn('nclink_detected', record)

    def test_rejects_truncated_direct_packet(self):
        packet = mqtt_packet(3, 0, mqtt_string('Register/Request') + b'{}')
        with self.assertRaises(MQTTDecodeError):
            decode_packet(packet[:-1])

    def test_generic_nested_query_topic_is_not_marked(self):
        body = mqtt_string('ordinary/application/query/request') + b'{}'
        record = decode_packet(mqtt_packet(3, 0, body))
        self.assertNotIn('nclink_detected', record)

    def test_stream(self):
        stream = mqtt_packet(12, 0, b'') + mqtt_packet(14, 0, b'')
        self.assertEqual([item['packet_type'] for item in decode_stream(stream)], ['PINGREQ', 'DISCONNECT'])

    def test_split_packets_keeps_partial_remainder(self):
        packet = mqtt_packet(3, 0, mqtt_string('factory/nclink/status') + b'REGMSG')
        packets, remainder = split_packets(packet[:-2])
        self.assertEqual(packets, [])
        self.assertEqual(remainder, packet[:-2])
        packets, remainder = split_packets(remainder + packet[-2:])
        self.assertEqual(len(packets), 1)
        self.assertEqual(remainder, b'')


if __name__ == '__main__':
    unittest.main()
