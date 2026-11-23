import json
from pathlib import Path

DOMAIN_SPEC = json.loads((Path(__file__).parents[1] / 'domain' / 'spec.json').read_text(encoding='utf-8'))
PROJECT = json.loads(Path(__file__).with_name('identity.json').read_text(encoding='utf-8'))
SPEC = {**DOMAIN_SPEC, **PROJECT}
