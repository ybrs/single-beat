import json
import os
import subprocess
import sys
import time
import unittest
import uuid

import redis


class CLIIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.identifier = 'test-' + uuid.uuid4().hex
        self.env = os.environ.copy()
        self.env.update(SINGLE_BEAT_IDENTIFIER=self.identifier,
                        SINGLE_BEAT_HEARTBEAT_INTERVAL='1',
                        SINGLE_BEAT_LOCK_TIME='3',
                        SINGLE_BEAT_INITIAL_LOCK_TIME='4')
        self.redis = redis.Redis.from_url(self.env.get('SINGLE_BEAT_REDIS_SERVER', 'redis://localhost:6379/9'))
        self.nodes = []
        self.start_node()
        self.wait_for(lambda: self.redis.pubsub_numsub('SB_' + self.identifier)[0][1] == 1)
        self.wait_for(lambda: 'RUNNING' in self.cli('info'))

    def tearDown(self):
        for node in self.nodes:
            if node.poll() is None:
                node.terminate()
                try:
                    node.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    node.kill()
                    node.wait()
        self.redis.delete('SINGLE_BEAT_' + self.identifier)
        self.redis.close()

    def start_node(self):
        node = subprocess.Popen([sys.executable, '-m', 'singlebeat.beat', sys.executable,
                                 '-c', 'import time; time.sleep(120)'],
                                env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.nodes.append(node)

    def cli(self, command):
        result = subprocess.run([sys.executable, '-m', 'singlebeat.cli', command],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def wait_for(self, condition, timeout=12):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = condition()
            if result:
                return result
            time.sleep(.1)
        self.fail('condition did not become true')

    def running_pid(self):
        output = self.cli('info')
        if 'RUNNING' not in output or 'pid: ' not in output:
            return None
        return int(output.split('pid: ')[1].split()[0])

    def test_info_pause_resume_stop_restart_and_quit(self):
        first_pid = self.wait_for(self.running_pid)
        self.assertIn('killed', self.cli('restart'))
        second_pid = self.wait_for(lambda: (pid := self.running_pid()) and pid != first_pid and pid)
        self.assertIn('killed', self.cli('pause'))
        self.wait_for(lambda: 'PAUSED' in self.cli('info'))
        self.cli('resume')
        third_pid = self.wait_for(lambda: (pid := self.running_pid()) and pid != second_pid and pid)
        self.assertIn('killed', self.cli('stop'))
        self.wait_for(lambda: (pid := self.running_pid()) and pid != third_pid and pid)
        self.cli('quit')
        self.assertEqual(self.nodes[0].wait(timeout=5), 0)

    def test_commands_reach_all_nodes(self):
        self.start_node()
        self.wait_for(lambda: self.redis.pubsub_numsub('SB_' + self.identifier)[0][1] == 2)
        output = self.cli('info')
        self.assertEqual(len(output.strip().splitlines()), 2)
        self.assertEqual(output.count('RUNNING'), 1)
        self.assertEqual(output.count('WAITING'), 1)
        self.cli('pause')
        self.wait_for(lambda: self.cli('info').count('PAUSED') == 2)
        self.cli('resume')
        self.wait_for(lambda: self.cli('info').count('RUNNING') == 1)
        self.cli('quit')
        for node in self.nodes:
            self.assertEqual(node.wait(timeout=5), 0)

    def test_malformed_command_does_not_stop_listener(self):
        self.redis.publish('SB_' + self.identifier, json.dumps({}))
        self.wait_for(lambda: 'RUNNING' in self.cli('info'))


if __name__ == '__main__':
    unittest.main()
