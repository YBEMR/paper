"""Protected precheck for the fixed original/deadline-fallback pair."""
from e2_resources.precheck import main
from .protocol import PROTOCOL_ID
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',required=True)
    main(p.parse_args().out,protocol_id=PROTOCOL_ID)
