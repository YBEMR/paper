"""Observed-process memory sampling and fail-closed resource checks.

Importing this module neither loads psutil nor probes/kills processes. The
supervisor explicitly creates a monitor after spawning its own worker. A PID is
never an ownership proof without its process creation time. Observed-tree
cleanup is only one input to isolation checks, not OS process containment.
"""
import math
import os
from pathlib import Path
import time

GIB = 1024 ** 3


def _identity(info):
    pid = info.get('pid')
    stamps = [info[k] for k in ('create_time', 'creation_time', 'created_at') if k in info]
    if not stamps or any(x != stamps[0] for x in stamps[1:]):
        return None
    born = stamps[0]
    if (type(pid) is not int or pid <= 0 or type(born) not in (int, float)
            or not math.isfinite(born) or born < 0):
        return None
    return pid, born


class PsutilProvider:
    """Lazy OS adapter. Tests inject a data-only provider instead."""
    def __init__(self):
        self._module = None
        self._import_error = None

    def _psutil(self):
        if self._module is None and self._import_error is None:
            try:
                import psutil
                self._module = psutil
            except ImportError as error:
                self._import_error = type(error).__name__ + ': ' + str(error)
        return self._module

    def describe(self, pid):
        psutil = self._psutil()
        if psutil is None:
            return {'pid': pid, 'state': 'UNKNOWN', 'reason': 'PSUTIL_UNAVAILABLE',
                    'error': self._import_error}
        try:
            p = psutil.Process(pid)
            born = p.create_time()
            name = p.name()
            if not p.is_running() or p.status() == psutil.STATUS_ZOMBIE:
                return {'pid': pid, 'create_time': born, 'name': name, 'state': 'EXITED'}
            try:
                rss = int(p.memory_info().rss)
                memory_error = None
            except (psutil.AccessDenied, OSError) as error:
                rss, memory_error = None, type(error).__name__ + ': ' + str(error)
            return {'pid': pid, 'create_time': born, 'name': name, 'state': 'ACTIVE',
                    'rss_bytes': rss, 'memory_error': memory_error}
        except psutil.NoSuchProcess:
            return {'pid': pid, 'state': 'EXITED'}
        except (psutil.Error, OSError) as error:
            return {'pid': pid, 'state': 'UNKNOWN', 'error': type(error).__name__ + ': ' + str(error)}

    def children(self, pid):
        psutil = self._psutil()
        if psutil is None:
            return {'state': 'UNKNOWN', 'processes': [], 'reason': 'PSUTIL_UNAVAILABLE'}
        try:
            processes = [self.describe(p.pid) for p in psutil.Process(pid).children(recursive=True)]
            complete = all(p.get('state') in ('ACTIVE', 'EXITED') for p in processes)
            return {'state': 'OK' if complete else 'UNKNOWN', 'processes': processes}
        except psutil.NoSuchProcess:
            return {'state': 'ROOT_EXITED', 'processes': []}
        except (psutil.Error, OSError) as error:
            return {'state': 'UNKNOWN', 'processes': [], 'error': type(error).__name__ + ': ' + str(error)}

    def signal(self, pid, create_time, *, force=False):
        psutil = self._psutil()
        if psutil is None:
            return {'state': 'NOT_SIGNALLED', 'reason': 'PSUTIL_UNAVAILABLE'}
        try:
            p = psutil.Process(pid)
            if p.create_time() != create_time:
                return {'state': 'NOT_SIGNALLED', 'reason': 'PID_REUSED'}
            # psutil additionally checks PID reuse for terminate/kill.
            (p.kill if force else p.terminate)()
            return {'state': 'SIGNALLED', 'action': 'kill' if force else 'terminate'}
        except psutil.NoSuchProcess:
            return {'state': 'ALREADY_EXITED'}
        except (psutil.Error, OSError) as error:
            return {'state': 'NOT_SIGNALLED', 'reason': type(error).__name__ + ': ' + str(error)}


