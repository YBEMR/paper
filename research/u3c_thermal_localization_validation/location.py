"""Window indices are zero-based internally. Peak can lie in the drain interval."""
def simple(method, n, raw_peak, keys=None):
    if method == "slack":
        return min(keys)[3]
    if method == "peak":
        return min(raw_peak, n-1)
    if method == "previous":
        return min(n-1, max(0,raw_peak-1))
    if method == "energy":
        eligible = keys[:max(1,min(raw_peak,n))]
        return min(eligible, key=lambda row: (row[2],row[3]))[3]
    raise ValueError(method)


def select(ctx, method, anchor, cert, trace):
    from guidance import Guidance
    from local_search import anchor_window

    metrics = cert["metrics"]
    node = metrics["hotspot"]
    peak_tick = metrics["peak_tick"][node]
    raw_peak = int(peak_tick // ctx.b.e.dur)
    n = len(ctx.b.types)
    assert 0 <= raw_peak <= n
    info = dict(method=method,anchor=cert["plan_sha256"],node=int(node),
                peak_tick=peak_tick,raw_peak_w=raw_peak+1,windows=n)
    if method == "heat":
        guide = Guidance(ctx.b, anchor, cert, trace)
        chosen = guide.window
        info["heat"] = guide.observation
    else:
        keys = None
        if method in ("slack","energy"):
            _, keys = anchor_window(ctx,anchor)
            info["ordinary_keys"] = keys
        chosen = simple(method,n,raw_peak,keys)
    info["selected_w"] = chosen+1
    return chosen,info
