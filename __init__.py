"""Jev decision sidekick for Hermes, including request-scoped model routing."""
import json
from pathlib import Path


def _model_route_middleware(ctx):
    """Rewrite only the outgoing model field for the matching Hermes session."""
    def middleware(request, **kwargs):
        runtime = ctx.state.get('active_route', {})
        if not isinstance(runtime, dict) or runtime.get('session_id') != kwargs.get('session_id'):
            return None
        saved_turn = runtime.get('turn_id')
        if saved_turn and saved_turn != kwargs.get('turn_id'):
            return None
        saved_provider = runtime.get('provider')
        current_provider = kwargs.get('provider')
        if saved_provider and current_provider and saved_provider != current_provider:
            return {'request': request, 'source': 'jev', 'reason': 'provider_mismatch_no_switch'}
        rewritten = dict(request)
        rewritten['model'] = runtime['model']
        return {'request': rewritten, 'source': 'jev', 'reason': f"route:{runtime.get('route_id', 'selected')}"}
    return middleware


def _clear_model_route(ctx, **kwargs):
    """Drop a route when its Hermes turn finishes; never leak it to a later turn."""
    runtime = ctx.state.get('active_route', {})
    if not isinstance(runtime, dict) or runtime.get('session_id') != kwargs.get('session_id'):
        return None
    saved_turn = runtime.get('turn_id')
    current_turn = kwargs.get('turn_id')
    if saved_turn and current_turn and saved_turn != current_turn:
        return None
    ctx.state.set('active_route', {})
    return None


def register(ctx):
    from .service import Service
    from .cli import build_parser, dispatch
    service = Service(ctx)
    ctx.register_tool(
        name='jev_evaluate', toolset='jev',
        schema={
            'name': 'jev_evaluate',
            'description': 'Fast advisory classification, bounded choice, true/false judgments or rubric scoring via Jev. Use for explicit finite decisions, not generation, arithmetic, permissions or deep reasoning. Send minimal non-secret state. Prefer a preset for task triage, next-step review or relevance; alternatively provide atomic questions. Returns answers, uncertainty review signals, latency and usage. It never executes actions or grants approval. Load jev:decision-sidekick for examples.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'state': {'description': 'Minimal text or JSON state; relevant observations only. Never include credentials or unnecessary private data.', 'anyOf': [{'type': 'string'}, {'type': 'object', 'additionalProperties': True}, {'type': 'array', 'items': {}}]},
                    'preset': {'type': 'string', 'enum': ['task_triage', 'next_step', 'relevance'], 'description': 'Use exactly one of preset or questions. next_step needs goal/recent attempts; relevance needs goal/item.'},
                    'questions': {'type': 'object', 'additionalProperties': {'type': 'object', 'properties': {'type': {'type': 'string', 'enum': ['noul', 'choice', 'score']}, 'instructions': {'type': 'string'}, 'criteria': {'anyOf': [{'type': 'object', 'additionalProperties': {'type': ['string', 'null']}}, {'type': 'array', 'items': {'type': 'string'}}]}}, 'required': ['type', 'instructions'], 'additionalProperties': False}, 'description': 'Named independent questions. Choice criteria is option→description; score criteria is an ordered rubric; noul criteria optionally true/false.'},
                },
                'required': ['state'], 'additionalProperties': False,
            },
        },
        handler=lambda args, **kwargs: json.dumps(service.run(args), ensure_ascii=False),
    )
    ctx.register_tool(
        name='jev_route', toolset='jev',
        schema={
            'name': 'jev_route',
            'description': 'Choose the best configured model profile for a task using one bounded Jev choice. With apply=true (default), arms the selected model for the next Hermes provider requests in this turn when confidence passes the threshold. Provide task and, optionally, 2-32 candidate profiles; otherwise plugin setting model_routes is used. It never grants execution approval or switches providers.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'task': {'description': 'Minimal task description or JSON state; remove secrets and irrelevant history.', 'anyOf': [{'type': 'string'}, {'type': 'object', 'additionalProperties': True}, {'type': 'array', 'items': {}}]},
                    'candidates': {'type': 'array', 'minItems': 2, 'maxItems': 32, 'items': {'type': 'object', 'properties': {'id': {'type': 'string'}, 'model': {'type': 'string'}, 'description': {'type': 'string'}, 'provider': {'type': 'string'}, 'cost_tier': {'type': 'string'}, 'speed_tier': {'type': 'string'}, 'strengths': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['id', 'model', 'description'], 'additionalProperties': False}},
                    'min_confidence': {'type': 'number', 'minimum': 0, 'maximum': 1, 'description': 'Optional local acceptance threshold. Missing/low confidence marks route_needs_review; it never authorizes a switch.'},
                    'apply': {'type': 'boolean', 'default': True, 'description': 'Arm the selected model for subsequent provider requests in this Hermes turn when the route is accepted. Set false for advisory-only routing.'},
                },
                'required': ['task'], 'additionalProperties': False,
            },
        },
        handler=lambda args, **kwargs: json.dumps(
            service.route({**args, '_runtime': {key: kwargs.get(key) for key in ('session_id', 'turn_id', 'provider') if kwargs.get(key) is not None}}),
            ensure_ascii=False),
    )

    if hasattr(ctx, 'register_middleware'):
        ctx.register_middleware('llm_request', _model_route_middleware(ctx))
    if hasattr(ctx, 'register_hook'):
        def on_pre_llm_call(**kwargs):
            service.auto_route_turn(kwargs.get('user_message') or '', {
                key: kwargs.get(key) for key in ('session_id', 'turn_id', 'provider', 'model')
                if kwargs.get(key) is not None
            })
            return None
        ctx.register_hook('pre_llm_call', on_pre_llm_call)
        ctx.register_hook('post_llm_call', lambda **kwargs: _clear_model_route(ctx, **kwargs))
    ctx.register_cli_command(name='jev', help='Configure and test the Jev decision sidekick',
                             setup_fn=build_parser, handler_fn=lambda args: dispatch(ctx, args))
    ctx.register_skill('decision-sidekick', Path(__file__).parent / 'skills' / 'decision-sidekick' / 'SKILL.md')
    ctx.register_skill('typesafe-ai', Path(__file__).parent / 'skills' / 'typesafe-ai' / 'SKILL.md')
