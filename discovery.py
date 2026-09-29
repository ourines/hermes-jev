"""Read the current Hermes provider catalog and turn it into Jev candidates."""
from __future__ import annotations

import re

from .routing import MAX_CANDIDATES, validate_candidates


MAX_DISCOVERED = 8
_VARIANT_SUFFIXES = ('-900k', ':batch', '-batch')
_FAST = ('mini', 'flash', 'luna', 'haiku', 'nano', 'lite', 'small')
_STRONG = ('pro', 'opus', 'sol', 'ultra', 'max', 'reasoning', 'astra')
_BALANCED = ('codex', 'sonnet', 'terra', 'medium')
_SKIP = ('image', 'video', 'whisper', 'tts', 'embed', 'moderation', 'dall-e', 'dalle', 'flux', 'imagen')
_ID = re.compile(r'[^a-zA-Z0-9._-]+')


def truthy(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return False


def _slug(model):
    return str(model).strip().split('/')[-1]


def _route_id(model, used):
    base = _ID.sub('-', _slug(model)).strip('.-')[:64] or 'model'
    candidate = base
    index = 2
    while candidate in used:
        suffix = f'-{index}'
        candidate = (base[:64 - len(suffix)] + suffix)
        index += 1
    used.add(candidate)
    return candidate


def _skip_model(model):
    slug = _slug(model).lower()
    if not slug or any(slug.endswith(suffix) for suffix in _VARIANT_SUFFIXES):
        return True
    return any(token in slug for token in _SKIP)


def describe_model(model):
    slug = _slug(model).lower()
    if any(token in slug for token in _FAST):
        return 'Fast, cheaper model for simple questions, formatting and small edits.'
    if any(token in slug for token in _STRONG):
        return 'Higher-capability model for complex debugging, architecture and long reasoning.'
    if any(token in slug for token in _BALANCED):
        return 'Balanced coding model for multi-file work and routine engineering.'
    return f'Hermes model {model} on the current provider.'


def _rank(model, current):
    slug = _slug(model).lower()
    if model == current or slug == _slug(current or '').lower():
        return 0
    if any(token in slug for token in _FAST):
        return 1
    if any(token in slug for token in _STRONG):
        return 2
    if any(token in slug for token in _BALANCED):
        return 3
    return 4


def candidates_from_models(models, *, provider='', current_model='', limit=MAX_DISCOVERED):
    """Build 2-32 unique described profiles from a Hermes model id list."""
    if not isinstance(models, list):
        return []
    usable = []
    seen = set()
    for model in models:
        if not isinstance(model, str) or _skip_model(model):
            continue
        key = model.strip()
        if key in seen:
            continue
        seen.add(key)
        usable.append(key)
    if current_model and isinstance(current_model, str) and current_model.strip() and current_model.strip() not in seen:
        if not _skip_model(current_model):
            usable.insert(0, current_model.strip())
    usable.sort(key=lambda model: (_rank(model, current_model), model))
    usable = usable[: max(2, min(int(limit or MAX_DISCOVERED), MAX_CANDIDATES))]
    used_ids = set()
    raw = []
    for model in usable:
        item = {
            'id': _route_id(model, used_ids),
            'model': model,
            'description': describe_model(model),
        }
        if provider:
            item['provider'] = provider
        raw.append(item)
    if len(raw) < 2:
        return []
    return validate_candidates(raw)

def candidates_from_inventory(inventory, *, limit=MAX_DISCOVERED):
    """Build bounded route profiles from authenticated Hermes model options."""
    if not isinstance(inventory, dict):
        return []
    providers = inventory.get('providers')
    if not isinstance(providers, list):
        return []
    current_provider = inventory.get('provider') or ''
    current_model = inventory.get('model') or ''
    seen_pairs = set()
    used_ids = set()
    ranked = []
    for row in providers:
        if not isinstance(row, dict) or row.get('authenticated') is not True:
            continue
        provider = row.get('slug')
        models = row.get('models')
        if not isinstance(provider, str) or not provider or not isinstance(models, list):
            continue
        provider_models = []
        for entry in models:
            model = entry if isinstance(entry, str) else entry.get('id') if isinstance(entry, dict) else None
            if not isinstance(model, str) or _skip_model(model):
                continue
            model = model.strip()
            pair = (provider, model)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            provider_models.append(model)
        provider_models.sort(key=lambda model: (_rank(model, current_model) if provider == current_provider else _rank(model, ''), model))
        for model in provider_models[:4]:
            ranked.append((provider, model))
    ranked.sort(key=lambda pair: (0 if pair == (current_provider, current_model) else 1, pair[0], _rank(pair[1], current_model if pair[0] == current_provider else ''), pair[1]))
    candidates = [{
        'id': _route_id(f'{provider}-{model}', used_ids),
        'model': model,
        'provider': provider,
        'description': describe_model(model),
    } for provider, model in ranked[:max(2, min(int(limit or MAX_DISCOVERED), MAX_CANDIDATES))]]
    return validate_candidates(candidates) if len(candidates) >= 2 else []


def read_hermes_runtime(provider=None):
    """Read non-secret current provider/model and cached catalog. Fail closed to empty."""
    runtime = {'provider': provider or '', 'current_model': '', 'models': []}
    try:
        from hermes_cli.config import load_config_readonly
        from hermes_cli.models import cached_provider_model_ids
    except Exception:
        return runtime
    try:
        config = load_config_readonly() or {}
        model_cfg = config.get('model') if isinstance(config, dict) else {}
        if not isinstance(model_cfg, dict):
            model_cfg = {}
        runtime['provider'] = provider or model_cfg.get('provider') or ''
        runtime['current_model'] = model_cfg.get('default') or model_cfg.get('model') or model_cfg.get('name') or ''
        if runtime['provider']:
            runtime['models'] = list(cached_provider_model_ids(runtime['provider']) or [])
    except Exception:
        return runtime
    return runtime

def read_hermes_inventory():
    """Read the active profile's authenticated model picker inventory without a live probe."""
    try:
        from hermes_cli.inventory import build_model_options_payload, load_picker_context
        return build_model_options_payload(
            load_picker_context(), explicit_only=True, include_unconfigured=False,
            refresh=False,
        )
    except Exception:
        return {}
