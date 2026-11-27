from shared import *
from run import improves,logs
def main():
    examples=[]
    for c in ['D1','D2','C10']:
        folder=RUN/c/'diagnostic';receipt=read(folder/'receipt.json')
        assert receipt['status']=='COMPLETE' and receipt['wall_s']<600
        for row in logs(folder/'candidates.jsonl'):
            m=row.get('result',{})
            if m.get('status')!='SAFE' or not improves(m,receipt['initial']):continue
            if not any(m.get(k,0) for k in ('config_changes','start_changes','gap_flag_changes')):continue
            examples.append(dict(case=c,seq=row['seq'],region=row['region'],kind=row['kind'],result=m))
    put(RUN/'gate.json',dict(open=bool(examples),condition='strict SAFE interval improvement with identified physical change',witnesses=examples))
    print('OPEN' if examples else 'CLOSED')
if __name__=='__main__':main()
