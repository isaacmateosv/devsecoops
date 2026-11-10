#!/usr/bin/env bash
# Compile the synthetic legacy excess-of-loss binary to a static Linux ELF.
# Source lives in evaluation-private/ (evaluation authority only); the compiled
# artifact is the ONLY thing the investigation/runner side ever sees.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/evaluation-private/legacy-source/xol_calc.c"
OUT="$ROOT/demo/artifacts/xol_calc"
TMP="$(mktemp -d)"
cp "$SRC" "$TMP/xol_calc.c"
docker run --rm --platform linux/arm64 -v "$TMP":/src -w /src gcc:14-bookworm \
  cc -O0 -static -o xol_calc xol_calc.c
mkdir -p "$ROOT/demo/artifacts"
cp "$TMP/xol_calc" "$OUT"
rm -rf "$TMP"
echo "built: $OUT"
file "$OUT"
