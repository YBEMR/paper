import unittest
from types import SimpleNamespace
from process_monitor import monitor_owned,terminate_owned_tree

class ProcessTests(unittest.TestCase):
    def test_watchdog_does_not_signal_reused_root_pid(self):
        class Gone(Exception):pass
        p=SimpleNamespace(create_time=lambda:2.)
        module=SimpleNamespace(NoSuchProcess=Gone,Process=lambda pid:p)
        result=terminate_owned_tree(module,123,1.)
        self.assertEqual(result['reason'],'ROOT_PID_REUSED_NO_SIGNAL_SENT')
    def test_controller_tracks_and_cleans_owned_survivor(self):
        now=[0.];killed=[]
        class Gone(Exception):pass
        class P:
            def __init__(self,pid):self.pid=pid
            def create_time(self):return float(self.pid)
            def is_running(self):return self.pid==2 and self.pid not in killed
            def children(self,recursive=True):return [P(2)]
            def kill(self):killed.append(self.pid)
        class Worker:
            pid=1;returncode=None
            def poll(self):
                if now[0]>=.25:self.returncode=1
                return self.returncode
        m=SimpleNamespace(NoSuchProcess=Gone,Process=P,wait_procs=lambda ps,timeout:(ps,[]))
        result=monitor_owned(Worker(),1.,0.,m,clock=lambda:now[0],sleep=lambda s:now.__setitem__(0,now[0]+s))
        self.assertEqual(killed,[2]);self.assertEqual(result['returncode'],1)
        self.assertTrue(result['complete']);self.assertEqual(result['forced_pids'],[2])
    def test_controller_watchdog_ends_stuck_worker(self):
        now=[679.9];killed=[]
        class Gone(Exception):pass
        class P:
            def __init__(self,pid):self.pid=pid
            def create_time(self):return 1.
            def is_running(self):return not killed
            def children(self,recursive=True):return []
            def kill(self):killed.append(self.pid)
        class Worker:
            pid=1;returncode=None
            def poll(self):
                if killed:self.returncode=-9
                return self.returncode
        m=SimpleNamespace(NoSuchProcess=Gone,Process=P,wait_procs=lambda ps,timeout:(ps,[]))
        result=monitor_owned(Worker(),1.,0.,m,clock=lambda:now[0],sleep=lambda s:now.__setitem__(0,now[0]+s))
        self.assertTrue(result['watchdog_expired']);self.assertEqual(killed,[1])


