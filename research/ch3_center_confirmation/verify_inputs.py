"""Read-only preflight, with no search, warm-up plan, or experimental cell."""
import hashlib
import os
from pathlib import Path

from lane import CASES
from cold_cell import m

ROOT = Path(__file__).resolve().parents[2]
PINS = {
    "research/ch3_integrated_quality_v1/trial.py": "27b02c54ce703d49677d87782aa8e58004395bc4",
    "research/ch3_integrated_quality_v2/trial.py": "54f0f0a7cf41d7ac1fd240dc0507f57385b8c62c",
    "research/ch3_integrated_quality_v3/hot.py": "0c179fb335ad0cb2f164f43f238aaa5c5dc0a441",
    "research/ch3_integrated_quality_v3/online.py": "a25f8606b0fa9c1aa2bd80224d48acd8267f5354",
    "research/m6a_global_frequency_mapping/dp.cpp": "8e94c6f638442108f4dc9be61e0b5f07ac4efae9",
    "research/ch3_center_only/simplified.py": "94e586fdb7fe83aa263a3b8b2513a6e5fc25dba5",
    "research/ch3_analytic_quota/method.py": "5358b991316c34c024f9455fe95ffcbf2cb6f076"
}


def main():
    for path,expected in PINS.items():
        data=(ROOT/path).read_bytes()
        assert hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()==expected,path
    assert tuple(m.label(o) for o in m.u2.CASES)==CASES
    api=m.u2.stack()[0]
    assert api.e.p1.P1=="be641ce06a4f496d2b1f233a09bdfc3776738668"
    from simplified import expand
    assert Path(expand.__code__.co_filename).resolve()==ROOT/"research/ch3_center_only/simplified.py"
    assert "m1e_thermal_quota_ablation" in api.e.expand.__code__.co_filename
    for obj in m.u2.CASES:
        path=Path(os.environ["GEN"])/"research/m1i_generalization/registration/inputs"/obj["input"]
        assert obj["ambient"]==35 and hashlib.sha256(path.read_bytes()).hexdigest()==obj["input_sha256"]
    print("12 registered streams, frozen fit, frozen center-only and shared physical model verified")


if __name__=="__main__":
    main()
