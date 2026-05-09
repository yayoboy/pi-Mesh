"""HTTP endpoints for the bots framework.

Thin layer over ``bots.runner``: introspect the registry and toggle
individual bots without restarting the process.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from bots import runner as bots_runner

router = APIRouter()


class ToggleBody(BaseModel):
    enabled: bool


class PrefixBody(BaseModel):
    prefix: str


@router.get('/api/bots')
async def list_bots():
    """Return prefix + list of bots with their enabled flag."""
    return bots_runner.get_state_snapshot()


@router.post('/api/bots/{name}/toggle')
async def toggle_bot(name: str, body: ToggleBody):
    state = bots_runner.get_state_snapshot()
    if not any(b['name'] == name for b in state.get('bots', [])):
        raise HTTPException(404, detail=f'unknown bot: {name}')
    cfg = bots_runner._state.config
    if cfg is None:
        raise HTTPException(503, detail='bots runner not started')
    await cfg.set_enabled(name, body.enabled)
    await bots_runner.reload_config()
    return {'ok': True, 'name': name, 'enabled': body.enabled}


@router.post('/api/bots/prefix')
async def set_prefix(body: PrefixBody):
    cfg = bots_runner._state.config
    if cfg is None:
        raise HTTPException(503, detail='bots runner not started')
    prefix = (body.prefix or '').strip()
    if not prefix:
        raise HTTPException(400, detail='prefix cannot be empty')
    await cfg.set_prefix(prefix)
    await bots_runner.reload_config()
    return {'ok': True, 'prefix': prefix}


@router.post('/api/bots/reload')
async def reload_bots():
    await bots_runner.reload_config()
    return {'ok': True}
