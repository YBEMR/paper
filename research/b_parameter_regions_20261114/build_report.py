"""Create a self-contained HTML report from the checked report and figure."""
import base64,html,re
from pathlib import Path
from urllib.parse import quote
import markdown

ROOT=Path(__file__).resolve().parent
text=(ROOT/'REPORT.md').read_text(encoding='utf-8')
figure='data:image/png;base64,'+base64.b64encode((ROOT/'region_summary.png').read_bytes()).decode('ascii')
text=text.replace('(region_summary.svg)','('+figure+')')
base='https://github.com/YBEMR/paper/blob/research/direction-screening-20261114/research/b_parameter_regions_20261114/'
def link(match):
    label,target=match.groups()
    if target.startswith(('http:','https:','data:','#')):return match.group()
    return '['+label+']('+base+quote(target,safe='/')+')'
text=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',link,text)
body=markdown.markdown(text,extensions=['tables','fenced_code'])
css='''body{font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif;color:#163047;background:#eff3f6;margin:0;line-height:1.8}main{max-width:1080px;margin:30px auto;background:white;padding:42px 52px;box-shadow:0 3px 25px #102b4010}h1{font-size:30px;line-height:1.45}h2{font-size:23px;border-bottom:2px solid #dbe7eb;padding-bottom:8px;margin-top:40px}h3{font-size:19px}p,li{font-size:16px}strong{color:#0e615b}a{color:#216b9a}img{width:100%;height:auto;margin:14px 0}table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.65;margin:20px 0;display:block;overflow-x:auto}th{background:#e8f1f3;text-align:left}td,th{border:1px solid #d4e1e5;padding:10px 13px}tr:nth-child(even){background:#f7fafb}code{font-family:Consolas,monospace;background:#eff3f6;padding:2px 4px;overflow-wrap:anywhere}pre{white-space:pre-wrap;padding:16px;background:#eff3f6}.meta{font-size:13px;color:#526775;border-bottom:1px solid #d4e1e5;padding-bottom:18px}@media(max-width:700px){main{margin:0;padding:20px}h1{font-size:25px}table{font-size:13px}}@media print{body{background:white}main{box-shadow:none;margin:0;padding:0}h2{break-after:avoid}tr{break-inside:avoid}a{color:inherit}}'''
page='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>B参数区域与稳健性分析</title><style>'+css+'</style></head><body><main><div class="meta">研究记录 · 2026-11-14 · 图已嵌入，可离线阅读；明细链接指向已授权研究分支</div>'+body+'</main></body></html>'
(ROOT/'report.html').write_text(page,encoding='utf-8')
assert '<table>' in page and 'data:image/png;base64,' in page and '<html lang="zh-CN">' in page
print({'html_bytes':len(page.encode('utf-8')),'tables':page.count('<table>'),'remote_scripts':page.count('<script')})
