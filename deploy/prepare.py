"""Run with the tutor runtime's venv. Prepares but never starts services."""
import os
import shutil
from pathlib import Path

import yaml
from dotenv import dotenv_values, set_key
from hermes_cli.default_soul import DEFAULT_SOUL_MD, is_legacy_template_soul

ROOT = Path(__file__).resolve().parents[1]
HOME = Path('/home/hermes/.hermes-tutor')
WORKSPACE = Path('/home/hermes/workspace/tutor-workspace')


def main():
    os.umask(0o077)
    os.environ['HERMES_HOME'] = str(HOME)
    if HOME.is_symlink():
        raise ValueError('Migrate the old profile to a real standalone tutor home first')
    HOME.mkdir(parents=True, exist_ok=True)
    HOME.chmod(0o700)
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    for name in ('cron', 'logs', 'sessions', 'memories', 'skills', 'plugins'):
        (HOME / name).mkdir(exist_ok=True)
    config = {
        'model': {'default': 'gpt-5.6-sol', 'provider': 'openai-codex',
                  'base_url': 'https://chatgpt.com/backend-api/codex'},
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
    existing = dotenv_values(env)
    owner = existing.get('TUTOR_OWNER_ID') or os.environ.get('TUTOR_OWNER_ID', '')
    if not owner.isdigit():
        raise ValueError('Specify one numeric Telegram owner before installation')
    for key, value in {'TUTOR_OWNER_ID': owner, 'TELEGRAM_ALLOWED_USERS': owner,
                       'TELEGRAM_HOME_CHANNEL': owner, 'GATEWAY_ALLOW_ALL_USERS': 'false'}.items():
        if key not in existing:
            set_key(str(env), key, value, quote_mode='never')
    if 'TELEGRAM_BOT_TOKEN' not in existing:
        set_key(str(env), 'TELEGRAM_BOT_TOKEN', '', quote_mode='never')
    # Each standalone home owns its credentials. Never import another instance's OAuth.
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
    override = units / 'hermes-tutor.service.d'
    override.mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'deploy/hermes-tutor.service.d/tutor.conf', override / 'tutor.conf')
    from hermes_cli.gateway import get_service_name
    alias = units / (get_service_name() + '.service')
    unit = units / 'hermes-tutor.service'
    if alias.exists() or alias.is_symlink():
        if alias.resolve() != unit.resolve():
            raise ValueError('Native gateway alias already belongs to another service')
    else:
        alias.symlink_to(unit.name)
    wrapper = Path('/home/hermes/.local/bin/hermes-tutor')
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text('#!/bin/sh\nexport HERMES_HOME=/home/hermes/.hermes-tutor\n'
                       'exec /home/hermes/runtimes/hermes-tutor/venv/bin/python -m hermes_cli.main "$@"\n')
    wrapper.chmod(0o700)
    print('Prepared isolated tutor home, workspace and services. No services started.')
    print('Telegram bot token present:', bool(dotenv_values(env).get('TELEGRAM_BOT_TOKEN')))


if __name__ == '__main__':
    main()