class ProcessMonitor:
    """Sample only a captured root and its observed descendants.

    provider.describe(pid) returns {state, pid, create_time, name, rss_bytes};
    provider.children(pid) returns {state: OK/ROOT_EXITED/UNKNOWN, processes: []};
    provider.signal(pid, create_time, force=...) must recheck identity.

    Missing memory remains None. The sum peak is computed from one simultaneous
    sampling pass, never the sum of per-process lifetime peaks.
    """
    def __init__(self, root_pid, *, provider=None, clock=time.monotonic,
                 sample_interval_s=1.0):
        if type(root_pid) is not int or root_pid <= 0:
            raise ValueError('positive root PID required')
        if not isinstance(sample_interval_s, (int, float)) or isinstance(sample_interval_s, bool) or not math.isfinite(sample_interval_s) or sample_interval_s <= 0:
            raise ValueError('positive finite sample interval required')
        self.provider = provider if provider is not None else PsutilProvider()
        self.clock, self.interval = clock, float(sample_interval_s)
        self.root_pid, self.started = root_pid, clock()
        self.root = self._describe(root_pid)
        self.root_identity = _identity(self.root) if self.root.get('state') == 'ACTIVE' else None
        self.owned = {}
        self.identity_errors, self.discovery_errors = [], []
        self.samples, self.peaks = [], {}
        self.peak_sum, self.incomplete_memory_samples = None, 0
        self.last_sample_at = None
        if self.root_identity is not None:
            self._register(self.root, 'root_initial_capture')
        else:
            self.identity_errors.append('ROOT_IDENTITY_UNVERIFIED')

    def _describe(self, pid):
        try:
            value = self.provider.describe(pid)
            return value if isinstance(value, dict) else {'pid': pid, 'state': 'UNKNOWN', 'reason': 'MALFORMED_PROVIDER_RESULT'}
        except Exception as error:
            return {'pid': pid, 'state': 'UNKNOWN', 'error': type(error).__name__ + ': ' + str(error)}

    def _register(self, info, source):
        identity = _identity(info)
        if identity is None:
            self.identity_errors.append('DESCENDANT_IDENTITY_UNVERIFIED')
            return False
        if self.root_identity is None:
            return False
        if identity[0] == self.root_pid and identity != self.root_identity:
            self.identity_errors.append('ROOT_IDENTITY_MISMATCH')
            return False
        if identity[1] < self.root_identity[1]:
            self.identity_errors.append('DESCENDANT_PREDATES_ROOT')
            return False
        self.owned.setdefault(identity, {'pid': identity[0], 'create_time': identity[1],
                                        'name': info.get('name'), 'source': source})
        return True

    def register_identities(self, items, *, source):
        """Merge already-validated worker process-tree records from this call.

        The caller must bind the worker's record to this slot/input/source.
        This method does not establish that provenance by itself.
        """
        if not isinstance(source, str) or not source or not isinstance(items, list):
            raise ValueError('explicit source and identity records required')
        return [self._register(item, source) if isinstance(item, dict) else False for item in items]

    def _refresh(self):
        root_now = self._describe(self.root_pid)
        if (self.root_identity is not None and root_now.get('state') == 'ACTIVE'
                and _identity(root_now) == self.root_identity):
            try:
                tree = self.provider.children(self.root_pid)
            except Exception as error:
                tree = {'state': 'UNKNOWN', 'processes': [], 'error': str(error)}
            if not isinstance(tree, dict) or tree.get('state') not in ('OK', 'ROOT_EXITED'):
                self.discovery_errors.append('DESCENDANT_SCAN_UNRESOLVED')
            if isinstance(tree, dict):
                children = tree.get('processes', [])
                if not isinstance(children, list):
                    children = []
                    self.discovery_errors.append('MALFORMED_DESCENDANT_SCAN')
                for item in children:
                    if isinstance(item, dict) and item.get('state') == 'ACTIVE':
                        self._register(item, 'descendant_poll')
                    elif isinstance(item, dict) and item.get('state') not in ('EXITED',):
                        self.discovery_errors.append('DESCENDANT_SCAN_IDENTITY_UNKNOWN')
        elif root_now.get('state') == 'UNKNOWN':
            self.discovery_errors.append('ROOT_SCAN_UNRESOLVED')
        rows = []
        for identity, owned in sorted(self.owned.items()):
            current = root_now if identity[0] == self.root_pid else self._describe(identity[0])
            state = current.get('state', 'UNKNOWN')
            if state == 'ACTIVE' and _identity(current) != identity:
                state = 'PID_REUSED_ORIGINAL_EXITED' if _identity(current) is not None else 'UNKNOWN'
            rss = current.get('rss_bytes') if state == 'ACTIVE' else None
            if type(rss) is not int or rss < 0:
                rss = None
            name = owned.get('name') or current.get('name')
            role = ('PYTHON_ROOT' if identity == self.root_identity else
                    'MATLAB' if str(name or '').lower() in ('matlab.exe', 'matlab') else 'DESCENDANT')
            rows.append({**owned, 'role': role, 'state': state, 'rss_bytes': rss,
                         'memory_error': current.get('memory_error') if state == 'ACTIVE' else None})
        return rows

    def sample(self, *, force=False):
        now = self.clock()
        if not force and self.last_sample_at is not None and now-self.last_sample_at < self.interval:
            return {'state': 'NOT_DUE', 'sampled': False, 'elapsed_s': now-self.started}
        rows = self._refresh()
        active = [r for r in rows if r['state'] == 'ACTIVE']
        unknown = [r for r in rows if r['state'] == 'UNKNOWN']
        complete = (self.root_identity is not None and not unknown
                    and all(r['rss_bytes'] is not None for r in active))
        known = sum(r['rss_bytes'] for r in active if r['rss_bytes'] is not None)
        total = known if complete else None
        if total is not None:
            self.peak_sum = total if self.peak_sum is None else max(self.peak_sum, total)
        else:
            self.incomplete_memory_samples += 1
        for row in active:
            if row['rss_bytes'] is not None:
                key = (row['pid'], row['create_time'])
                self.peaks[key] = max(self.peaks.get(key, 0), row['rss_bytes'])
        result = {'state': 'SAMPLED', 'sampled': True, 'elapsed_s': now-self.started,
                  'processes': rows, 'memory_sample_complete': complete,
                  'same_sample_rss_sum_bytes': total, 'known_rss_sum_bytes': known,
                  'scope': 'observed process working sets; shared pages may be counted more than once'}
        self.samples.append(result)
        self.last_sample_at = now
        return result

    poll = sample

    def cleanup_verified(self):
        """True/False/None for captured identities, not complete containment."""
        rows = self._refresh()
        if any(r['state'] == 'ACTIVE' for r in rows):
            return False
        if (self.root_identity is None or self.identity_errors or self.discovery_errors
                or any(r['state'] not in ('EXITED', 'PID_REUSED_ORIGINAL_EXITED') for r in rows)):
            return None
        return True

    def terminate_owned(self, *, force=False):
        """Signal verified captured identities once; never signal by name."""
        self._refresh()
        records = []
        # Descendants first; the root is last. No waiting, retries or global kill.
        for identity, item in sorted(self.owned.items(), key=lambda x: x[0] == self.root_identity):
            current = self._describe(identity[0])
            state = current.get('state')
            if state == 'EXITED':
                outcome = {'state': 'ALREADY_EXITED'}
            elif state != 'ACTIVE' or _identity(current) != identity:
                outcome = {'state': 'NOT_SIGNALLED', 'reason': 'IDENTITY_UNKNOWN_OR_REUSED'}
            else:
                try:
                    outcome = self.provider.signal(identity[0], identity[1], force=force)
                except Exception as error:
                    outcome = {'state': 'NOT_SIGNALLED', 'reason': type(error).__name__ + ': ' + str(error)}
            records.append({'pid': identity[0], 'create_time': identity[1], 'force': force, **outcome})
        return records

    def summary(self):
        cleanup = self.cleanup_verified()
        return {'root_pid': self.root_pid, 'root_identity': list(self.root_identity) if self.root_identity else None,
                'sample_interval_s': self.interval, 'sample_count': len(self.samples),
                'sampled_peak_same_time_rss_sum_bytes': self.peak_sum,
                'sampled_peak_by_identity': [{**self.owned[k], 'sampled_peak_rss_bytes': value}
                                             for k, value in sorted(self.peaks.items())],
                'incomplete_memory_samples': self.incomplete_memory_samples,
                'identity_errors': list(self.identity_errors), 'discovery_errors': list(self.discovery_errors),
                'cleanup_verified_observed_tree': cleanup,
                'scope': 'sampled observed root/descendants only; no full containment guarantee or lifetime-peak summation',
                'worker_matlab_cleanup_receipt_also_required': True}


