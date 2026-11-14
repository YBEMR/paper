"""Render the reviewed report for reading; calculation does not depend on this."""
from pathlib import Path
import markdown
from html.parser import HTMLParser

root=Path(__file__).resolve().parent
body=markdown.markdown((root/'REPORT.md').read_text(encoding='utf-8'),extensions=['tables','fenced_code'])
base='https://github.com/YBEMR/paper/blob/research/direction-screening-20261114/research/b_parameter_audit_20261114/'
# Resolve artifact links so the standalone output remains navigable.
import re
body=re.sub(r'href="(?!https?://|#)([^\"]+)"',lambda m:'href="'+base+m.group(1)+'"',body)
html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>B 同平台参数与可测效应审计</title><style>
:root{font-family:system-ui,"Microsoft YaHei",sans-serif;color:#203345;background:#f1f4f6;line-height:1.8}body{max-width:1060px;margin:24px auto;padding:42px 54px;background:white;border-top:6px solid #167c80}h1{font-size:30px;line-height:1.35}h2{font-size:21px;margin-top:32px;color:#10666b}p{margin:15px 0}a{color:#086c86;text-decoration-thickness:1px}table{border-collapse:collapse;width:100%;font-size:14px;margin:22px 0}th,td{border:1px solid #d3dde1;padding:10px;vertical-align:top}th{background:#e8f1f2}code{font-family:Consolas,monospace;background:#f1f4f6;padding:2px 5px;overflow-wrap:anywhere}li{margin:10px 0}strong{color:#183f52}@media(max-width:700px){body{margin:0;padding:20px}h1{font-size:25px}table{font-size:12px}th,td{padding:6px}}@media print{body{margin:0;max-width:none;padding:0;border:0}h2{break-after:avoid}tr{break-inside:avoid}}
</style><body>'''+body+'</body></html>'
(root/'report.html').write_text(html,encoding='utf-8')
print('Rendered report.html')
