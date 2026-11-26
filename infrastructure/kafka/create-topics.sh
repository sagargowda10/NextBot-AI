#!/bin/sh
# Creates the NextBot topics and their dead-letter twins. Idempotent.
set -e
BS=${BOOTSTRAP:-kafka:9092}
PREFIX=${PREFIX:-nextbot}
for t in orders payments inventory shipments returns notifications; do
  for name in "$PREFIX.$t" "$PREFIX.$t.dlq"; do
    /opt/kafka/bin/kafka-topics.sh --bootstrap-server "$BS" --create --if-not-exists --topic "$name" \
      --partitions 3 --replication-factor 1 --config retention.ms=604800000
  done
done
/opt/kafka/bin/kafka-topics.sh --bootstrap-server "$BS" --list
