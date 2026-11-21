"""Finite deployment domain for the cooperative-cut study. No solver is invoked.

A per-app shape is a tuple of inclusive DLA prefix endpoints; the final block
always runs on GPU. The first DLA may be on either physical DLA, and a second
one must use the other DLA. Each shape is checked by the original catalog.
"""
import argparse
from bisect import bisect_right
from collections import Counter
from collections.abc import Sequence
from functools import lru_cache
from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path
import sys


N_APPS = 4
SLOT_CAP = 4
HERE = Path(__file__).resolve().parent


def _stages(size, cuts, orientation):
    rows = []
    start = 0
    for i, end in enumerate(cuts):
        rows.append([f"DLA{orientation ^ i}", start, end])
        start = end + 1
    rows.append(["GPU", start, size - 1])
    return rows


def _canonical(layout):
    first = next((orientation for shape, orientation in layout if shape), 0)
    return tuple((shape, orientation ^ first if shape else 0) for shape, orientation in layout)


class LazyOrder(Sequence):
    """Same uniform random-index semantics as a list, without instantiating millions of rows."""

    def __init__(self, domain):
        self.domain = domain

    def __len__(self):
        return self.domain.size

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        if index < len(self.domain.legacy_ids):
            return self.domain.legacy_ids[index]
        # Insert the holes occupied by legacy representatives into the dense novel ranks.
        novel_index = index - len(self.domain.legacy_ids)
        raw = novel_index + bisect_right(self.domain.legacy_holes, novel_index)
        return self.domain.ident(raw)

    def __contains__(self, dep):
        try:
            self.domain.raw(dep)
            return True
        except (KeyError, TypeError, ValueError):
            return False

    def index(self, dep, start=0, stop=None):
        index = self.domain.rank[dep]
        lo, hi, _ = slice(start, stop).indices(len(self))
        if not lo <= index < hi:
            raise ValueError(dep)
        return index


class Rank:
    def __init__(self, domain):
        self.domain = domain

    def __getitem__(self, dep):
        d = self.domain
        if dep in d.legacy_index:
            return d.legacy_index[dep]
        raw = d.raw(dep)
        return len(d.legacy_ids) + raw - bisect_right(d.legacy_raw_sorted, raw)


