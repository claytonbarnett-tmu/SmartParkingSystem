FROM python:3.12-slim

WORKDIR /app

# Install OS dependencies needed by psycopg2-binary (Postgres client libs)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy dependency definition and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY inventory/ inventory/
COPY proto/ proto/

# Generate gRPC bindings (keeps generated code in sync with proto)
RUN python -m grpc_tools.protoc \
    -I proto \
    --python_out=inventory/generated \
    --grpc_python_out=inventory/generated \
    proto/inventory.proto

EXPOSE 8000

CMD ["python", "-m", "inventory.api"]
