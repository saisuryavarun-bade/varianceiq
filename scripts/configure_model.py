"""Enter a provider key locally, with terminal echo disabled."""
import getpass
from pathlib import Path
import warnings

ROOT = Path(__file__).resolve().parents[1]


def main():
    path = ROOT / '.env'
    existing = path.read_text(encoding='utf-8') if path.exists() else ''
    if any(line.strip().startswith('OPENAI_API_KEY=') for line in existing.splitlines()):
        raise SystemExit('A key entry already exists in .env. Edit it locally to replace it.')
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        key = getpass.getpass('OpenAI API key (hidden; never paste into chat): ').strip()
    if not key or any(c.isspace() for c in key) or not all(c.isalnum() or c in '-_' for c in key):
        raise SystemExit('Invalid key format; nothing saved.')
    with path.open('a', encoding='utf-8') as handle:
        handle.write(('\n' if existing and not existing.endswith('\n') else '') + 'OPENAI_API_KEY=' + key + '\n')
    print('Saved to the ignored local .env file. Restart the application to load it.')


if __name__ == '__main__':
    main()
