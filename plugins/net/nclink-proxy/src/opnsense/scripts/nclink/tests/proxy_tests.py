import json
import logging
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from proxy import JsonLogFormatter, format_peer, setup_logging


class ProxyTests(unittest.TestCase):
    def test_peer_formatting(self):
        self.assertEqual(format_peer(('192.0.2.1', 1883)), '192.0.2.1:1883')
        self.assertEqual(format_peer(('2001:db8::1', 1883, 0, 0)), '2001:db8::1:1883')

    def test_packet_log_is_not_wrapped_as_service_event(self):
        formatter = JsonLogFormatter()
        record = logging.LogRecord('test', logging.INFO, '', 0, '', (), None)
        record.nclink_payload = {'packet_type': 'PUBLISH', 'topic': 'Register/Request'}
        self.assertEqual(json.loads(formatter.format(record))['packet_type'], 'PUBLISH')

    def test_file_logger_writes_json(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, 'nclink.log')
            logger, handler = setup_logging(filename)
            logger.info('started')
            handler.close()
            logger.removeHandler(handler)
            with open(filename, encoding='utf-8') as log_file:
                self.assertEqual(json.loads(log_file.readline())['message'], 'started')


if __name__ == '__main__':
    unittest.main()
