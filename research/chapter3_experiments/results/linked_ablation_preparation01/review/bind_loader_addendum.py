"""Append final loader-text addendum binding without overwriting prior reviews."""
from copy import deepcopy
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent
REPO = HERE.parents[4]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def save(name, payload):
    with (HERE / name).open('x', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write('\n')

def main():
    old = read(HERE / 'final_review.json')
    add_path = AUDIT / 'audit/protocol_loader_addendum.json'
    add = read(add_path)
    raw = (AUDIT / 'protocol.md').read_bytes()
    assert add['passed'] and sha(AUDIT / 'protocol.md') == add['current_protocol_sha256']
    removed = raw.replace(add['added_sentence'].encode('utf-8'), b'', 1)
    assert raw.count(add['added_sentence'].encode('utf-8')) == 1
    assert hashlib.sha256(removed).hexdigest() == add['previous_protocol_sha256'] == add['remove_only_added_sentence_sha256']
    assert sha(AUDIT / 'audit/proposal_review.json') == add['previous_review_json_sha256']
    assert sha(AUDIT / 'audit/proposal_review.md') == add['previous_review_md_sha256']
    assert add['prior_nine_checks_preserved'] and all(add['all_other_review_inputs_unchanged'].values())
    proposal = read(AUDIT / 'preparation02/proposal.json')
    assert all(sha(REPO / k) == v for k, v in proposal['source_sha256'].items())
    assert not proposal['authorized'] and not proposal['scientific_execution_enabled'] and proposal['claim'] is None
    for binding in add['code_contract']:
        assert sha(REPO / binding['path']) == binding['sha256']
        source = (REPO / binding['path']).read_text(encoding='utf-8-sig')
        expected_node = ast.parse(binding['expression']).body[0]
        expected_ast = ast.dump(expected_node, include_attributes=False)
        assert any(ast.dump(node, include_attributes=False) == expected_ast
                   for node in ast.walk(ast.parse(source)))
    record = deepcopy(old)
    record['protocol'] = 'K172-independent-final-preparation-review-v2'
    record['previous_review_preserved_sha256'] = sha(HERE / 'final_review.json')
    record['previous_review_path'] = (HERE / 'final_review.json').relative_to(REPO).as_posix()
    record['v2_scope'] = 'Bind independently verified loader return-shape text clarification and preserved prior audit; no science, code, inputs or budgets changed.'
    record['first_review_protocol_hash_already_matches_final'] = old['evidence_sha256'][(AUDIT / 'protocol.md').relative_to(REPO).as_posix()] == add['current_protocol_sha256']
    record['checks'].extend([
        {'name': 'loader_sentence_only_change_exact_byte_proof_and_old_audit_bound', 'passed': True},
        {'name': 'loader_3_to2_return_contract_matches_frozen_code_and_pending_state', 'passed': True}])
    record['checks_passed'] = len(record['checks'])
    record['loader_clarification'] = {'current_protocol_sha256': add['current_protocol_sha256'],
        'addendum_json_sha256': sha(add_path), 'return_shape': 'fresh_input -> (raw, config, instance); thin input_loader -> (config, instance)',
        'runtime_launcher_still_not_implemented_or_admitted': True}
    paths = [AUDIT / 'protocol.md', add_path, AUDIT / 'audit/protocol_loader_addendum.md',
        AUDIT / 'audit/proposal_review.md', HERE / 'final_review.json', HERE / 'final_review.md', HERE / 'final_manifest.json']
    for p in paths:
        record['evidence_sha256'][p.relative_to(REPO).as_posix()] = sha(p)
    failed_review_check = HERE / 'loader_binding_run01_failure.json'
    record['evidence_sha256'][failed_review_check.relative_to(REPO).as_posix()] = sha(failed_review_check)
    record['review_check_history'] = 'Literal substring validation was too strict about Python whitespace and tuple parentheses; failed check retained, final check compares exact AST without executing code.'
    # Original independent metadata and final old-artifact check are inherited;
    # a documentary clarification does not require another large hash sweep.
    assert read(HERE / 'after_manifest.json')['passed']
    save('final_review02.json', record)
    text = (HERE / 'final_review.md').read_text(encoding='utf-8')
    text = text.replace('另核48项', '另核48项（补充核对后共50项）')
    text = text.replace('`final_review.json`、`final_manifest.json`', '`final_review02.json`、`final_manifest02.json`')
    text += '\n补充绑定：最终协议loader须把`fresh_input`三个返回值解包，再向方法返回`config, instance`；已核其只新增该合同澄清句，移除即恢复原审查绑定hash。原独立审查及首次终审均保留，活动终审以02为准。实际launcher仍未实现、未准入、未授权。\n'
    with (HERE / 'final_review02.md').open('x', encoding='utf-8') as f:
        f.write(text)
    manifest_hashes = dict(record['evidence_sha256'])
    for p in [HERE / 'final_review02.json', HERE / 'final_review02.md', HERE / 'bind_loader_addendum.py']:
        manifest_hashes[p.relative_to(REPO).as_posix()] = sha(p)
    save('final_manifest02.json', {'protocol': 'K172-independent-final-evidence-binding-v2',
        'active_review': (HERE / 'final_review02.json').relative_to(REPO).as_posix(),
        'previous_review_preserved': (HERE / 'final_review.json').relative_to(REPO).as_posix(),
        'sha256': manifest_hashes, 'self_excluded': True, 'prepared_only': True, 'new_scientific_calls': 0})
    print(json.dumps({'active_review': 'final_review02.json', 'checks_passed': len(record['checks']),
        'review_sha256': sha(HERE / 'final_review02.json'), 'current_protocol_sha256': add['current_protocol_sha256'],
        'prepared_only': True, 'new_scientific_calls': 0}, ensure_ascii=False))

if __name__ == '__main__':
    main()
