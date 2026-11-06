import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REFERENCE = 'fr'
I18N_DIR = ROOT / 'i18n'
TEMPLATE = ROOT / 'templates' / 'index.html.j2'
JS_DIR = ROOT / 'js'
PLURAL_FORMS = {'zero', 'one', 'two', 'few', 'many', 'other'}
PLACEHOLDER = re.compile(r'\{(\w+)\}')
KEY_IN_JS = re.compile(r"""\bt\(\s*'([^']+)'|\b\w+Key:\s*'([^']+)'""")
KEY_IN_TEMPLATE = re.compile(r"""\bt\(\s*'([^']+)'\s*\)""")
FRENCH_LETTERS = re.compile(r'[À-ÖØ-öø-ÿŒœ]')
STRING_LITERAL = re.compile(r"""'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`""")
JINJA_BLOCK = re.compile(r'\{\{.*?\}\}|\{%.*?%\}', re.S)
SCRIPT_OR_STYLE = re.compile(r'<(script|style)\b.*?</\1>', re.S | re.I)
TEXT_NODE = re.compile(r'>([^<]+)<')
TEXT_ATTRIBUTE = re.compile(r'\b(title|aria-label|placeholder|alt)="([^"]*)"')
WORD = re.compile(r'[A-Za-zÀ-ÖØ-öø-ÿŒœ]{2,}')
TEMPLATE_ALLOWED_WORDS = {'OSM', 'UrbIS'}


def placeholders(value):
    texts = value.values() if isinstance(value, dict) else [value]
    return {name for text in texts for name in PLACEHOLDER.findall(text)}


def check_value(lang, key, value, ref_value, errors):
    if isinstance(ref_value, dict):
        if not isinstance(value, dict):
            errors.append(f'{lang}.json : « {key} » doit avoir des formes de pluriel')
            return
        if 'other' not in value or not set(value) <= PLURAL_FORMS:
            errors.append(f'{lang}.json : « {key} » doit avoir la forme « other » et seulement des formes valides')
    elif not isinstance(value, str):
        errors.append(f'{lang}.json : « {key} » doit être un texte')
        return
    if placeholders(value) != placeholders(ref_value):
        errors.append(f'{lang}.json : « {key} » n’a pas les mêmes variables que {REFERENCE}.json')
    texts = value.values() if isinstance(value, dict) else [value]
    if any(not text.strip() for text in texts):
        errors.append(f'{lang}.json : « {key} » est vide')


def used_keys():
    keys = {}
    for path in sorted(JS_DIR.glob('*.js')):
        for match in KEY_IN_JS.finditer(path.read_text(encoding='utf-8')):
            keys.setdefault(match.group(1) or match.group(2), path.name)
    for match in KEY_IN_TEMPLATE.finditer(TEMPLATE.read_text(encoding='utf-8')):
        keys.setdefault(match.group(1), TEMPLATE.name)
    for key in ('banner.text', 'banner.switch', 'banner.dismiss'):
        keys.setdefault(key, 'build-site.py')
    return keys


def hardcoded_french():
    found = []
    for path in sorted(JS_DIR.glob('*.js')):
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if 'console.' in line:
                continue
            for literal in STRING_LITERAL.findall(line):
                if FRENCH_LETTERS.search(literal):
                    found.append(f'{path.name}:{number} : {literal[:60]}')
    template = SCRIPT_OR_STYLE.sub('', JINJA_BLOCK.sub('', TEMPLATE.read_text(encoding='utf-8')))
    texts = [m.group(1) for m in TEXT_NODE.finditer(template)]
    texts += [m.group(2) for m in TEXT_ATTRIBUTE.finditer(template)]
    for text in texts:
        words = [w for w in WORD.findall(re.sub(r'&#?\w+;', '', text)) if w not in TEMPLATE_ALLOWED_WORDS]
        if words:
            found.append(f'{TEMPLATE.name} : « {" ".join(text.split())[:60]} »')
    return found


def main():
    errors = []
    warnings = []
    dictionaries = {}
    for path in sorted(I18N_DIR.glob('*.json')):
        try:
            dictionaries[path.stem] = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            errors.append(f'{path.name} : JSON invalide ({e})')
    reference = dictionaries.get(REFERENCE)
    if reference is None:
        errors.append(f'{REFERENCE}.json introuvable')
    else:
        for lang, strings in dictionaries.items():
            for key in sorted(set(reference) - set(strings)):
                errors.append(f'{lang}.json : clé manquante « {key} »')
            for key in sorted(set(strings) - set(reference)):
                errors.append(f'{lang}.json : clé inconnue de {REFERENCE}.json « {key} »')
            for key in sorted(set(reference) & set(strings)):
                check_value(lang, key, strings[key], reference[key], errors)
        keys = used_keys()
        for key, origin in sorted(keys.items()):
            if key not in reference:
                errors.append(f'{origin} utilise la clé « {key} », absente de {REFERENCE}.json')
        for key in sorted(set(reference) - set(keys)):
            warnings.append(f'clé inutilisée « {key} »')
    for item in hardcoded_french():
        errors.append(f'texte en dur : {item}')
    for warning in warnings:
        print(f'[ATTENTION] {warning}')
    for error in errors:
        print(f'[ERREUR] {error}')
    if errors:
        sys.exit(1)
    print(f'[OK] {len(dictionaries)} langues, {len(reference)} clés, aucune erreur')


if __name__ == '__main__':
    main()
