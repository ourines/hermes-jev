"""Hermes-facing runtime; resolve settings and secrets on every call."""
from .presets import assess, questions_for
from .client import safe_error_details, validate_gateway_id
from .discovery import candidates_from_models, read_hermes_runtime, truthy
from .routing import route_questions, route_result, validate_candidates, validate_min_confidence

SECRET_NAMES = {'typesafe': 'TYPESAFE_API_KEY', 'cloudflare': 'CLOUDFLARE_JEV_API_TOKEN'}
MODELS = {'typesafe': 'jev-latest', 'cloudflare': 'typesafe/jev'}


def credential_name_present(name):
    """Check loaded names, never token values or .env files; fail closed on scope errors."""
    import os
    from agent.secret_scope import current_secret_scope, is_multiplex_active
    scope = current_secret_scope()
    if scope is not None and any(key == name for key in scope):
        return True
    if is_multiplex_active():
        return False
    # Iteration is deliberate: Mapping.__contains__ can read a value.
    return any(key == name for key in os.environ)


class Service:
    def __init__(self, ctx, evaluator=None, secret_reader=None, catalog_reader=None):
        self.ctx = ctx
        self.evaluator = evaluator
        self.secret_reader = secret_reader
        self.catalog_reader = catalog_reader

    def secret(self, name):
        if self.secret_reader is not None:
            return self.secret_reader(name)
        from agent.secret_scope import get_secret
        return get_secret(name)

    def request(self, connection, token, state, questions):
        evaluator = self.evaluator
        if evaluator is None:
            from .client import evaluate
            evaluator = evaluate
        backend = connection['backend']
        validate_gateway_id(backend, connection.get('gateway_id'))
        routing = {'gateway_id': connection['gateway_id']} if connection.get('gateway_id') is not None else {}
        return evaluator(backend=backend, token=token, state=state, questions=questions,
                         account_id=connection.get('account_id', ''),
                         model=connection.get('model') or MODELS[backend],
                         timeout=connection.get('timeout', 30), **routing)

    def status(self):
        connection = self.ctx.get_config('connection', {})
        backend = connection.get('backend')
        validate_gateway_id(backend, connection.get('gateway_id'))
        try:
            present = credential_name_present(SECRET_NAMES[backend]) if backend in SECRET_NAMES else False
        except Exception:
            present = False
        configured = backend in SECRET_NAMES and present
        return {'backend': backend, 'model': connection.get('model') or MODELS.get(backend),
                'account_id': connection.get('account_id', ''), 'credential_present': present,
                'gateway_id': connection.get('gateway_id'),
                'configured': configured,
                'credential_presence_scope': 'loaded_names_only_not_token_validity',
                'verification_scope': 'local_configuration_only',
                'online_verification': 'not_checked',
                'agent_tool_visibility': 'not_checked_in_this_cli_process',
                'next_step': ('For an optional online check, run hermes jev test (may be billed); '
                              'use hermes jev guide for free usage examples.' if configured else
                              'Run hermes jev setup in an interactive terminal (live validation may be billed); '
                              'use hermes jev guide for free guidance.'),
                'status_note': 'Presence means a credential name is loaded, not that its value is nonempty or valid. '
                               'No token values were read. online_verified=false means not checked here, '
                               'not a failed online test. This CLI does not check desktop tool visibility.',
                'online_verified': False, 'advisory_only': True}

    def run(self, args):
        try:
            return self._run(args)
        except Exception as exc:
            # Never echo arbitrary exceptions, request bodies or headers.
            return {'message': 'Invalid request, configuration, or evaluation failure. Run hermes jev test for diagnosis.',
                    **safe_error_details(exc), 'ok': False, 'error': 'evaluation_failed',
                    'advisory_only': True, 'execution_authorized': False}

    def route(self, args):
        try:
            return self._route(args)
        except Exception as exc:
            return {'message': 'Invalid routing request, configuration, or evaluation failure. Run hermes jev test for diagnosis.',
                    **safe_error_details(exc), 'ok': False, 'error': 'routing_failed',
                    'advisory_only': True, 'execution_authorized': False}

    def auto_route_enabled(self):
        return truthy(self.ctx.get_config('model_route_enabled', False))

    def set_auto_route(self, enabled):
        value = bool(enabled)
        self.ctx.set_config('model_route_enabled', value)
        return {'ok': True, 'model_route_enabled': value, 'advisory_only': True,
                'execution_authorized': False}

    def resolve_candidates(self, raw=None, *, provider='', current_model=''):
        """Prefer explicit plugin profiles; otherwise discover the current Hermes catalog."""
        if raw is not None:
            return validate_candidates(raw), 'configured'
        configured = self.ctx.get_config('model_routes', [])
        if configured:
            return validate_candidates(configured), 'configured'
        runtime = {'provider': provider, 'current_model': current_model, 'models': []}
        if self.catalog_reader is not None:
            runtime = self.catalog_reader(provider) or runtime
        else:
            runtime = read_hermes_runtime(provider)
        discovered = candidates_from_models(
            runtime.get('models') or [],
            provider=runtime.get('provider') or provider,
            current_model=current_model or runtime.get('current_model') or '',
        )
        return discovered, 'discovered'

    def routes(self):
        """Show configured or discovered non-secret model profiles without contacting Jev."""
        runtime = read_hermes_runtime() if self.catalog_reader is None else (self.catalog_reader(None) or {})
        candidates, source = self.resolve_candidates(
            provider=runtime.get('provider') or '',
            current_model=runtime.get('current_model') or '',
        )
        threshold = validate_min_confidence(self.ctx.get_config('route_min_confidence', None))
        return {'configured': source == 'configured' and bool(candidates),
                'model_route_enabled': self.auto_route_enabled(),
                'source': source if candidates else 'none',
                'provider': runtime.get('provider') or '',
                'current_model': runtime.get('current_model') or '',
                'candidates': candidates, 'min_confidence': threshold,
                'advisory_only': True, 'execution_authorized': False}

    def auto_route_turn(self, task, runtime=None):
        """Passive per-turn routing. Fail open: never raise into the Hermes loop."""
        try:
            if not self.auto_route_enabled():
                return {'ok': False, 'error': 'disabled', 'applied': False}
            if not isinstance(task, str) or not task.strip() or task.lstrip().startswith('/'):
                return {'ok': False, 'error': 'skipped_task', 'applied': False}
            runtime = runtime if isinstance(runtime, dict) else {}
            existing = self.ctx.state.get('active_route', {}) if hasattr(self.ctx, 'state') else {}
            if isinstance(existing, dict) and existing.get('session_id') == runtime.get('session_id') and existing.get('turn_id') == runtime.get('turn_id') and existing.get('turn_id'):
                return {'ok': True, 'error': 'already_armed', 'applied': True}
            candidates, _source = self.resolve_candidates(
                provider=runtime.get('provider') or '',
                current_model=runtime.get('model') or '',
            )
            if len(candidates) < 2:
                return {'ok': False, 'error': 'insufficient_candidates', 'applied': False}
            return self.route({
                'task': task.strip()[:4000], 'candidates': candidates, 'apply': True,
                '_runtime': runtime,
            })
        except Exception:
            return {'ok': False, 'error': 'auto_route_skipped', 'applied': False, 'advisory_only': True,
                    'execution_authorized': False}

    def _run(self, args):
        if not isinstance(args, dict):
            raise ValueError('Expected object')
        connection = self.ctx.get_config('connection', {})
        backend = connection.get('backend')
        validate_gateway_id(backend, connection.get('gateway_id'))
        if backend not in SECRET_NAMES:
            return {'ok': False, 'error': 'not_configured', 'message': 'Run hermes jev setup in an interactive terminal.', 'execution_authorized': False}
        threshold = self.ctx.get_config('review_threshold', None)
        assess({'answers': {}}, threshold)  # validate before any paid request
        if bool(args.get('preset')) == bool(args.get('questions')):
            raise ValueError('Provide exactly one preset or questions map')
        questions = args.get('questions')
        if args.get('preset'):
            questions = questions_for(args['preset'])
        token = self.secret(SECRET_NAMES[backend])
        if not token:
            return {'ok': False, 'error': 'missing_credential', 'message': 'Run hermes jev setup in this profile.', 'execution_authorized': False}
        result = self.request(connection, token, args.get('state'), questions)
        return {**result, 'review': assess(result, self.ctx.get_config('review_threshold', None)),
                'ok': True, 'advisory_only': True, 'execution_authorized': False}

    def _route(self, args):
        if not isinstance(args, dict):
            raise ValueError('Expected object')
        connection = self.ctx.get_config('connection', {})
        backend = connection.get('backend')
        validate_gateway_id(backend, connection.get('gateway_id'))
        if backend not in SECRET_NAMES:
            return {'ok': False, 'error': 'not_configured', 'message': 'Run hermes jev setup in an interactive terminal.', 'execution_authorized': False}
        task = args.get('task', args.get('state'))
        if task is None:
            raise ValueError('Provide task')
        runtime = args.get('_runtime', {})
        if not isinstance(runtime, dict):
            runtime = {}
        candidates, _source = self.resolve_candidates(
            args.get('candidates'),
            provider=runtime.get('provider') or '',
            current_model=runtime.get('model') or '',
        )
        if len(candidates) < 2:
            raise ValueError('candidates must contain 2..32 model profiles')
        threshold = validate_min_confidence(args.get('min_confidence', self.ctx.get_config('route_min_confidence', None)))
        token = self.secret(SECRET_NAMES[backend])
        if not token:
            return {'ok': False, 'error': 'missing_credential', 'message': 'Run hermes jev setup in this profile.', 'execution_authorized': False}
        result = self.request(connection, token, task, route_questions(candidates))
        routed = route_result(result, candidates, threshold)
        apply_route = args.get('apply', True)
        if not isinstance(apply_route, bool):
            raise ValueError('apply must be a boolean')
        switch = self._apply_route(routed, runtime) if apply_route and routed['route_accepted'] else {
            'requested': apply_route, 'applied': False,
            'reason': 'route_needs_review' if not routed['route_accepted'] else 'apply_disabled',
        }
        routed['model_control'] = switch
        routed['advisory_only'] = not switch['applied']
        return routed

    def _apply_route(self, routed, runtime):
        """Arm a request-scoped model override consumed by Hermes LLM middleware."""
        session_id = runtime.get('session_id')
        turn_id = runtime.get('turn_id')
        if not isinstance(session_id, str) or not session_id:
            return {'requested': True, 'applied': False, 'reason': 'missing_session_id'}
        selection = {
            'session_id': session_id,
            'turn_id': turn_id if isinstance(turn_id, str) else '',
            'model': routed['selected_model'],
            'route_id': routed['route']['route_id'],
            'provider': runtime.get('provider') if isinstance(runtime.get('provider'), str) else '',
        }
        self.ctx.state.set('active_route', selection)
        return {
            'requested': True, 'applied': True,
            'scope': 'next Hermes provider requests in this turn',
            'selected_model': selection['model'],
            'route_id': selection['route_id'],
        }
