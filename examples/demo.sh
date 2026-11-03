#!/usr/bin/env sh
# Builds a throwaway database with a made-up car and shows what wrenchlog reports.
# Run from the project folder:  sh examples/demo.sh
set -e
demo_dir=$(mktemp -d "${TMPDIR:-/tmp}/wrenchlog-demo.XXXXXX")
trap 'rm -f "$DB"; rmdir "$demo_dir"' EXIT
DB="$demo_dir/wrenchlog.db"
w() { python -m wrenchlog --db "$DB" --today 2026-11-03 "$@"; }

w add-car civic --make Honda --model Civic --year 2018
w odometer 61000 --date 2026-01-10
w log oil-change       --date 2026-05-01 --odometer 70500 --cost 79.99
w log tire-rotation    --date 2026-05-01 --odometer 70500 --cost 30
w log brake-inspection --date 2025-12-15 --odometer 60000
w log wiper-blades     --date 2025-10-20 --cost 34.50 --note "both fronts"
w odometer 78900
echo
w due
echo
w costs
