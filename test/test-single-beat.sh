#!/bin/bash

rm -f first_single_beat.log \
	second_single_beat.log \
	third_single_beat.log

(SINGLE_BEAT_REDIS_SERVER='redis://localhost:6379/9' SINGLE_BEAT_LOG_LEVEL=debug SINGLE_BEAT_IDENTIFIER='test-beat' python ../singlebeat/beat.py sh -c 'exec python long_waiting_process.py > first_single_beat.log') &
first_pid=$!
echo $first_pid

(SINGLE_BEAT_REDIS_SERVER='redis://localhost:6379/9' SINGLE_BEAT_LOG_LEVEL=debug SINGLE_BEAT_IDENTIFIER='test-beat' python ../singlebeat/beat.py sh -c 'exec python long_waiting_process.py > second_single_beat.log') &
second_pid=$!
echo $second_pid

(SINGLE_BEAT_REDIS_SERVER='redis://localhost:6379/9' SINGLE_BEAT_LOG_LEVEL=debug SINGLE_BEAT_IDENTIFIER='test-beat' python ../singlebeat/beat.py sh -c 'exec python long_waiting_process.py > third_single_beat.log') &
third_pid=$!
echo $third_pid

sleep 20
echo "waiting"
kill $first_pid
kill $second_pid
kill $third_pid

wait $first_pid
wait $second_pid
wait $third_pid

python check_output.py
result=$?

echo "done waiting"
exit $result
