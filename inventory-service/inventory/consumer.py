import json
import pika

from inventory import service

def _on_message(channel, method, properties, body):
    try:
        payload = json.loads(body)
        lot_id = int(payload["lot_id"])
        spot_id = int(payload["spot_id"])
        status = payload["status"]

        service.update_spot_status(lot_id=lot_id, spot_id=spot_id, new_status=status)
        channel.basic_ack(method.delivery_tag)
    except Exception as exc:
        channel.basic_nack(method.delivery_tag, requeue=False)


def run(
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/",
    queue_name: str = "sensor_events",
):
    params = pika.URLParameters(rabbitmq_url)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)
    channel.basic_consume(queue=queue_name, on_message_callback=_on_message)
    
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == "__main__":
    run()
