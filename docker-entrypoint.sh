#!/bin/sh
set -eu

python -m utils.docker_bootstrap

exec "$@"
