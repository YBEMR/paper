"""Exactly one archived-payload equality-representation diagnostic; no sweep or retry."""
from pathlib import Path
import replay_once as replay

replay.ENTRY_FILE = Path(__file__).resolve()
replay.REPRESENTATION = replay.EQUALITY_REPRESENTATION
replay.OUT = replay.SCIENCE / 'results/natural_full_equalities_repair01'
replay.PRECHECK = replay.SCIENCE / 'results/natural_full_equalities_precheck01.json'

if __name__ == '__main__':
    raise SystemExit(replay.main() or 0)
