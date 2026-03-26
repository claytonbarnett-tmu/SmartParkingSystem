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
COPY seed_demo_data.py seed_demo_data.py


# Generate gRPC bindings (keeps generated code in sync with proto)
RUN python -m grpc_tools.protoc \
    -I proto \
    --python_out=inventory/generated \
    --grpc_python_out=inventory/generated \
    proto/inventory.proto

# --- DEMO/TEST ONLY: Seed demo data. Remove the next line for production! ---
RUN python seed_demo_data.py || true

ENV PYTHONPATH=/app:/app/inventory/generated:$PYTHONPATH
EXPOSE 50051

CMD ["python", "-m", "inventory.server"]
