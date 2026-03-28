import json
import os
import random
import time
import pika

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
QUEUE_NAME = os.getenv("RABBITMQ_QUEUE", "sensor_events")
LOT_IDS = [int(x) for x in os.getenv("LOT_IDS", "1,2").split(",") if x.strip()]
SPOT_IDS = [int(x) for x in os.getenv("SPOT_IDS", "1,2,3,4,5").split(",") if x.strip()]
PUBLISH_INTERVAL_SECONDS = float(os.getenv("PUBLISH_INTERVAL_SECONDS", "5"))
EVENTS_PER_BATCH = int(os.getenv("EVENTS_PER_BATCH", "1"))
EVENT_COUNT = int(os.getenv("EVENT_COUNT", "0"))

STATUSES = ["occupied", "available"]

# Probability that a spot changes state on each event (default 10%)
CHANGE_PROBABILITY = float(os.getenv("CHANGE_PROBABILITY", "0.1"))

if not LOT_IDS:
    LOT_IDS = [1, 2]

if not SPOT_IDS:
    SPOT_IDS = [1, 2, 3, 4, 5]


SPOT_STATE = {}

def initialize_state():
    for lot in LOT_IDS:
        for spot in SPOT_IDS:
            SPOT_STATE[(lot, spot)] = random.choice(STATUSES)


def build_event() -> dict:
    lot = random.choice(LOT_IDS)
    spot = random.choice(SPOT_IDS)

    current_status = SPOT_STATE[(lot, spot)]

    # Decide whether to flip state
    if random.random() < CHANGE_PROBABILITY:
        new_status = "occupied" if current_status == "available" else "available"
        SPOT_STATE[(lot, spot)] = new_status
    else:
        new_status = current_status

    return {
        "lot_id": lot,
        "spot_id": spot,
        "status": new_status,
    }


def publish_event(channel, event: dict) -> None:
    body = json.dumps(event).encode("utf-8")
    channel.basic_publish(
        exchange="",
        routing_key=QUEUE_NAME,
        body=body,
        properties=pika.BasicProperties(delivery_mode=2),
    )
    print(f"[publisher] sent {event}")


def main() -> None:
    params = pika.URLParameters(RABBITMQ_URL)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    print(f"[publisher] connected to {RABBITMQ_URL}, queue={QUEUE_NAME}")
    initialize_state()
    
    sent = 0
    try:
        while EVENT_COUNT <= 0 or sent < EVENT_COUNT:
            for _ in range(EVENTS_PER_BATCH):
                event = build_event()
                publish_event(channel, event)
                sent += 1

                if EVENT_COUNT > 0 and sent >= EVENT_COUNT:
                    break

            time.sleep(PUBLISH_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("[publisher] stopping")
    finally:
        connection.close()


if __name__ == "__main__":
    main()