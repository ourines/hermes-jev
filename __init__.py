"""Jev decision sidekick for Hermes: explicit calls only, no hooks."""
import json
from pathlib import Path


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
    ctx.register_cli_command(name='jev', help='Configure and test the Jev decision sidekick',
                             setup_fn=build_parser, handler_fn=lambda args: dispatch(ctx, args))
    ctx.register_skill('decision-sidekick', Path(__file__).parent / 'skills' / 'decision-sidekick' / 'SKILL.md')
    ctx.register_skill('typesafe-ai', Path(__file__).parent / 'skills' / 'typesafe-ai' / 'SKILL.md')