def default_host_probe(workspace_root):
    """Read current Windows host resources only when explicitly called."""
    result = {'state': 'UNAVAILABLE', 'physical_available_bytes': None,
              'commit_available_bytes': None, 'disk_free_bytes': None,
              'token_is_appcontainer': None, 'matlab_processes': None,
              'matlab_scan_complete': False, 'errors': []}
    if os.name != 'nt':
        result['errors'].append('FROZEN_HOST_REQUIRES_WINDOWS')
        return result
    provider = PsutilProvider()
    psutil = provider._psutil()
    if psutil is None:
        result['errors'].append('PSUTIL_UNAVAILABLE')
        return result
    try:
        import ctypes
        from ctypes import wintypes as w
        import shutil
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        advapi = ctypes.WinDLL('advapi32', use_last_error=True)
        advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
        advapi.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD, ctypes.POINTER(w.DWORD)]
        kernel.GetCurrentProcess.restype = w.HANDLE
        kernel.CloseHandle.argtypes = [w.HANDLE]
        token, flag, size = w.HANDLE(), w.DWORD(), w.DWORD()
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
            raise ctypes.WinError()
        try:
            if not advapi.GetTokenInformation(token, 29, ctypes.byref(flag), ctypes.sizeof(flag), ctypes.byref(size)):
                raise ctypes.WinError()
        finally:
            kernel.CloseHandle(token)
        class Memory(ctypes.Structure):
            _fields_ = [('length', w.DWORD), ('load', w.DWORD)] + [(n, ctypes.c_ulonglong) for n in (
                'total_phys', 'avail_phys', 'total_page', 'avail_page',
                'total_virtual', 'avail_virtual', 'avail_extended')]
        mem = Memory(); mem.length = ctypes.sizeof(mem)
        if not kernel.GlobalMemoryStatusEx(ctypes.byref(mem)):
            raise ctypes.WinError()
        matlab, complete = [], True
        for process in psutil.process_iter(['name', 'pid', 'create_time']):
            try:
                info = process.info
                if info.get('name') is None:
                    complete = False
                elif info['name'].lower() == 'matlab.exe':
                    matlab.append(dict(info))
            except (psutil.Error, OSError):
                complete = False
        result.update(state='AVAILABLE', physical_available_bytes=mem.avail_phys,
                      commit_available_bytes=mem.avail_page,
                      disk_free_bytes=shutil.disk_usage(Path(workspace_root)).free,
                      token_is_appcontainer=bool(flag.value), matlab_processes=matlab,
                      matlab_scan_complete=complete)
    except Exception as error:
        result['errors'].append(type(error).__name__ + ': ' + str(error))
    return result


def host_gate(probe):
    """Pure resource decision. Unknown measurements fail closed."""
    if not isinstance(probe, dict):
        return {'passed': False, 'reasons': ['MALFORMED_HOST_PROBE']}
    reasons = []
    if probe.get('state') != 'AVAILABLE': reasons.append('HOST_PROBE_UNAVAILABLE')
    for name, minimum in (('physical_available_bytes', 2*GIB),
                          ('commit_available_bytes', 4*GIB), ('disk_free_bytes', 2*GIB)):
        value = probe.get(name)
        if type(value) is not int or value < minimum:
            reasons.append('INSUFFICIENT_OR_UNKNOWN_'+name.upper())
    if probe.get('token_is_appcontainer') is not False:
        reasons.append('APPCONTAINER_OR_UNKNOWN')
    if probe.get('matlab_scan_complete') is not True or not isinstance(probe.get('matlab_processes'), list):
        reasons.append('MATLAB_SCAN_UNVERIFIED')
    elif probe['matlab_processes']:
        reasons.append('PREEXISTING_MATLAB')
    if probe.get('errors'):
        reasons.append('HOST_PROBE_ERRORS')
    return {'passed': not reasons, 'reasons': reasons}
