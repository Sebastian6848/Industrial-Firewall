#!/usr/local/bin/python3

import argparse
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lib.decoder import decode_stream


def load_input(args):
    if args.hex:
        return bytes.fromhex(args.hex.replace(':', '').replace(' ', ''))
    if args.base64:
        return base64.b64decode(args.base64)
    if args.file:
        with open(args.file, 'rb') as handle:
            return handle.read()
    return sys.stdin.buffer.read()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Decode MQTT/NC-Link packets')
    parser.add_argument('--hex', help='hex encoded MQTT packet stream')
    parser.add_argument('--base64', help='base64 encoded MQTT packet stream')
    parser.add_argument('--file', help='file containing raw MQTT packet stream')
    args = parser.parse_args()

    print(json.dumps(decode_stream(load_input(args)), ensure_ascii=False))
