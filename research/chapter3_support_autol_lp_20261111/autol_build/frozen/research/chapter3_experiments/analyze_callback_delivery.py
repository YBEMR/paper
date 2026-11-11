"""Read saved 300/600-second callback records; no scientific/model imports.

Usage: python -B research/chapter3_experiments/analyze_callback_delivery.py NEW.json
Original files and existing output are never overwritten.
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / 'research/chapter3_experiments/results'
CASES = ('natural_full_repaired_execution01', 'natural_full_600_execution01')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(value):
    return hashlib.sha256(json.dumps(value, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def extract(name):
    slot = RESULTS / name / 'slots/whole_milp__method'
    folder = slot / 'worker/method'
    native = folder / 'matlab'
    ticket = read(slot / 'ticket.json')
    raw = read(slot / 'worker/raw_result.json')
    request = read(native / 'request_000001.request.json')
    response = read(native / 'request_000001.response.json')
    returned = read(native / 'request_000001.python.json')
    admission = read(native / 'request_000001.equality_admission.json')
    closed = read(native / 'closed.json')
    cert = read(native / 'request_000001.equality_certificate.json')
    records = [json.loads(line) for line in
               (folder / 'diagnostic_events.jsonl').read_text(encoding='utf-8').splitlines()]
    receipts = {r['event_number']: r['method_elapsed_s'] for r in records
                if r.get('event') == 'worker_event_received'}
    publication = next(r for r in raw['timing']['phase_records']
                       if r['phase'] == 'transport_request_publication')
    offset_lower = publication['start_s']
    events, vectors = [], {}
    for path in sorted(native.glob('request_000001.event_*.json')):
        event = read(path)
        number = event['event_number']
        x = event.get('x', [])
        vectors[number] = x
        appeared = event['request_wall_seconds']
        received = receipts.get(number)
        events.append(dict(event_number=number, kind=event.get('kind'),
            state=event.get('state'), native_request_elapsed_s=appeared,
            solver_values=event.get('values'), vector_length=len(x),
            vector_json_sha256=digest(x) if x else None,
            python_received_root_s=received,
            root_time_estimate_lower_s=offset_lower + appeared,
            publication_and_read_delay_estimate_upper_s=(None if received is None
                else received - offset_lower - appeared)))
    e5, e6 = events[4], events[5]
    assert e5['event_number'] == 5 and e6['event_number'] == 6
    budget = ticket['scientific_deadline'] - ticket['origin']
    return dict(case=name, root_budget_s=budget,
        root_origin_monotonic=ticket['origin'], absolute_deadline=ticket['scientific_deadline'],
        request_publication_root_interval_s=[publication['start_s'], publication['end_s']],
        native_request_remaining_s=request['remaining_s'],
        native_MaxTime_s=response['options']['MaxTime'],
        native_phase_seconds=response['phase_seconds'], events=events,
        native_event5_to_event6_gap_s=e6['native_request_elapsed_s']-e5['native_request_elapsed_s'],
        event6_exceeds_native_request_remaining_s=e6['native_request_elapsed_s']-request['remaining_s'],
        event6_callback_request_deadline_stop_condition_true=e6['native_request_elapsed_s']>=request['remaining_s'],
        timely_python_received_event_numbers=sorted(receipts),
        response_read_attempts=returned['publication_read']['attempts'],
        response_read_errors=returned['publication_read']['transient_read_errors'],
        python_return=dict(status=returned['status'], budget_valid=returned['budget_valid'],
            accepted_for_evaluation=returned['accepted_for_evaluation'], vector_length=len(returned['x']),
            root_s=admission['backend_returned_at_monotonic']-ticket['origin']),
        cancel_write_root_interval_s=[budget, admission['backend_returned_at_monotonic']-ticket['origin']],
        cancel_write_interval_basis='Source: PublicationTimeout occurs at/after deadline, writes cancel before backend returns; no dedicated cancel timestamp.',
        cancel_file_content=(native/'request_000001.cancel').read_text(encoding='ascii').strip(),
        graceful_cleanup_started_root_s=closed['cleanup_started_at_monotonic']-ticket['origin'],
        cleanup_wall_s=closed['cleanup_wall_seconds'],
        cleanup_force_requested=closed['force_requested'],
        cleanup_graceful_stop_requested=closed['graceful_stop_requested'],
        cleanup_verified=closed['observed_tree_verified_terminated'],
        method_process_wall_s=read(slot/'slot_result.json')['total_wall_s'],
        native_response_request_elapsed_s=response['matlab_request_wall_seconds'],
        native_response=dict(status=response['status'], exitflag=response['exitflag'],
                             fval=response['fval'], output=response['output']),
        original_arrays_sha256=cert['source_array_sha256'],
        evidence_sha256={p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [slot/'ticket.json', slot/'worker/raw_result.json',
                folder/'diagnostic_events.jsonl', native/'request_000001.request.json',
                native/'request_000001.response.json', native/'request_000001.python.json',
                native/'request_000001.equality_certificate.json', native/'closed.json']}
        ), vectors


def analyze():
    rows, vectors = [], []
    for case in CASES:
        row, values = extract(case)
        rows.append(row)
        vectors.append(values)
    return dict(state='READONLY_TIMELINE_COMPLETE', scientific_calls=0, model_builds=0,
        solver_calls=0, thermal_evaluations=0, runs=rows,
        both_initial_vectors_identical=vectors[0][4] == vectors[1][4],
        both_late_vectors_identical=vectors[0][6] == vectors[1][6],
        both_original_array_certificates_identical=rows[0]['original_arrays_sha256']==rows[1]['original_arrays_sha256'],
        conclusions=[
            'The long gap already exists between native request-relative event timestamps; it is not merely Python receiving an earlier event6 late.',
            'Each event6 timestamp exceeds its own native request remaining_s before publication; callback stop can therefore be true independently of the cancel file.',
            'Event6 has the same complete 10956-coordinate vector in both runs, not only the same objective.',
            'Python accepted and evaluated only event4, which is the initial schedule. Event6/7 have no timely Python receipt.',
            'Internal incumbent discovery time and why native code invokes event6 at that moment are not observed. The callback request-time stop condition is already true.',
            'The bridge reads its cancel file only after publishing the callback event; that read cannot explain the earlier native production of event6. Cleanup did not request force termination.'
        ], clock_limitations=[
            'Python root uses monotonic; MATLAB request/solver use their own elapsed timers. Publication-start plus request elapsed is an engineering lower estimate assuming elapsed scales agree, not an independently calibrated clock identity.',
            'Early receipt minus that lower estimate bounds event publication/read overhead only under that same clock assumption; it is not a hard real-time guarantee.',
            'No file mtime/ctime is used as an immutable scientific timestamp. Restoring files can alter such metadata.',
            'Native response elapsed is recorded before JSON publication; it is not Python acceptance time.',
            'The late vector is neither decoded nor thermally evaluated by this analysis.'
        ])


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: analyze_callback_delivery.py NEW_OUTPUT_JSON')
    target = Path(sys.argv[1])
    if target.exists():
        raise SystemExit('Refusing to overwrite existing output')
    result = analyze()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(state=result['state'], identical_late_vectors=result['both_late_vectors_identical'],
                         native_callback_gaps_s=[r['native_event5_to_event6_gap_s'] for r in result['runs']])))
