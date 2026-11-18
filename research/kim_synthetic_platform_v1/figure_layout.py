"""Keep the generated energy heading clear of its key and normalize SVG whitespace."""
from pathlib import Path


def main():
    folder = Path(__file__).resolve().parent / "figures"
    for name in ("temperature", "energy", "feasibility"):
        path = folder / f"{name}.svg"
        svg = path.read_text(encoding="utf-8")
        if name == "energy":
            full = ">10-second service | feasible selections on continuous replay</text>"
            short = ">10-second service | continuous replay</text>"
            if svg.count(full) + svg.count(short) != 1:
                raise ValueError("Unexpected energy figure title")
            svg = svg.replace(full, short)
        # Newlines continue to separate the numbers in multiline SVG path data.
        path.write_bytes(("\n".join(line.rstrip() for line in svg.splitlines())+"\n").encode("utf-8"))


if __name__ == "__main__":
    main()
