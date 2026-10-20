"""Trim already exported CSV only; never reconstruct a model."""
import csv
from pathlib import Path

folder = Path(__file__).resolve().parent
source = folder / 'rows.csv'
temporary = folder / 'rows.trim.csv'
fields = ['row_zero_based', 'tag', 'rhs', 'Ax0_minus_b']
with source.open(encoding='utf-8', newline='') as src, temporary.open(
        'w', encoding='utf-8', newline='') as dst:
    reader = csv.DictReader(src)
    writer = csv.DictWriter(dst, fields, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(reader)
temporary.replace(source)
print(source.stat().st_size)
