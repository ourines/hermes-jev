"""Hermes-facing runtime; resolve settings and secrets on every call."""
from .presets import assess, questions_for

SECRET_NAMES = {'typesafe': 'TYPESAFE_API_KEY', 'cloudflare': 'CLOUDFLARE_JEV_API_TOKEN'}
MODELS = {'typesafe': 'jev-latest', 'cloudflare': 'typesafe/jev'}


class Service:
    def __init__(self, ctx, evaluator=None, secret_reader=None):
        self.ctx = ctx
        self.evaluator = evaluator
        self.secret_reader = secret_reader

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
        return evaluator(backend=backend, token=token, state=state, questions=questions,
                         account_id=connection.get('account_id', ''),
                         model=connection.get('model') or MODELS[backend],
                         timeout=connection.get('timeout', 30))

    def status(self):
        connection = self.ctx.get_config('connection', {})
        backend = connection.get('backend')
        try:
            present = bool(self.secret(SECRET_NAMES[backend])) if backend in SECRET_NAMES else False
        except Exception:
            present = False
        return {'backend': backend, 'model': connection.get('model') or MODELS.get(backend),
                'account_id': connection.get('account_id', ''), 'credential_present': present,
                'configured': backend in SECRET_NAMES and present,
                'online_verified': False, 'advisory_only': True}

    def run(self, args):
        try:
            return self._run(args)
        except Exception:
            # Never echo arbitrary exceptions, request bodies or headers.
            return {'ok': False, 'error': 'evaluation_failed',
                    'message': 'Invalid request, configuration, or evaluation failure. Run hermes jev test for diagnosis.',
                    'execution_authorized': False}

    def _run(self, args):
        if not isinstance(args, dict):
            raise ValueError('Expected object')
        connection = self.ctx.get_config('connection', {})
        backend = connection.get('backend')
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
