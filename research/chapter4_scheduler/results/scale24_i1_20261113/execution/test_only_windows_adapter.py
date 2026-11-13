"""Test-only Windows temp-path/mode adapter; never imported by experiments."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE / 'paper'
SCRATCH = HERE / 'portable_test_scratch'
SCRATCH.mkdir(exist_ok=True)
sys.path[:0] = [str(REPO), str(REPO / 'research/chapter3_experiments')]
real_mkdir, real_mkdtemp = os.mkdir, tempfile.mkdtemp

def mkdir(path, mode=0o777, *, dir_fd=None):
    return real_mkdir(path, 0o777, dir_fd=dir_fd)

def mkdtemp(suffix=None, prefix=None, dir=None):
    if dir is None or str(dir) == '/tmp':
        dir = SCRATCH
    return real_mkdtemp(suffix=suffix, prefix=prefix, dir=dir)

os.mkdir, tempfile.mkdtemp = mkdir, mkdtemp
modules = sys.argv[1:] or [
    'research.chapter4_scheduler.blocking.tests.test_ablation',
    'research.chapter4_scheduler.blocking.tests.test_blocking_method',
    'research.chapter4_scheduler.comparison.test_comparison',
]
suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
with (HERE / 'scale24_i1_precheck.log').open('w', encoding='utf-8') as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
summary = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
           'passed': result.wasSuccessful(), 'modules': modules,
           'test_only_adapter': 'sys.path; /tmp redirected to workspace; mkdir mode 0777 for Windows restricted-token test temporary directories'}
(HERE / 'scale24_i1_precheck.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary))
if not result.wasSuccessful():
    print((HERE / 'scale24_i1_precheck.log').read_text(encoding='utf-8')[-6000:])
sys.exit(not result.wasSuccessful())
