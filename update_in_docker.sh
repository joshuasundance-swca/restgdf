#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

cd /home/appuser/restgdf

coverage run
coverage report -m --format=markdown > COVERAGE.md
coverage html
coverage-badge -fo coverage.svg

cd /home/appuser/restgdf/docs

make clean html

exit 0
