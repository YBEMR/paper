"""Read-only replay of selection and receipt identity; no search or thermal calls."""
from fractions import Fraction as F
from h02_pair_preflight.common import require, sha, timely
from .scoring import score_candidate


def verify_export(instance, config, result, seconds=300):
    require(result.get('method') == 'e1-adapted-heft' and result.get('seed') is None, 'METHOD')
    if 'archive' not in result:
        require(result.get('state') == 'UNRESOLVED' and all(result.get(k) is None for k in
                ('safe_candidate','evaluation','safe_upper_bound_J','planning_score_J')), 'EARLY_FALSE_SAFE')
        require(result.get('timing',{}).get('limit_s') == seconds, 'EARLY_BUDGET')
        require(result.get('stop_required') is True or
                (result.get('reason') == 'METHOD_BUDGET_EXHAUSTED' and
                 result['timing']['method_elapsed_s'] >= seconds), 'EARLY_STOP_CLASSIFICATION')
        return dict(state='NO_SELECTED_SAFE_INPUT_UNFINISHED', stop_required=result.get('stop_required') is True)
    require(result.get('input_sha256') == sha(instance) and
            result.get('config_sha256') == sha(config), 'EXPORT_INPUT')
    require(result.get('timing', {}).get('limit_s') == seconds, 'EXPORT_BUDGET')
    require(result.get('objective') in ('FULL', 'OMIT_TEMP'), 'EXPORT_OBJECTIVE')
    archive = result.get('archive', {})
    require(archive.get('objective') == result['objective'] and
            archive.get('input_sha256') == sha(instance) and
            archive.get('accuracy_sha256') == sha(config['accuracy_targets']), 'ARCHIVE_CONTEXT')
    selected = None
    last = -1
    for row in archive.get('evaluations', []):
        if not row.get('eligible_for_selection'): continue
        stamp, returned = row.get('selection_formed_at_s'), row.get('returned_at_s')
        require(timely(stamp, seconds) and timely(returned, seconds) and
                last <= returned <= stamp, 'SELECTION_TIME')
        last = stamp
        require(row.get('accepted_safe') is True and row['candidate_sha256'] == sha(row['candidate']),
                'ROW_CANDIDATE')
        require(row['evaluation']['completed_at_elapsed_s'] <= returned, 'RECEIPT_TIME')
        expected = score_candidate(instance, row['candidate'], row['legality'], row['evaluation'],
                                   config['accuracy_targets'], seconds, result['objective'])
        require(expected == row.get('score'), 'SCORE_REPLAY')
        if selected is None or F(expected['planning_score_J'][1]) < F(selected['score']['planning_score_J'][1]):
            selected = row  # Earliest on ties. True U is never a tiebreaker.
    require(archive.get('best') == selected, 'ARCHIVED_SELECTION')
    if selected is None:
        require(result.get('state') == 'UNRESOLVED' and all(result.get(k) is None for k in
                ('safe_candidate', 'evaluation', 'safe_upper_bound_J', 'planning_score_J')), 'FALSE_FINAL_SAFE')
        return dict(state='NO_SELECTED_SAFE', stop_required=result.get('stop_required') is True)
    require(result.get('state') == 'SAFE' and
            result['safe_candidate'] == selected['candidate'] and result['evaluation'] == selected['evaluation'] and
            result['safe_upper_bound_J'] == selected['evaluation']['safe_upper_bound_J'] and
            result['planning_score_J'] == selected['score']['planning_score_J'] and
            result['selected_candidate_sha256'] == selected['candidate_sha256'] and
            result['selected_at_s'] == selected['selection_formed_at_s'] and
            result['selected_source'] == selected['source'], 'FINAL_SELECTION_IDENTITY')
    return dict(state='SELECTED_SAFE_IDENTITY_VERIFIED', candidate_sha256=selected['candidate_sha256'],
                stop_required=result.get('stop_required') is True)
