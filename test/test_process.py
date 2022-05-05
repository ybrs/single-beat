import subprocess
import unittest
import time
import psutil
import os

import signal


class TestStringMethods(unittest.TestCase):

    def setup_processes(self, cmd="single-beat python echo.py", cnt=3):
        self.processes = [
            subprocess.Popen(cmd, shell=True)
            for i in range(0, cnt)
        ]

    def get_all_children(self):
        children = []
        for p in self.processes:
            try:
                parent = psutil.Process(p.pid)
            except psutil.NoSuchProcess:
                continue
            children += parent.children(recursive=True)
        return children

    def get_active_subprocess(self):
        for p in self.processes:
            try:
                parent = psutil.Process(p.pid)
            except psutil.NoSuchProcess:
                continue
            if parent.children(recursive=True):
                return p

    def wait_and_try_again(self, fn, max_seconds=5):
        cnt = 0
        while cnt < max_seconds:
            result = fn()
            if result:
                return result
            time.sleep(1)
            cnt += 1
        raise Exception(f"Couldn't complete {fn} in a timely fashion")

    def test_single_instance(self):
        """
        only one instance of the child should be running
        """
        self.setup_processes()
        # check we only one echo.py running
        children = self.wait_and_try_again(self.get_all_children, 5)
        self.assertEqual(len(children), 1, "we have more than one child")
        # send kill to the child, see if someone else spawns
        os.kill(children[0].pid, signal.SIGTERM)
        new_children = self.wait_and_try_again(self.get_all_children, 30)
        self.assertGreater(len(children), 0, "couldn't spawn new child in 30 seconds")
        self.assertEqual(len(children), 1, "we have more than one child")
        self.assertNotEqual(
            children[0].pid,
            new_children[0].pid,
            "couldn't kill child - pid should've changed",
        )

    def test_exit_code(self):
        self.setup_processes("single-beat python echo-exit-code.py", cnt=1)
        # check we only one echo.py running
        children = self.wait_and_try_again(self.get_all_children, 5)
        self.assertEqual(len(children), 1, "we have more than one child")
        sp = self.get_active_subprocess()
        exit_code = self.wait_and_try_again(lambda: sp.poll(), 5)
        self.assertEqual(exit_code, 3)

    def tearDown(self):
        for p in self.processes:
            try:
                p.terminate()
                p.wait(10)
            except Exception as e:
                import traceback

                traceback.print_exc()


if __name__ == "__main__":
    unittest.main()
