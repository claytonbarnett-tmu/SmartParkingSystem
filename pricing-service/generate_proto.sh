#!/usr/bin/env bash
# Generate Python gRPC stubs from proto/pricing.proto
set -euo pipefail
cd "$(dirname "$0")"

python -m grpc_tools.protoc \
  -Iproto \
  --python_out=pricing/generated \
  --grpc_python_out=pricing/generated \
  proto/pricing.proto

echo "Generated stubs in pricing/generated/"
