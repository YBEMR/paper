"""Exact repetition/splitting of frozen power histories, no scheduling."""
from copy import deepcopy
from fractions import Fraction as F

TIME_FIELDS={'start_ms','end_ms','duration_ms'}
def signature(row):return {k:v for k,v in row.items() if k not in TIME_FIELDS}
def repeat_history(period_segments,period_ms,horizon_ms):
    p,h=F(period_ms),F(horizon_ms);out=[];origin=[];cycle=0
    if p<=0 or h<=0:raise ValueError('POSITIVE_TIME_REQUIRED')
    while cycle*p<h:
        for index,segment in enumerate(period_segments):
            start,end=cycle*p+F(segment['start_ms']),min(h,cycle*p+F(segment['end_ms']))
            if start>=h:break
            row=deepcopy(segment);row.update(start_ms=str(start),end_ms=str(end),duration_ms=str(end-start));out.append(row);origin.append({'cycle_index_zero_based':cycle,'source_segment_index':index})
        cycle+=1
    validate_coverage(out,h)
    return out,origin
def split_history(coarse,max_step_ms='2'):
    step=F(max_step_ms);fine=[];parent=[]
    if step<=0:raise ValueError('POSITIVE_STEP_REQUIRED')
    for index,segment in enumerate(coarse):
        left,right=F(segment['start_ms']),F(segment['end_ms'])
        while left<right:
            end=min(right,left+step);row=deepcopy(segment);row.update(start_ms=str(left),end_ms=str(end),duration_ms=str(end-left));fine.append(row);parent.append(index);left=end
    validate_coverage(fine,F(coarse[-1]['end_ms']))
    for index,segment in enumerate(coarse):
        children=[r for r,p in zip(fine,parent) if p==index]
        if not children or sum(F(r['duration_ms']) for r in children)!=F(segment['duration_ms']):raise ValueError('SPLIT_DURATION_CHANGED')
        if any(signature(r)!=signature(segment) for r in children):raise ValueError('SPLIT_POWER_OR_OCCUPANCY_CHANGED')
    return fine,parent
def validate_coverage(segments,horizon):
    cursor=F(0)
    for row in segments:
        a,b,d=map(F,(row['start_ms'],row['end_ms'],row['duration_ms']))
        if a!=cursor or b<=a or d!=b-a:raise ValueError('HISTORY_GAP_OR_OVERLAP')
        cursor=b
    if cursor!=F(horizon):raise ValueError('HORIZON_CHANGED')

