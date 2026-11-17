"""Read-only consistency checks for data, claims, provenance, and standalone HTML."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path

root=Path(__file__).resolve().parent
def read(p): return json.loads((root/p).read_text(encoding='utf-8'))
rows=[json.loads(x) for x in (root/'results/all_candidates.jsonl').read_text().splitlines()]
env=read('results/run_environment.json')
assert len(rows)==1224
assert hashlib.sha256((root/'parameters.json').read_bytes()).hexdigest()==env['parameters_sha256']
assert hashlib.sha256((root/'screen.py').read_bytes()).hexdigest()==env['code_sha256']
assert read('results/checks.json')['pass']
summaries=read('results/summary.json')
for x in summaries:
    if x['variant']=='full':
        assert x['best']['ids']==x['best_without_temperature_limit']['ids']
        assert x['feasible']==(56 if x['direction']=='A' else 44)
    assert x['replay_full_feasible']==len(x['best']['ids'])
a=read('results/analysis.json')
assert a['A']['adaptive_gain_J']==0
assert a['B']['best_ids']=={'cool':'B-211-100','warm':'B-22-11'}
assert abs(a['B']['adaptive_gain_percent']-0.05949957224613001)<1e-12
assert read('results/energy_accounting_check.json')['rows']==306

class Audit(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=[];self.refs=[];self.images=[];self.level2=0
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if 'id' in d:self.ids.append(d['id'])
        if tag=='a':self.refs.append(d.get('href',''))
        if tag=='img':self.images.append(d.get('src',''))
        if tag=='h2':self.level2+=1

doc=(root/'report.html').read_text(encoding='utf-8')
h=Audit();h.feed(doc);h.close()
assert len(h.ids)==len(set(h.ids))
assert all(x[1:] in h.ids for x in h.refs if x.startswith('#'))
assert all(x.startswith('https://') or x.startswith('#') for x in h.refs)
assert len(h.images)==1 and h.images[0].startswith('data:image/png;base64,')
assert h.level2==7
assert '0.0594996%' in doc and '51.98°C' in doc
assert 'PROPOSED_NOT_EXECUTED' in doc and 'SYNTHETIC_UNCALIBRATED' in doc
assert not any(x in doc for x in ['TODO','{{','turn0search','turn1view'])
summary=dict(status='PASS',raw_rows=len(rows),model_groups=len(summaries),full_accounting_rows=306,html_sections=h.level2,source_links=sum(x.startswith('https://') for x in h.refs),unique_internal_ids=len(h.ids),embedded_images=len(h.images),note='Data/HTML consistency only; not hardware validation or full visual rendering certification.')
(root/'results/delivery_qa.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary))
