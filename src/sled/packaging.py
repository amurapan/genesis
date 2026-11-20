"""Create a portable offline submission from verified source and actual reports."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile
from .metadata import ROOT,source_fingerprint
from .storage import write_json


def build(report_dir, output):
    report_dir=Path(report_dir).resolve(); output=Path(output).resolve()
    report=json.loads((report_dir/'report.json').read_text())
    if report['versions']['source_sha256']!=source_fingerprint() or not report['technical_gates_passed']:
        raise ValueError('A successful verification of current source is required')
    demo=ROOT/'artifacts/demo-release'
    for name in ['demo.mp4','presentation.pdf','media-tools.json']:
        if not (demo/name).is_file():raise ValueError('Missing demo artifact: '+name)
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sled-package-') as temp:
        folder=Path(temp)
        directories=['src','tests','fixtures','data','configs','schemas','containers','planning','docs','scripts']
        for name in directories:
            shutil.copytree(ROOT/name,folder/'source'/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        for name in ['demo','verification']:
            if (ROOT/name).exists():shutil.copytree(ROOT/name,folder/'source'/name)
        for name in ['README.md','LICENSE','pyproject.toml','requirements.lock','verify.sh','.dockerignore','.gitignore','.gitattributes']:
            shutil.copy2(ROOT/name,folder/'source'/name)
        shutil.copytree(report_dir,folder/'verification')
        shutil.copy2(ROOT/'artifacts/unit-tests.json',folder/'verification/unit-tests.json')
        shutil.copy2(report_dir/'trajectories.jsonl',folder/'trajectories.jsonl')
        shutil.copytree(demo,folder/'demo',ignore=shutil.ignore_patterns('frames'))
        shutil.copy2(demo/'demo.mp4',folder/'demo.mp4')
        shutil.copy2(demo/'presentation.pdf',folder/'presentation.pdf')
        (folder/'GitHub.txt').write_text('https://github.com/amurapan/genesis\n')
        (folder/'START.txt').write_text('evidable / GENESIS FinTech\nLinux + Python 3.11 + Docker (cgroup v2).\nRun: bash run-offline.sh\nReport: verification/report.html\nEngineering criteria I01-I05 require human review.\nThis archive is not an official submission confirmation.\n')
        # docker save includes shared layers once; gzip is a packaging tool, not a dependency.
        with (folder/'images.tar.gz').open('wb') as raw:
            with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0,compresslevel=6) as compressed:
                process=subprocess.Popen(['docker','save','sled-agent:1.0.0','sled-core:1.0.0'],stdout=subprocess.PIPE)
                try:shutil.copyfileobj(process.stdout,compressed)
                finally:process.stdout.close()
                if process.wait()!=0:raise RuntimeError('docker save failed')
        launcher='''#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 - <<'PY'
import hashlib,json
from pathlib import Path
manifest=json.loads(Path('artifact_manifest.json').read_text())
for name,expected in manifest['sha256'].items():
    actual=hashlib.sha256(Path(name).read_bytes()).hexdigest()
    if actual!=expected:raise SystemExit('Checksum mismatch: '+name)
print('Artifact checksums verified')
PY
docker load -i images.tar.gz
cd source
bash verify.sh --offline
'''
        (folder/'run-offline.sh').write_text(launcher)
        checksums={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob('*')) if p.is_file()}
        uncompressed=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())
        # Count loaded image size conservatively (shared base counted twice), plus artifacts.
        loaded=sum(i['size_bytes'] for i in report['versions']['images'])+uncompressed
        if loaded>=1_000_000_000:raise ValueError('Conservative installed size exceeds 1 GB')
        write_json(folder/'artifact_manifest.json',dict(source_sha256=source_fingerprint(),sha256=checksums,
                    artifact_bytes=uncompressed,conservative_installed_bytes=loaded,
                    note='Manifest excludes itself. Image sizes double-count shared layers.'))
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for p in sorted(folder.rglob('*')):
                if p.is_file():archive.write(p,str(p.relative_to(folder)))
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.zip.sha256').write_text(digest+'  '+output.name+'\n')
    print(json.dumps(dict(archive=str(output),bytes=output.stat().st_size,sha256=digest,conservative_installed_bytes=loaded)))
