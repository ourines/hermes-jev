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
            'credential_saved': True, 'connection_verified': True, 'main_model_changed': False,
            'next_step': 'Run hermes jev guide for free examples and skill usage. '
                         'For an optional additional online smoke test, run hermes jev test (may be billed).',
            'agent_tool_visibility': 'not_checked_in_this_cli_process',
            'session_note': 'Existing sessions may need a plugin reload or a new session. '
                            'A new session does not guarantee tool visibility; check its actual tool list. '
                            'No restart was performed.',
            'restart_performed': False, 'advisory_only': True, 'execution_authorized': False}


def guide():
    """Static onboarding only: no configuration, credential or provider access."""
    return {
        'what_it_does': 'Jev 是按需调用的决策助手：对有限问题做分类、真假判断、选项选择或评分；不替换主模型，不执行行动，也不授予权限。',
        'presets': {
            'task_triage': '任务分类，提示缺失上下文与需要审批的风险。',
            'next_step': '结合目标、近期尝试和观察，建议继续、重试、换方法、询问、升级或停止。',
            'relevance': '根据目标和待评估材料，判断材料的相关程度。',
        },
        'example_prompts': {
            'task_triage': '请加载 jev:decision-sidekick，用 task_triage 评估“整理项目文档”，只给建议，不执行。',
            'next_step': '请用 Jev next_step 评估：目标是修复测试；同一修改已重试两次，错误不变。建议下一步，不执行。',
            'relevance': '请用 Jev relevance 评估：目标是排查登录失败；材料是一段已去除敏感信息的认证错误摘要。',
        },
        'billing': {
            'free_commands': ['status', 'guide', 'presets'],
            'paid_commands': ['setup', 'test', 'evaluate'],
            'notice': 'status / guide / presets 仅在本地运行，不发 API 请求。setup 会发送一次在线验证；test / evaluate 会向所选提供商发请求，可能计费。仅发送最少必要且不含密钥的数据。',
        },
        'skill': {
            'name': 'jev:decision-sidekick',
            'invocation': '在 Hermes 对话中请求“请加载 jev:decision-sidekick”；助手可调用 skill_view(name="jev:decision-sidekick")。',
        },
        'native_tool_missing': {
            'cli_fallback': 'hermes jev evaluate --file request.json',
            'request_example': {'state': '整理项目文档', 'preset': 'task_triage'},
            'note': '如果当前会话未暴露 jev_evaluate，可将请求 JSON 保存为 request.json 后使用 CLI（可能计费）。CLI 成功不证明桌面已暴露原生工具。',
        },
        'agent_tool_visibility': 'not_checked_in_this_cli_process',
        'session_note': '现有会话可能需要重新加载插件或开启新会话；新会话也不保证工具可见，请检查该会话的实际工具列表。本命令不自动重启。',
        'advisory_only': True,
        'execution_authorized': False,
    }


def build_parser(parser):
    subs = parser.add_subparsers(dest='jev_command', required=True)
    config = subs.add_parser('setup', help='Interactive hidden credential entry and one live validation')
    config.add_argument('--backend', choices=sorted(SECRET_NAMES))
    config.add_argument('--account-id', help='Non-secret Cloudflare account ID')
    config.add_argument('--gateway-id', help='Non-secret Cloudflare AI Gateway ID')
    config.add_argument('--model', help='Optional model ID; default depends on backend')
    subs.add_parser('status', help='Local configuration presence, never prints keys')
    subs.add_parser('guide', help='Free local onboarding, examples and billing boundaries; no API call')
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
            actions = {'status': service.status, 'guide': guide, 'presets': lambda: {'presets': PRESETS},
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
