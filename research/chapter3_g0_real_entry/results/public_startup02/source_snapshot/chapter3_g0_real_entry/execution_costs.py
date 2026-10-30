"""Root-elapsed accounting only; never changes clocks or scientific data."""
import math

LEGACY='legacy_slot_startup_v1'
PUBLIC='phase_public_startup_v1'


def startup_cost(start,end,metadata):
    if not all(math.isfinite(x) for x in (start,end)) or end<start:
        raise ValueError('INVALID_STARTUP_OVERVIEW')
    points=(metadata or {}).get('startup_intervals') or {}
    parts=[]
    for name,a,b in (('ready_wait','ready_wait_start_s','ready_wait_end_s'),
                     ('failed_startup_cleanup','failure_cleanup_start_s','failure_cleanup_end_s')):
        lo,hi=points.get(a),points.get(b)
        if lo is None and hi is None:continue
        if (type(lo) not in (int,float) or type(hi) not in (int,float)
                or not math.isfinite(lo) or not math.isfinite(hi) or not start<=lo<=hi<=end):
            raise ValueError('INVALID_STARTUP_COMPONENT:'+name)
        parts.append((lo,hi,name))
    segments=[];cursor=start
    for lo,hi,name in sorted(parts):
        if lo<cursor:raise ValueError('OVERLAPPING_STARTUP_COMPONENTS')
        if lo>cursor:segments.append({'name':'startup_other','start_s':cursor,'end_s':lo})
        segments.append({'name':name,'start_s':lo,'end_s':hi});cursor=hi
    if cursor<end:segments.append({'name':'startup_other','start_s':cursor,'end_s':end})
    totals={}
    for item in segments:
        item['seconds']=item['end_s']-item['start_s']
        totals[item['name']]=totals.get(item['name'],0)+item['seconds']
    return {'overview':{'start_s':start,'end_s':end,'seconds':end-start,
                        'includes_failed_startup_cleanup':True,'add_to_components':False},
            'exclusive_segments':segments,'exclusive_seconds':totals,
            'component_detail_available':bool(parts),
            'rule':'sum exclusive segments only; overview is not an extra cost'}
