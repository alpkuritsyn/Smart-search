#!/usr/bin/env python3
"""
Serve the Smart-search V1 Web Demo and API.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import os
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

os.environ["SMART_SEARCH_ENTITY_RESOLVER_MODE"] = "apply"
os.environ["SMART_SEARCH_ENTITY_RESOLVER_POLICY"] = "top1"

from src.backend.app import run_server

def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the Smart-search V1 Web Demo & API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()

    run_server(host=args.host, port=args.port)

if __name__ == "__main__":
    main()
