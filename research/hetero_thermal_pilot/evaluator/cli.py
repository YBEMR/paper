"""Standard-library certificate sidecar used by the MATLAB entry."""
from pathlib import Path
import argparse,json,sys
if __package__ in (None,''): sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evaluator.schedule import evaluate_frozen

def main():
    ap=argparse.ArgumentParser(); group=ap.add_mutually_exclusive_group(required=True); group.add_argument('--fixture'); group.add_argument('--schedule',type=Path)
    ap.add_argument('--seconds',type=float,default=60); ap.add_argument('--output',type=Path,required=True); args=ap.parse_args()
    if args.seconds<=0 or args.seconds>60: ap.error('A04 per-evaluation cap must be in (0,60] seconds')
    result=evaluate_frozen(args.schedule,args.fixture,args.seconds)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(result['state'],result.get('reason',''))
if __name__=='__main__': main()
