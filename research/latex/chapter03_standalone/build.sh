#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v xelatex >/dev/null 2>&1; then
  echo "ERROR: XeLaTeX is not installed or not in PATH" >&2
  exit 1
fi
mkdir -p build
for pass in 1 2; do
  echo "Running XeLaTeX pass $pass of 2..."
  if ! xelatex -interaction=nonstopmode -halt-on-error -file-line-error \
       -jobname=chapter03_preview -output-directory=build main.tex \
       > build/chapter03_preview.compile.log 2>&1; then
    tail -n 70 build/chapter03_preview.compile.log >&2
    exit 1
  fi
done
echo "OK: build/chapter03_preview.pdf"
