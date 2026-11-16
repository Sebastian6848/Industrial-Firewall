#!/usr/local/bin/python3

import json
import sys

import log_query
from protocols import catalog
from runtime import ApplyManager, CapabilityProbe, ServiceManager, error, ok


def query_logs(args):
    old_argv = sys.argv
    try:
        sys.argv = ["log_query.py"] + args
        return_code = log_query.main()
        if return_code not in (None, 0):
            return error("log query failed")
        return None
    finally:
        sys.argv = old_argv


def main(argv):
    action = argv[1] if len(argv) > 1 else "status"
    if action in ("apply", "reload", "configure"):
        return ApplyManager().apply()
    if action == "status":
        result = ServiceManager().status()
        result['protocols'] = catalog()
        return result
    if action == "capabilities":
        return ok({"capabilities": CapabilityProbe().probe(), "protocols": catalog()})
    if action == "log":
        logged = query_logs(argv[2:])
        return logged if logged is not None else None
    return error("unsupported action")


if __name__ == "__main__":
    result = main(sys.argv)
    if result is not None:
        print(json.dumps(result, separators=(",", ":")))
        # Preserve structured failures: configd discards output for nonzero exits.
        sys.exit(0)
