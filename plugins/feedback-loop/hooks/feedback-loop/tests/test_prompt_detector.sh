#!/usr/bin/env bash
set -euo pipefail
exec pytest -q -p no:cacheprovider "$(dirname "$0")/test_event_logger.py"
