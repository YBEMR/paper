"""Recompute published-power ratios. Python standard library only; no simulation."""
from pathlib import Path
from fractions import Fraction
import json

data = json.loads(Path(__file__).with_name('evidence.json').read_text(encoding='utf-8'))
for row in data['table10']:
    ratio = Fraction(row['reported_power_on_W']) / Fraction(row['reported_power_off_W'])
    assert ratio == Fraction(row['ratio_on_over_off_exact'])
    assert row['same_service_energy_saving_percent'] is None
    assert row['all_frames_meet_deadlines'] is None
    print(f"{row['board_as_reported']}, {row['streams']} streams: "
          f"P_on/P_off={float(ratio):.8f}; power change={float((ratio-1)*100):+.4f}%")
print('PASS: six power ratios. Same-service energy and deadline outcomes remain unknown.')
