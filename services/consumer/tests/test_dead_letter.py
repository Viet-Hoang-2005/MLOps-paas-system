from unittest.mock import Mock

from src.dead_letter import DeadLetter, DeadLetterQueue


def letter(offset=1):
    return DeadLetter(value=b"payload", topic="events", partition=2, offset=offset, reason="db_write_failed")


def queue_with(producer, topic="events.dlq"):
    return DeadLetterQueue("broker:9092", topic, producer_factory=lambda conf: producer)


def acknowledging_producer():
    producer = Mock()

    def produce(topic, **kwargs):
        kwargs["on_delivery"](None, Mock())

    producer.produce.side_effect = produce
    producer.flush.return_value = 0
    return producer


def test_publish_sends_identified_records_and_reports_success():
    producer = acknowledging_producer()

    assert queue_with(producer).publish([letter(1), letter(2)])

    assert producer.produce.call_count == 2
    first = producer.produce.call_args_list[0]
    assert first.args == ("events.dlq",)
    assert first.kwargs["key"] == b"events:2:1"
    assert ("x-source-offset", b"1") in first.kwargs["headers"]


def test_publish_fails_when_the_broker_does_not_acknowledge():
    producer = Mock()
    producer.flush.return_value = 1

    assert not queue_with(producer).publish([letter()])


def test_publish_fails_on_delivery_error():
    producer = Mock()
    producer.produce.side_effect = lambda topic, **kw: kw["on_delivery"](Mock(code=lambda: "UNKNOWN_TOPIC"), Mock())
    producer.flush.return_value = 0

    assert not queue_with(producer).publish([letter()])


def test_publish_fails_when_producer_raises():
    producer = Mock()
    producer.produce.side_effect = BufferError("queue full")

    assert not queue_with(producer).publish([letter()])


def test_disabled_queue_never_publishes():
    producer = Mock()
    queue = queue_with(producer, topic="")

    assert not queue.enabled
    assert not queue.publish([letter()])
    producer.produce.assert_not_called()
