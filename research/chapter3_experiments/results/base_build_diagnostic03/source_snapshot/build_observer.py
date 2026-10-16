"""Construction progress only: no pruning, model changes or search guidance.

The caller owns the single method budget. Synchronous observation overhead is
inside that budget; final evidence serialization can be reported separately.
The observer retains the partial model solely to describe an interrupted
construction, never to export it as a complete optimization problem.
"""
import ctypes
import json
import os
from pathlib import Path
import sys
import time


def process_memory():
    """Current/peak resident memory of this Python process, including imports.

    Windows counters are OS lifetime high-water marks, not allocation deltas.
    MATLAB is not included; construction-only diagnostics never start it.
    """
    if os.name == 'nt':
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                        ('PeakWorkingSetSize', ctypes.c_size_t),
                        ('WorkingSetSize', ctypes.c_size_t),
                        ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                        ('QuotaPagedPoolUsage', ctypes.c_size_t),
                        ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                        ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                        ('PagefileUsage', ctypes.c_size_t),
                        ('PeakPagefileUsage', ctypes.c_size_t)]

        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE,
                                             ctypes.POINTER(Counters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),
                                         ctypes.byref(counters), counters.cb):
            return {'state': 'unavailable', 'os_error': ctypes.get_last_error()}
        return {'state': 'available', 'rss_bytes': counters.WorkingSetSize,
                'peak_rss_bytes': counters.PeakWorkingSetSize,
                'scope': 'current_python_process_lifetime_including_imports'}
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return {'state': 'available', 'rss_bytes': None,
                'peak_rss_bytes': int(peak if sys.platform == 'darwin' else peak*1024),
                'scope': 'current_python_process_lifetime_including_imports'}
    except (ImportError, OSError):
        return {'state': 'unavailable'}


class BuildObserver:
    """Callable accepted by ``build_model(..., progress=observer)``.

    ``snapshot()`` and ``finish(status)`` do not check/renew the budget, so
    already-formed progress remains reportable after an interruption.
    Optional JSONL output is flushed at phase boundaries or every second.
    """
    def __init__(self, budget, log_path=None, interval_seconds=1.0):
        if interval_seconds <= 0:
            raise ValueError('observation interval must be positive')
        self.budget = budget
        self.clock = getattr(budget, 'clock', time.monotonic)
        self.log_path = Path(log_path) if log_path else None
        self.interval_seconds = interval_seconds
        self.model = None
        self.stage = None
        self.detail = {}
        self.stage_started = self.clock()
        self.last_emit = float('-inf')
        self.stage_seconds = {}
        self.status = 'CONSTRUCTION_PENDING'
        self.observations = 0
        self.observation_wall_seconds = 0.0
        self.observation_seconds_by_stage = {}
        self.finished_at = None
        self.initial_memory = process_memory()

    def __call__(self, stage, model, detail):
        measured_start = time.perf_counter()
        try:
            if self.finished_at is not None:
                return
            now = self.clock()
            self.model = model
            changed = stage is not None and stage != self.stage
            if changed:
                if self.stage is not None:
                    self.stage_seconds[self.stage] = self.stage_seconds.get(self.stage, 0.0)+(now-self.stage_started)
                self.stage, self.stage_started = stage, now
            self.detail.update(detail)
            self.status = 'MODEL_CONSTRUCTED' if self.stage == 'complete' else 'CONSTRUCTION_IN_PROGRESS'
            if changed or now-self.last_emit >= self.interval_seconds:
                self._emit(now)
        finally:
            elapsed = time.perf_counter()-measured_start
            self.observation_wall_seconds += elapsed
            self.observation_seconds_by_stage[self.stage] = self.observation_seconds_by_stage.get(self.stage, 0.0)+elapsed

    def snapshot(self):
        now = self.finished_at if self.finished_at is not None else self.clock()
        times = dict(self.stage_seconds)
        if self.stage is not None:
            times[self.stage] = times.get(self.stage, 0.0)+now-self.stage_started
        model = self.model
        return {
            'status': self.status,
            'method_elapsed_seconds': now-self.budget.start,
            'current_stage': self.stage,
            'detail': dict(self.detail),
            'phase_wall_seconds': times,
            'options': len(model.options) if model else 0,
            'variables': len(model.names) if model else 0,
            'binary_variables': len(model.integer) if model else 0,
            'rows': len(model.rows) if model else 0,
            # Model rows are append-only; Big-M metadata does not change coef.
            # Older/fake models retain the scan fallback used by prechecks.
            'nonzeros_in_rows': (model.row_nonzeros if hasattr(model, 'row_nonzeros') else
                                 sum(len(row['coef']) for row in model.rows)) if model else 0,
            'coefficient_sets_completed': model.coefficients.calls if model else 0,
            'coefficient_state_kernels_completed': len(getattr(model.coefficients, 'kernel_cache', {})) if model else 0,
            'events_per_scene': {sid: len(scene['events']) for sid, scene in model.scenes.items()} if model else {},
            'scene_control_intervals_begun': {sid: len(scene['active']) for sid, scene in model.scenes.items()} if model else {},
            'scene_energy_variables_created': {sid: len(scene['energy']) for sid, scene in model.scenes.items()} if model else {},
            'memory': process_memory(),
            'initial_memory': self.initial_memory,
            'observations': self.observations,
            'observation_callback_wall_s': self.observation_wall_seconds,
            'observation_seconds_by_stage': dict(self.observation_seconds_by_stage),
            'construction_components': {key: dict(value) for key, value in
                                        getattr(model, 'construction_costs', {}).items()},
            'component_scope': 'disjoint timed regions; inclusive includes nested observation; unfinished calls counted on exception unwind',
            'observation_cost_scope': 'callbacks including synchronous progress logging; budget checks excluded',
            'complete_model_only_when': 'status MODEL_CONSTRUCTED and successful build_model return',
            'partial_counts_are_not_solver_ready': self.status != 'MODEL_CONSTRUCTED',
        }

    def _emit(self, now):
        self.last_emit = now
        self.observations += 1
        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(self.snapshot(), ensure_ascii=False)+'\n')

    def finish(self, status):
        self.status = status
        self.finished_at = self.clock()
        self._emit(self.finished_at)
        return self.snapshot()
