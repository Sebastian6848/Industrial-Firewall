#!/usr/local/bin/python3

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler

sys.path.insert(0, os.path.dirname(__file__))
from lib.decoder import MQTTDecodeError, decode_packet, split_packets


MAX_OBSERVER_BUFFER = 4 * 1024 * 1024


class JsonLogFormatter(logging.Formatter):
    def format(self, record):
        if hasattr(record, 'nclink_payload'):
            return json.dumps(record.nclink_payload, ensure_ascii=False)
        payload = {
            'event': 'service',
            'level': record.levelname.lower(),
            'message': record.getMessage(),
            'timestamp': record.created,
        }
        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class ProxyLog:
    def __init__(self, logger, handler):
        self.logger = logger
        self.handler = handler
        self.lock = asyncio.Lock()

    async def write_packet(self, packet):
        async with self.lock:
            self.logger.info('', extra={'nclink_payload': packet})

    async def info(self, message, *args):
        await self.log(logging.INFO, message, *args)

    async def error(self, message, *args, exc_info=None):
        await self.log(logging.ERROR, message, *args, exc_info=exc_info)

    async def log(self, level, message, *args, exc_info=None):
        async with self.lock:
            self.logger.log(level, message, *args, exc_info=exc_info)

    def close(self):
        self.handler.close()
        self.logger.removeHandler(self.handler)


def setup_logging(log_file):
    logger = logging.getLogger('nclink_proxy')
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8',
        )
    else:
        handler = logging.StreamHandler(sys.stdout)

    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    return logger, handler


def format_peer(peer):
    if isinstance(peer, tuple):
        if len(peer) >= 2:
            return '%s:%s' % (peer[0], peer[1])
        return ':'.join([str(item) for item in peer])
    return str(peer) if peer is not None else ''


async def forward(reader, writer, direction, peer, proxy_log):
    buffer = b''
    try:
        while True:
            data = await reader.read(65535)
            if not data:
                break
            buffer += data
            try:
                packets, buffer = split_packets(buffer)
            except MQTTDecodeError as error:
                await proxy_log.write_packet({
                    'decode_error': str(error),
                    'direction': direction,
                    'peer': peer,
                    'timestamp': time.time(),
                })
                packets = []
                buffer = b''
            for packet in decode_packets(packets):
                packet['direction'] = direction
                packet['peer'] = peer
                packet['timestamp'] = time.time()
                await proxy_log.write_packet(packet)
            if len(buffer) > MAX_OBSERVER_BUFFER:
                await proxy_log.write_packet({
                    'decode_error': 'observer buffer limit exceeded',
                    'direction': direction,
                    'peer': peer,
                    'timestamp': time.time(),
                })
                buffer = b''
            writer.write(data)
            await writer.drain()
    except Exception:
        await proxy_log.error('forward %s failed for peer %s', direction, peer, exc_info=True)
        raise


def decode_packets(packets):
    records = []
    for packet in packets:
        try:
            records.append(decode_packet(packet))
        except MQTTDecodeError as error:
            records.append({'decode_error': str(error)})
    return records


async def handle_client(client_reader, client_writer, args, proxy_log):
    client_peer = format_peer(client_writer.get_extra_info('peername'))
    await proxy_log.info('client connected from %s', client_peer)
    try:
        server_reader, server_writer = await asyncio.wait_for(
            asyncio.open_connection(args.target_host, args.target_port),
            timeout=10,
        )
    except Exception:
        await proxy_log.error(
            'connect to target %s:%s failed for client %s',
            args.target_host,
            args.target_port,
            client_peer,
            exc_info=True,
        )
        client_writer.close()
        await client_writer.wait_closed()
        return

    server_peer = format_peer(server_writer.get_extra_info('peername'))
    tasks = {
        asyncio.create_task(forward(
            client_reader,
            server_writer,
            'client-to-server',
            client_peer,
            proxy_log,
        )),
        asyncio.create_task(forward(
            server_reader,
            client_writer,
            'server-to-client',
            server_peer,
            proxy_log,
        )),
    }
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        client_writer.close()
        server_writer.close()
        await asyncio.gather(
            client_writer.wait_closed(),
            server_writer.wait_closed(),
            return_exceptions=True,
        )
        await proxy_log.info('client disconnected from %s', client_peer)


async def run(args):
    logger, handler = setup_logging(args.log_file)
    proxy_log = ProxyLog(logger, handler)
    try:
        server = await asyncio.start_server(
            lambda r, w: handle_client(r, w, args, proxy_log),
            args.listen_host,
            args.listen_port,
        )
        sockets = ', '.join([format_peer(sock.getsockname()) for sock in server.sockets or []])
        await proxy_log.info(
            'NC-Link proxy listening on %s and forwarding to %s:%s',
            sockets,
            args.target_host,
            args.target_port,
        )
        async with server:
            await server.serve_forever()
    except Exception:
        await proxy_log.error('NC-Link proxy stopped due to an error', exc_info=True)
        raise
    finally:
        proxy_log.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Transparent NC-Link MQTT observer proxy')
    parser.add_argument('--listen-host', default='127.0.0.1')
    parser.add_argument('--listen-port', default=11883, type=int)
    parser.add_argument('--target-host', required=True)
    parser.add_argument('--target-port', default=1883, type=int)
    parser.add_argument('--log-file', help='write decoded JSON lines to this file')
    asyncio.run(run(parser.parse_args()))
