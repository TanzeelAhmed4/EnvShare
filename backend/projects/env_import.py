import re


KEY_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def parse_env_content(content):
    """Parse simple KEY=VALUE dotenv entries without logging or echoing input values."""
    entries = []
    errors = []
    seen = set()

    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if '=' not in raw_line:
            errors.append({'line': line_number, 'message': 'Expected KEY=VALUE.'})
            continue

        raw_key, raw_value = raw_line.split('=', 1)
        key = raw_key.strip()
        value = raw_value.strip()
        if not KEY_PATTERN.fullmatch(key):
            errors.append({'line': line_number, 'message': 'Invalid variable key.'})
            continue
        if key in seen:
            errors.append({'line': line_number, 'message': 'Duplicate key in imported text.'})
            continue

        if value.startswith(('"', "'")):
            quote = value[0]
            if len(value) < 2 or not value.endswith(quote):
                errors.append({'line': line_number, 'message': 'Quoted value is not closed.'})
                continue
            value = value[1:-1]
        seen.add(key)
        entries.append({'key': key, 'value': value, 'line': line_number})

    return entries, errors
