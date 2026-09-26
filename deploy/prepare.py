"""Run on the VPS with the shared Hermes venv. Prepares but never starts services."""
import os
import shutil
from pathlib import Path

import yaml
from dotenv import dotenv_values, set_key
from hermes_cli.default_soul import DEFAULT_SOUL_MD, is_legacy_template_soul

ROOT = Path(__file__).resolve().parents[1]
HOME = Path('/home/hermes/.hermes-tutor')
WORKSPACE = Path('/home/hermes/workspace/tutor-workspace')
MAIN = Path('/home/hermes/.hermes')


def main():
    os.umask(0o077)
    # Native profile layout enables Hermes's lock-aware shared OAuth fallback.
    profile = MAIN / 'profiles/tutor'
    profile.parent.mkdir(parents=True, exist_ok=True)
    if HOME.is_dir() and not HOME.is_symlink() and not profile.exists():
        HOME.rename(profile)
    profile.mkdir(parents=True, exist_ok=True)
    if not HOME.exists():
        HOME.symlink_to(profile, target_is_directory=True)
    if HOME.resolve() != profile.resolve():
        raise ValueError('Tutor home exists at an unexpected path; inspect before continuing')
    HOME.mkdir(parents=True, exist_ok=True)
    HOME.chmod(0o700)
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    for name in ('cron', 'logs', 'sessions', 'memories', 'skills', 'plugins'):
        (HOME / name).mkdir(exist_ok=True)
    original = yaml.safe_load((MAIN / 'config.yaml').read_text())
    config = {
        'model': original['model'],
        'toolsets': ['tutor'],
        'platform_toolsets': {'telegram': ['tutor'], 'cli': ['tutor']},
        'terminal': {'backend': 'local', 'cwd': str(WORKSPACE)},
        'gateway': {'multiplex_profiles': False, 'auto_migrate': False},
        'plugins': {'enabled': ['hermes-tutor']},
    }
    # Never reset user customizations during an upgrade.
    if not (HOME / 'config.yaml').exists():
        (HOME / 'config.yaml').write_text(yaml.safe_dump(config, allow_unicode=True))
    for destination in (HOME / 'SOUL.md', WORKSPACE / 'SOUL.md'):
        current = destination.read_text() if destination.exists() else ''
        if not current or current.strip() == DEFAULT_SOUL_MD.strip() or is_legacy_template_soul(current):
            shutil.copy2(ROOT / 'workspace/SOUL.md', destination)
    env = HOME / '.env'
    env.touch(mode=0o600, exist_ok=True)
    env.chmod(0o600)
    values = dotenv_values(MAIN / '.env')
    owner = values.get('TELEGRAM_ALLOWED_USERS', '')
    if not owner.isdigit():
        raise ValueError('Specify one numeric Telegram owner before installation')
    existing = dotenv_values(env)
    for key, value in {'TUTOR_OWNER_ID': owner, 'TELEGRAM_ALLOWED_USERS': owner,
                       'TELEGRAM_HOME_CHANNEL': owner, 'GATEWAY_ALLOW_ALL_USERS': 'false'}.items():
        if key not in existing:
            set_key(str(env), key, value, quote_mode='never')
    if 'TELEGRAM_BOT_TOKEN' not in existing:
        set_key(str(env), 'TELEGRAM_BOT_TOKEN', '', quote_mode='never')
    # Use Hermes's supported global OAuth fallback. Do not copy refresh tokens.
    plugin = HOME / 'plugins/hermes-tutor'
    if plugin.is_symlink() and plugin.resolve() != ROOT / 'hermes_tutor':
        plugin.unlink()
    if not plugin.exists():
        plugin.symlink_to(ROOT / 'hermes_tutor', target_is_directory=True)
    units = Path('/home/hermes/.config/systemd/user')
    units.mkdir(parents=True, exist_ok=True)
    for source in (ROOT / 'deploy').glob('hermes-tutor*.*'):
        if source.suffix in ('.service', '.timer'):
            shutil.copy2(source, units / source.name)
    print('Prepared isolated tutor home, workspace and services. No services started.')
    print('Telegram bot token present:', bool(dotenv_values(env).get('TELEGRAM_BOT_TOKEN')))


if __name__ == '__main__':
    main()
