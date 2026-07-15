import re
import pathlib

root = pathlib.Path('backend/api/migrations')
files = {p.stem for p in root.glob('*.py') if p.name != '__init__.py'}
missing = []
for p in root.glob('*.py'):
    if p.name == '__init__.py':
        continue
    text = p.read_text(encoding='utf-8')
    for m in re.finditer(r"\('api',\s*'([^']+)'\)", text):
        dep = m.group(1)
        if dep not in files:
            missing.append((p.name, dep))

uniq = sorted(set(missing))
if not uniq:
    print('OK all api migration deps present')
else:
    print('MISSING:')
    for f, d in uniq:
        print(f'  {f} -> {d}')
