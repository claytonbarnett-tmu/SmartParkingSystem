#!/usr/bin/env bash
# Run from the repository root:
#   ./inventory-service/generate_proto.sh

set -euo pipefail

PROTO_DIR="$(dirname "$0")/proto"
OUT_DIR="$(dirname "$0")/inventory/generated"

mkdir -p "$OUT_DIR"

python -m grpc_tools.protoc \
  -I "$PROTO_DIR" \
  --python_out="$OUT_DIR" \
  --grpc_python_out="$OUT_DIR" \
  "$PROTO_DIR"/inventory.proto
