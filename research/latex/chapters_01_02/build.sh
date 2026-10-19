#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
command -v xelatex >/dev/null || { echo "请先安装 XeLaTeX (TeX Live/MacTeX)。" >&2; exit 1; }
mkdir -p build
compile() {
    local input="$1" name="$2" pass
    for pass in 1 2; do
        xelatex -interaction=nonstopmode -halt-on-error -file-line-error \
            -jobname="$name" -output-directory=build "$input.tex" \
            > "build/$name.compile.log" 2>&1 || {
            tail -n 40 "build/$name.compile.log" >&2
            exit 1
        }
    done
    echo "已生成：build/$name.pdf"
}
mode=all
if [ "$#" -gt 0 ]; then mode="$1"; fi
case "$mode" in
    all)
        compile main chapters_01_02_preview
        compile chapter01_only chapter01_preview
        compile chapter02_only chapter02_preview ;;
    combined) compile main chapters_01_02_preview ;;
    chapter01) compile chapter01_only chapter01_preview ;;
    chapter02) compile chapter02_only chapter02_preview ;;
    *) echo "用法：bash build.sh [all|combined|chapter01|chapter02]" >&2; exit 2 ;;
esac
