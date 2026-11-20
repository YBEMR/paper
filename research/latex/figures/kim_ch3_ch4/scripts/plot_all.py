"""Render the thesis figures from the CSVs shipped with this folder."""
from pathlib import Path
import subprocess
import sys


if __name__ == "__main__":
    scripts = Path(__file__).resolve().parent
    for script in (
        "plot_mechanisms.py",
        "power_traces.py",
        "plot_energy_pressure.py",
        "make_timings.py",
        "plot_progress.py",
    ):
        subprocess.run([sys.executable, str(scripts / script)], check=True)
