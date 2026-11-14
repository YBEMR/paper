"""Render the completed audit from local documents; no experiments or downloads."""
from pathlib import Path
import markdown
R=Path(__file__).resolve().parent
parts=[('report','REPORT.md'),('sources','SOURCE_AUDIT.md'),('model','SYMBOLIC_MODEL.md'),('review','REVIEW.md')]
html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>共享内存与热频率限制：准入审计</title><style>body{max-width:1150px;margin:32px auto;padding:0 26px;color:#20303a;font:16px/1.85 system-ui,"Microsoft YaHei",sans-serif}h1{font-size:28px;color:#204e69}h2{font-size:21px;margin-top:32px;border-top:1px solid #d9e1e5;padding-top:14px}table{border-collapse:collapse;display:block;overflow-x:auto;font-size:14px;margin:18px 0}th,td{border:1px solid #d6dfe5;padding:9px 11px;text-align:left;vertical-align:top}th{background:#eaf2f6}tr:nth-child(even){background:#f7f9fa}code,pre{background:#eef2f4}pre{padding:12px;overflow:auto}a{color:#12698a}nav{background:#eaf2f6;padding:12px}section{margin-bottom:65px}</style><nav><a href="#report">结论</a> · <a href="#sources">资料审计</a> · <a href="#model">符号模型</a> · <a href="#review">复核</a></nav>'
for anchor,file in parts:
    body=markdown.markdown((R/file).read_text(encoding='utf-8'),extensions=['tables','fenced_code'])
    for target,name in parts:body=body.replace('href="'+name+'"','href="#'+target+'"')
    html+='<section id="'+anchor+'">'+body+'</section>'
html+='</html>';(R/'report.html').write_text(html,encoding='utf-8');print('Rendered audit report, bytes',len(html.encode()))