class CutDomain:
    def __init__(self, root, scope, rules, search):
        if scope not in ("extended", "legacy81"):
            raise ValueError(scope)
        self.scope = scope
        self.rules = rules
        self.root = root
        src = root / "research/kim_multidnn_expansion"
        metadata = json.loads((src / "catalog.json").read_bytes())
        self.legacy_ids = tuple(metadata["search_order"])
        self.legacy_index = {dep: i for i, dep in enumerate(self.legacy_ids)}
        self.old_search = search.Domain(metadata, self.legacy_ids) if scope == "legacy81" else None
        self.graphs = [rules.graph(str(i)) for i in range(N_APPS)]
        self.sizes = [len(graph[0]) for graph in self.graphs]
        self.cuts = []
        self.features_by_shape = []
        self.details = []
        self.symmetry = rules.symmetry_checks()

        for app, (ops, heads, kinds) in enumerate(self.graphs):
            old = {tuple(last for dev, _, last in chain if dev.startswith("DLA"))
                   for _, chain, _ in rules.SPECS[str(app)]}
            shapes = set(old)
            if scope == "extended":
                for end in range(len(ops) - 1):
                    if kinds[end] not in rules.DLA_ABSTRACT_KINDS:
                        break
                    if (kinds[end], kinds[end + 1]) != ("conv", "activation"):
                        shapes.add((end,))
            ordered = sorted(shapes, key=lambda shape: (len(shape), shape))
            self.cuts.append(ordered)
            details, features = [], []
            for shape in ordered:
                chain = _stages(len(ops), shape, 0)
                boundaries = rules.check_chain(str(app), chain)
                work = [sum(op.mac for op in ops[lo:hi+1]) for _, lo, hi in chain]
                # Inter-device cut tensors only. Request input and final output are
                # constant across shapes and remain included by profiles.build_chains.
                features.append((work[-1], tuple(work[:-1]), sum(c["bytes"] for c in boundaries)))
                details.append(dict(cuts=shape, retained_original=shape in old, handoffs=boundaries))
            self.details.append(details)
            self.features_by_shape.append(features)

        self.legacy_raw = {}
        self.raw_legacy = {}
        for dep in self.legacy_ids:
            stages = metadata["deployments"][dep]["stages"]
            layout = []
            for i in range(N_APPS):
                chain = stages[str(i)]
                shape = tuple(b for resource, _, b in chain if resource.startswith("DLA"))
                orientation = int(chain[0][0][-1]) if shape else 0
                layout.append((self.cuts[i].index(shape), orientation))
            raw = self._encode(tuple(layout))
            if self._decode(raw) != tuple(layout) or self._make_stages(layout) != stages:
                raise ValueError("legacy mapping drift: " + dep)
            if raw in self.raw_legacy:
                raise ValueError("duplicate original symmetry class")
            self.legacy_raw[dep], self.raw_legacy[raw] = raw, dep
        self.legacy_raw_sorted = sorted(self.raw_legacy)
        self.legacy_holes = [raw - i for i, raw in enumerate(self.legacy_raw_sorted)]
        self.size = self._count(0, SLOT_CAP, False)
        self.order = self.old_search.order if self.old_search else LazyOrder(self)
        self.rank = self.old_search.rank if self.old_search else Rank(self)
        if scope == "legacy81" and self.size != len(self.legacy_ids):
            raise ValueError("legacy domain cardinality mismatch")
        self.max_binding = (1 << (N_APPS - 1)) - 1
        self.options = [list(range(len(shapes))) for shapes in self.cuts]
        self.options.append(list(range(self.max_binding + 1)))

    @lru_cache(maxsize=None)
    def _count(self, app, available, seen):
        if app == N_APPS:
            return 1
        result = 0
        for shape in self.cuts[app]:
            if len(shape) <= available:
                orientations = 2 if shape and seen else 1
                result += orientations * self._count(app + 1, available - len(shape), seen or bool(shape))
        return result

    @lru_cache(maxsize=None)
    def _blocks(self, app, available, seen):
        ends, options, offsets = [], [], {}
        total = 0
        for idx, shape in enumerate(self.cuts[app]):
            if len(shape) > available:
                continue
            span = self._count(app + 1, available - len(shape), seen or bool(shape))
            for bit in range(2 if shape and seen else 1):
                option = (idx, bit)
                offsets[option] = total
                options.append(option)
                total += span
                ends.append(total)
        return ends, options, offsets

    @lru_cache(maxsize=8192)
    def _decode(self, raw):
        available, seen = SLOT_CAP, False
        layout = []
        for app in range(N_APPS):
            ends, options, offsets = self._blocks(app, available, seen)
            option = options[bisect_right(ends, raw)]
            layout.append(option)
            raw -= offsets[option]
            slots = len(self.cuts[app][option[0]])
            available -= slots
            seen = seen or bool(slots)
        return tuple(layout)

    @lru_cache(maxsize=8192)
    def _encode(self, layout):
        available, seen, raw = SLOT_CAP, False, 0
        for app, (shape, bit) in enumerate(_canonical(layout)):
            raw += self._blocks(app, available, seen)[2][shape, bit]
            slots = len(self.cuts[app][shape])
            available -= slots
            seen = seen or bool(slots)
        return raw

    def raw(self, dep):
        if dep in self.legacy_raw:
            return self.legacy_raw[dep]
        if not isinstance(dep, str) or self.scope != "extended" or not dep.startswith("X"):
            raise KeyError(dep)
        raw = int(dep[1:])
        if not 0 <= raw < self.size or self.ident(raw) != dep:
            raise KeyError(dep)
        return raw

    def ident(self, raw):
        return self.raw_legacy.get(raw, f"X{raw:07d}")

    def _make_stages(self, layout):
        return {str(i): _stages(self.sizes[i], self.cuts[i][idx], bit)
                for i, (idx, bit) in enumerate(layout)}

    def stages(self, dep):
        return self._make_stages(self._decode(self.raw(dep)))

    stages_for = stages

    def features(self, dep):
        result = {}
        for app, (idx, bit) in enumerate(self._decode(self.raw(dep))):
            gpu, dla, transfer = self.features_by_shape[app][idx]
            by_dla = [0, 0]
            for j, mac in enumerate(dla):
                by_dla[bit ^ j] = mac
            result[str(app)] = dict(gpu_mac=gpu, dla0_mac=by_dla[0], dla1_mac=by_dla[1],
                                    handoff_bytes=transfer)
        return result

    def _genes(self, dep):
        layout = self._decode(self.raw(dep))
        bits = [bit for idx, bit in layout if idx]
        binding = 0
        for bit in bits[1:]:
            binding = binding * 2 + bit
        return tuple(idx for idx, _ in layout) + (binding,)

    def child(self, first, second, rng, counts):
        # Legacy scope delegates even RNG consumption to the frozen operator.
        if self.old_search:
            return self.old_search.child(first, second, rng, counts)
        a, b = self._genes(first), self._genes(second)
        genes = list(a)
        if rng.random() < .8:
            genes = [rng.choice((x, y)) for x, y in zip(a, b, strict=True)]
        if rng.random() < .2:
            i = rng.randrange(5)
            options = [v for v in self.options[i] if v != genes[i]]
            if options:
                genes[i] = rng.choice(options)
        active = [i for i in range(N_APPS) if genes[i]]
        nbits = max(0, len(active) - 1)
        budget = sum(len(self.cuts[i][genes[i]]) for i in range(N_APPS))
        binding = genes[4]
        if budget > SLOT_CAP or binding >= 1 << nbits:
            counts["illegal_offspring"] += 1
            return rng.choice(self.order)
        bits = {i: (binding >> (nbits - j)) & 1 for j, i in enumerate(active[1:], 1)}
        return self.ident(self._encode(tuple((genes[i], bits.get(i, 0)) for i in range(N_APPS))))

    def neighbors(self, dep, k, rng, allow_exchange=True):
        """Return bounded, distinct graph edits. Canonicalization may relabel both DLAs globally."""
        if k <= 0:
            return []
        layout = self._decode(self.raw(dep))
        sizes = [len(self.cuts[i][idx]) for i, (idx, _) in enumerate(layout)]
        used = sum(sizes)
        singles, exchanges = {}, {}
        def offer(changes, action, pool):
            child = list(layout)
            for i, choice in changes:
                child[i] = choice
            key = self.ident(self._encode(tuple(child)))
            if key != dep:
                pool.setdefault(key, action)

        # Nearby cuts in topology order, plus a random long move and transitions
        # between zero, one and two slots. DLA labels change only where requested.
        transitions = []
        for app, (idx, bit) in enumerate(layout):
            shapes = self.cuts[app]
            prefix_end = len(shapes) - sum(len(s) == 2 for s in shapes)
            local = {0, *range(prefix_end, len(shapes)), rng.randrange(1, prefix_end)}
            for delta in (-3, -1, 1, 3):
                local.add(min(prefix_end-1, max(1, idx+delta)))
            if len(shapes[idx]) == 2:
                local.update(shapes.index((end,)) for end in shapes[idx] if (end,) in shapes)
            edits = []
            for new in sorted(local - {idx}):
                delta = len(shapes[new]) - sizes[app]
                for orient in ((0, 1) if not idx and new else (bit if new else 0,)):
                    choice = (new, orient)
                    edits.append((choice, delta))
                    if used + delta <= SLOT_CAP:
                        offer([(app, choice)], "cut", singles)
            transitions.append(edits)
            if idx:
                offer([(app, (idx, 1-bit))], "binding", singles)

        if allow_exchange:
            for donor in range(N_APPS):
                for receiver in range(N_APPS):
                    if donor == receiver:
                        continue
                    give = [v for v, delta in transitions[donor] if delta == -1]
                    take = [v for v, delta in transitions[receiver] if delta == 1]
                    for relinquish in give:
                        for acquire in take:
                            offer([(donor, relinquish), (receiver, acquire)], "exchange", exchanges)
                    a, b = layout[donor], layout[receiver]
                    if donor < receiver and a[0] and b[0] and a[1] != b[1]:
                        offer([(donor, (a[0], b[1])), (receiver, (b[0], a[1]))], "exchange", exchanges)
        # An exchange equivalent to a one-app edit up to global DLA relabeling
        # remains in the single-app neighborhood for the coordination ablation.
        for same in singles.keys() & exchanges.keys():
            del exchanges[same]
        pool_s, pool_x = list(singles.items()), list(exchanges.items())
        rng.shuffle(pool_s)
        rng.shuffle(pool_x)
        nx = min(len(pool_x), k//2)
        ns = min(len(pool_s), k-nx)
        return pool_s[:ns] + pool_x[:min(k-ns, len(pool_x))]

    def manifest(self):
        counts = Counter({0: 1})
        for shapes in self.cuts:
            next_counts = Counter()
            for used, n in counts.items():
                for shape in shapes:
                    total = used + len(shape)
                    if total <= SLOT_CAP:
                        next_counts[total] += n * (2 if shape else 1)
            counts = next_counts
        physical = sum(counts.values())
        if (physical + 1) // 2 != self.size:
            raise ValueError("DP count disagrees with independent global-swap orbit count")
        inputs = ["kim_multidnn_expansion/catalog.py", "kim_multidnn_expansion/catalog.json",
                  "kim_case_b_freeze/input.json", "kim_synthetic_platform_v1/platform.json",
                  "kim_synthetic_platform_v1/profiles.py", "kim_synthetic_platform_v1/events.py"]
        return dict(scope=self.scope, all_resident_dla_stage_cap=SLOT_CAP,
                    rule="GPU-only, all DLA-compatible non-fused prefix endpoints then GPU suffix in extended; retain original two-DLA structures. All four networks resident; all relative DLA bindings; global DLA swap quotient.",
                    omitted="Internal GPU/DLA/GPU and newly designed two-DLA splits are outside this defined domain; no engine build or numerical output validation.",
                    physical_by_resident_stages=dict(sorted(counts.items())),
                    physical_assignments=physical, representatives=self.size, original_count=len(self.legacy_ids),
                    new_representatives=self.size-len(self.legacy_ids), frequency_codes_per_rep=27**4,
                    per_app_shapes=self.details, original_ids_and_raw_ranks=self.legacy_raw,
                    symmetry_checks=self.symmetry,
                    source_sha256={p: sha256((self.root / "research" / p).read_bytes()).hexdigest() for p in inputs})


def make_domain(root, scope="extended"):
    root = Path(root).resolve()
    research = root / "research"
    for folder in [research / "kim_multidnn_expansion", HERE.parent / "ch3_final_experiments/p2"]:
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))
    rules = import_module("catalog")
    if Path(rules.__file__).resolve() != research / "kim_multidnn_expansion/catalog.py":
        raise ValueError("frozen catalog import does not match configured input root")
    return CutDomain(root, scope, rules, import_module("search"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=HERE / "catalog_manifest.json")
    args = parser.parse_args()
    domain = make_domain(args.source_root)
    manifest = domain.manifest()
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8", newline="\n")
    print(f"{manifest['physical_assignments']} physical / {domain.size} representative deployments")

