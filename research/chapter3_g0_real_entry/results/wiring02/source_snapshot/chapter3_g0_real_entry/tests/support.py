"""Persistent, bounded workspace fixtures; no recursive temp cleanup.

Windows ephemeral-directory ACLs can prevent the test process reading its
own tempfile folders. Store every subsequent fixture with its run evidence.
"""
from pathlib import Path
import itertools
import json

_ROOT=None
_COUNTER=itertools.count(1)


def configure(root):
    global _ROOT
    root=Path(root).resolve()
    expected=Path(__file__).resolve().parents[1]/'results'
    if not root.is_relative_to(expected.resolve()):
        raise ValueError('test fixtures must stay inside the current isolated result run')
    root.mkdir(parents=True,exist_ok=False)
    _ROOT=root


class TemporaryDirectory:
    def __init__(self,suffix=None,prefix='case-',dir=None,**kwargs):
        if _ROOT is None:
            raise RuntimeError('configure an isolated fixture root before tests')
        safe=''.join(c for c in str(prefix) if c.isalnum() or c in '-_')
        folder=(_ROOT/(safe+f'{next(_COUNTER):04d}')).resolve()
        if not folder.is_relative_to(_ROOT):
            raise ValueError('fixture escapes run directory')
        folder.mkdir(exist_ok=False)
        self.name=str(folder)
        self._requested_parent=None if dir is None else str(dir)
    def __enter__(self):return self.name
    def __exit__(self,*args):self.cleanup()
    def cleanup(self):
        # Preserve files for audit. No chmod, recursive delete or retry.
        (Path(self.name)/'fixture_retained.json').write_text(json.dumps(
            {'kind':'SIMULATED_WORKSPACE_FIXTURE','retained':True,
             'requested_parent_ignored':self._requested_parent}),encoding='utf-8')
