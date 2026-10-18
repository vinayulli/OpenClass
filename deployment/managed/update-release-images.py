"""Select built images without changing live identities, access or bootstrap mode."""
import argparse
import base64
import io
import json
from pathlib import Path
import tarfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agents', nargs='*', choices=['teacher', 'tutor', 'exam', 'path', 'code', 'intervention', 'web'], default=[])
    parser.add_argument('--web', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    target = root/'deployment/managed/release.auto.tfvars.json'
    original = target.read_text(encoding='utf-8')
    values = json.loads(original)
    images = json.loads((root/'deployment/generated/images.json').read_text())
    if args.agents:
        content = ('FROM '+images['runtime']+'\n').encode()
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w:gz') as bundle:
            item = tarfile.TarInfo('Dockerfile')
            item.size = len(content)
            item.mode = 0o644
            bundle.addfile(item, io.BytesIO(content))
        for kind in args.agents:
            values['runtime_source_archives'][kind] = base64.b64encode(archive.getvalue()).decode()
    if args.web:
        values['web_image'] = images['web']
    (root/'deployment/generated/pre-image-update.tfvars.json').write_text(original, encoding='utf-8')
    target.write_text(json.dumps(values, indent=2)+'\n', encoding='utf-8')
    print('Selected runtime image for:', ', '.join(args.agents) or 'none', '; web image updated:', args.web)


if __name__ == '__main__':
    main()
