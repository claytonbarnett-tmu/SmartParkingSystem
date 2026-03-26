FROM python:3.12-slim

WORKDIR /app/FastAPI

# Install OS dependencies if needed (e.g., for psycopg2-binary)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

ENV PYTHONPATH=/app/FastAPI:/app/FastAPI/inventory_service/inventory/generated:/app/FastAPI/pricing_service/pricing/generated

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
