"""Run the complete regression suite and persist executed, not inferred, results."""
import argparse
import time
import unittest
from .metadata import ROOT,source_fingerprint
from .storage import write_json


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',default='artifacts/unit-tests.json');args=p.parse_args()
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    started=time.monotonic(); result=unittest.TextTestRunner(verbosity=1).run(suite)
    report=dict(source_sha256=source_fingerprint(),run=result.testsRun,passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
                skipped=len(result.skipped),failures=[str(t) for t,_ in result.failures],errors=[str(t) for t,_ in result.errors],seconds=time.monotonic()-started)
    write_json(args.output,report)
    if not result.wasSuccessful() or result.skipped: raise SystemExit(1)
if __name__=='__main__':main()
