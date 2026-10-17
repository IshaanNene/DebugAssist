"""Fail when a compose service publishes a port on every interface (reads `docker compose config --format json`).

Everything in the dev stack listens on 127.0.0.1: Redis feeds a worker that runs its jobs, and the other services
use well-known credentials or none."""

import json
import sys

config = json.load(sys.stdin)
bad = [
    "{}:{}".format(name, port.get("published"))
    for name, service in config["services"].items()
    for port in service.get("ports", [])
    if port.get("host_ip") != "127.0.0.1"
]
sys.exit("published on every interface: {}".format(", ".join(bad)) if bad else 0)
