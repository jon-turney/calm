#!/usr/bin/env bash
export PYTHONPATH=$(dirname "$0")
exec python3 -m calm.$1 "${@:2}"
