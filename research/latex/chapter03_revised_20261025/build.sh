#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
command -v xelatex >/dev/null 2>&1 || { echo "ERROR: XeLaTeX missing" >&2; exit 1; }
mkdir -p build
for pass in 1 2; do
  echo "XeLaTeX pass $pass/2"
  if ! xelatex -interaction=nonstopmode -halt-on-error -file-line-error \
      -jobname=chapter03_revised -output-directory=build main.tex \
      >build/chapter03_revised.compile.log 2>&1; then
    tail -n 70 build/chapter03_revised.compile.log >&2
    exit 1
  fi
done
echo "OK: build/chapter03_revised.pdf"
