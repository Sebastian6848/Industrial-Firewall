import re
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from generators import nclink
from nclink_semantics import classify_topic, payload_audit

class CompatibilityTest(unittest.TestCase):
    def rule(self, **changes):
        return dict(nclink_operations='sample,state_notify,discovery', nclink_direction='both',
                    nclink_topic_root='factory/nclink', _active=True, action='pass',
                    src_ip='any', dst_ip='any', dst_port='1883', **changes)

    def test_explicit_topic_root_and_notifications(self):
        patterns = nclink.patterns(self.rule())
        for topic in ['Sample/dev/c0','Notify/State/dev','Discovery/Request/client','Discovery/Response/client']:
            self.assertTrue(any(re.fullmatch(p[3], 'factory/nclink/'+topic) for p in patterns))
            self.assertFalse(any(re.fullmatch(p[3], topic) for p in patterns))
        self.assertEqual(classify_topic('factory/nclink/Notify/State/dev'), {})
        result=classify_topic('factory/nclink/Notify/State/dev',['factory/nclink'])
        self.assertEqual(result['nclink_operation'],'state_notify')
        self.assertEqual(result['nclink_device_uuid'],'dev')

    def test_root_is_literal_and_never_arbitrary_namespace(self):
        pattern=nclink.patterns(self.rule(nclink_device_uuid='dev'))[0][3]
        self.assertFalse(re.fullmatch(pattern,'other/Sample/dev/c0'))
        for root in ['a/#','/a','a/','a//b','a\x00b','a,b','a/+', 'x'*256]:
            with self.subTest(root=root), self.assertRaises(ValueError): nclink.topic_root(root)

    def test_wildcard_subscribe_is_separate_explicit_permission(self):
        rule=self.rule(nclink_packets='both',nclink_subscribe_filters='Probe/#,Sample/+/#')
        rendered=nclink.generate_policy([rule],2000000,'block')
        subscriptions=[x for x in rendered if 'EXPLICIT SUBSCRIPTION' in x]
        self.assertEqual(len(subscriptions),2)
        self.assertTrue(all('mqtt.type:SUBSCRIBE' in x for x in subscriptions))
        self.assertFalse(any('EXPLICIT SUBSCRIPTION' in x and 'mqtt.type:PUBLISH' in x for x in rendered))
        denies=[x for x in rendered if 'default block unapproved' in x]
        for packet in ['PUBLISH','SUBSCRIBE']:
            line=next(x for x in denies if 'mqtt.type:'+packet in x)
            regex=re.search(r'pcre:"/(.*)/s"',line).group(1).replace(r'\/', '/')
            self.assertEqual(bool(re.fullmatch(regex,'factory/nclink/Probe/#')),packet=='PUBLISH')

    def test_wildcard_cannot_override_device_condition(self):
        for key in ['nclink_device_uuid','nclink_endpoint']:
            with self.assertRaises(ValueError):
                nclink.subscription_patterns(self.rule(nclink_subscribe_filters='Probe/#',**{key:'dev'}))
        for bad in ['a#','a/#/b','$share/g/Probe/#','a/+b','a//b']:
            with self.assertRaises(ValueError): nclink.subscription_patterns(self.rule(nclink_subscribe_filters=bad))

    def test_payload_fields_are_contextual_and_do_not_export_values(self):
        result=payload_audit({'@id':'req1','guid':'dev','id':'c0','beginTime':'2026-11-15T00:00:00Z',
                              'values':[{'id':'speed','params':{'operation':'set_value','value':123}}]})
        self.assertEqual(result['nclink_request_id'],'req1')
        self.assertEqual(result['nclink_payload_device_uuid'],'dev')
        self.assertEqual(result['nclink_channel_id'],'c0')
        self.assertEqual(result['nclink_object_id'],'speed')
        self.assertNotIn('123',str(result))

    def test_legacy_defaults_do_not_implicitly_authorize_new_operations(self):
        self.assertNotIn('state_notify',nclink.operations({}))
        self.assertNotIn('discovery',nclink.operations({}))

if __name__=='__main__': unittest.main()
