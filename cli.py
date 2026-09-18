"""Interactive credentials stay in the user's terminal, never CLI arguments."""
import getpass
import re
import sys
import warnings

from .service import MODELS, SECRET_NAMES, Service
from .client import safe_error_details, validate_gateway_id

SMOKE = {
    'state': '线上网站发生故障，所有用户无法登录，请立即修复。',
    'questions': {
        'is_urgent': {'type': 'noul', 'instructions': 'Does this describe an urgent outage?'},
    },
}


def setup(ctx, args, *, service=None, save_secret=None):
    if not sys.stdin.isatty():
        raise ValueError('Setup needs an interactive terminal; no credentials were read.')
    service = service or Service(ctx)
    backend = args.backend or input('Backend [typesafe/cloudflare]: ').strip()
    if backend not in SECRET_NAMES:
        raise ValueError('Choose typesafe or cloudflare.')
    gateway_id = getattr(args, 'gateway_id', None)
    validate_gateway_id(backend, gateway_id)
    account = ''
    if backend == 'cloudflare':
        account = args.account_id or input('Cloudflare Account ID: ').strip()
        if not re.fullmatch(r'[a-fA-F0-9]{32}', account):
            raise ValueError('Account ID must be exactly 32 hexadecimal characters.')
    connection = {'backend': backend, 'model': args.model or MODELS[backend], 'account_id': account, 'timeout': 30}
    if backend == 'cloudflare' and gateway_id is not None:
        connection['gateway_id'] = gateway_id
    print('One small live Jev request will be sent to the selected provider; usage may be billed.', flush=True)
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        token = getpass.getpass(f'{SECRET_NAMES[backend]} (hidden): ').strip()
    if not token or any(char.isspace() for char in token):
        raise ValueError('Empty token or whitespace in token; nothing saved.')
    print('Validating Jev...', flush=True)
    result = service.request(connection, token, **SMOKE)
    if save_secret is None:
        from hermes_cli.config import save_env_value_secure
        save_secret = save_env_value_secure
    save_secret(SECRET_NAMES[backend], token)
    if service.secret(SECRET_NAMES[backend]) != token:
        raise RuntimeError('Credential read-back failed; connection was not changed.')
    ctx.set_config('connection', connection)
    if ctx.get_config('connection') != connection:
        raise RuntimeError('Connection read-back failed.')
    return {'ok': True, 'backend': backend, 'model': result.get('model'),
            'latency_ms': result.get('latency_ms'), 'usage': result.get('usage', {}),
            'credential_saved': True, 'connection_verified': True, 'main_model_changed': False}


def build_parser(parser):
    subs = parser.add_subparsers(dest='jev_command', required=True)
    config = subs.add_parser('setup', help='Interactive hidden credential entry and one live validation')
    config.add_argument('--backend', choices=sorted(SECRET_NAMES))
    config.add_argument('--account-id', help='Non-secret Cloudflare account ID')
    config.add_argument('--gateway-id', help='Non-secret Cloudflare AI Gateway ID')
    config.add_argument('--model', help='Optional model ID; default depends on backend')
    subs.add_parser('status', help='Local configuration presence, never prints keys')
    subs.add_parser('test', help='One billed Chinese smoke call covering all three primitives')
    subs.add_parser('presets', help='Print available decision rubrics, no API call')
    evaluation = subs.add_parser('evaluate', help='Evaluate a JSON request file (paid external request)')
    evaluation.add_argument('--file', required=True, help='JSON object with state and preset OR questions')


def smoke_test(service):
    questions = {
        **SMOKE['questions'],
        'department': {'type': 'choice', 'instructions': 'Which team should handle this?',
                       'criteria': {'technical': 'Bugs and outages', 'billing': 'Payments and invoices', 'unknown': 'Insufficient information'}},
        'severity': {'type': 'score', 'instructions': 'Rate the impact of this incident.',
                     'criteria': ['No outage', 'Partial outage', 'All users cannot log in']},
    }
    connection = service.ctx.get_config('connection', {})
    backend = connection.get('backend')
    validate_gateway_id(backend, connection.get('gateway_id'))
    if backend not in SECRET_NAMES or not service.secret(SECRET_NAMES[backend]):
        return {'ok': False, 'error': 'not_configured', 'message': 'Run hermes jev setup.'}
    result = service.request(connection, service.secret(SECRET_NAMES[backend]), SMOKE['state'], questions)
    answers = result['answers']
    checks = {'urgent': answers['is_urgent']['noul'] > 0.5,
              'department': answers['department']['choice'] == 'technical',
              'severity': answers['severity']['score'] > 1}
    return {**result, 'ok': all(checks.values()), 'online_verified': True,
            'synthetic_smoke_only': True, 'semantic_checks': checks,
            'advisory_only': True, 'execution_authorized': False}


def dispatch(ctx, args):
    import json
    from pathlib import Path
    from .presets import PRESETS
    service = Service(ctx)
    try:
        if args.jev_command == 'setup':
            result = setup(ctx, args, service=service)
        elif args.jev_command == 'evaluate':
            with Path(args.file).open('rb') as handle:
                data = handle.read(1_048_577)
            if len(data) > 1_048_576:
                raise ValueError('Request file exceeds the 1 MiB local limit.')
            result = service.run(json.loads(data))
        else:
            actions = {'status': service.status, 'presets': lambda: {'presets': PRESETS},
                       'test': lambda: smoke_test(service)}
            result = actions[args.jev_command]()
    except (KeyboardInterrupt, EOFError):
        print('Cancelled; no further action taken.')
        raise SystemExit(130)
    except Exception as exc:
        result = {'message': 'Setup or command failed. Check terminal input and plugin configuration; sensitive details are suppressed.',
                  **safe_error_details(exc), 'ok': False, 'error': 'command_failed',
                  'advisory_only': True, 'execution_authorized': False}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get('ok') is False:
        raise SystemExit(1)
