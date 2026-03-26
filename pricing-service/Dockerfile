FROM python:3.12-slim

# Ensure generated modules are importable
ENV PYTHONPATH=/app/pricing/generated:$PYTHONPATH

WORKDIR /app

# Install OS-level dependencies for psycopg2-binary
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Copy source code and proto
COPY pricing/ pricing/
COPY proto/ proto/

# Generate gRPC bindings (keeps generated code in sync with proto)
RUN python -m grpc_tools.protoc \
    -I proto \
    --python_out=pricing/generated \
    --grpc_python_out=pricing/generated \
    proto/pricing.proto

EXPOSE 50052

CMD ["python", "-m", "pricing.server"]
