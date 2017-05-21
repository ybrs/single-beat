import subprocess
import unittest
import time
import psutil
import os

import signal


class TestStringMethods(unittest.TestCase):

    def setUp(self):
        self.processes = [
            subprocess.Popen("single-beat python echo.py", shell=True)
            for i in range(0, 3)
        ]

    def get_all_children(self):
        children = []
        for p in self.processes:
            try:
                parent = psutil.Process(p.pid)
            except psutil.NoSuchProcess:
                return
            children += parent.children(recursive=True)
        return children

    def test_single_instance(self):
        time.sleep(5)
        # check we only one echo.py running
        children = self.get_all_children()
        self.assertEqual(len(children), 1, "we have more than one child")
        # send kill to the child, see if someone else spawns
        os.kill(children[0].pid, signal.SIGTERM)
        time.sleep(5)
        new_children = self.get_all_children()
        self.assertEqual(len(children), 1, "we have more than one child")
        self.assertNotEqual(children[0].pid, new_children[0].pid,
                            "couldn't kill child - pid should've changed")

    def tearDown(self):
        for p in self.processes:
            try:
                p.terminate()
            except Exception as e:
                import traceback
                traceback.print_exc()

if __name__ == '__main__':
    unittest.main()