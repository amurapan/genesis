import hashlib
import platform
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def source_fingerprint():
    files=[p for d in ['src','tests','schemas','configs','containers','fixtures'] for p in (ROOT/d).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    files += [ROOT/n for n in ['verify.sh','pyproject.toml','requirements.lock']]
    result=hashlib.sha256()
    for p in sorted(files): result.update(str(p.relative_to(ROOT)).encode()+b'\0'+p.read_bytes()+b'\0')
    return result.hexdigest()


def image_metadata(name):
    import json
    value=json.loads(subprocess.check_output(['docker','image','inspect',name],text=True))[0]
    return dict(name=name,id=value['Id'],size_bytes=value['Size'],labels=value['Config'].get('Labels',{}))


def versions():
    try:
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
        dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True))
    except subprocess.CalledProcessError: revision=None; dirty=None
    return dict(source_sha256=source_fingerprint(),revision=revision,uncommitted_changes=dirty,python=platform.python_version(),platform=platform.platform(),
                schema_version='1.0.0',generator_version='1.0.0',config_version='1.0.0',
                images=[image_metadata('sled-agent:1.0.0'),image_metadata('sled-core:1.0.0')])
