# Sensor Simulator

This service publishes simulated sensor events to RabbitMQ so the Inventory Service can consume them.

Each message is a JSON object like this:
```JSON
"lot_id": 1,
"spot_id": 3,
"status": "occupied"
```

Environment variables:
- `RABBITMQ_URL`: RabbitMQ connection URL (default: `amqp://guest:guest@rabbitmq:5672/`)
- `RABBITMQ_QUEUE`: queue name (default: `sensor_events`)
- `LOT_IDS`: comma-separated lot IDs to simulate (default: `1,2`)
- `SPOT_IDS`: comma-separated spot IDs to simulate (default: `1,2,3,4,5`)
- `PUBLISH_INTERVAL_SECONDS`: publish interval in seconds (default: `5`)
- `EVENTS_PER_BATCH`: number of events to publish per cycle (default: `1`)
- `EVENT_COUNT`: total number of events to publish, or `0` for infinite (default: `0`)

In Docker Compose, the service runs automatically as `sensor-simulator`.
