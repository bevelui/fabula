# -*- coding: utf-8 -*-
from fastapi import APIRouter
from .. import catalog

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/languages")
def languages():
    """All script/voice languages. `launch=false` = coming soon (CJK/RTL)."""
    return catalog.LANGUAGES


@router.get("/styles")
def styles():
    """Art-style presets. `custom` is also accepted on a project with style_custom text."""
    return [{"id": s["id"], "name": s["name"], "realistic": s["realistic"]}
            for s in catalog.STYLE_PRESETS]


@router.get("/providers")
def providers():
    """Image + voice engines + Claude models the user can pick per project."""
    return {"image": catalog.IMAGE_PROVIDERS, "audio": catalog.AUDIO_PROVIDERS,
            "llm": catalog.LLM_MODELS}


@router.get("/render-engines")
def render_engines():
    """The two render engines (ffmpeg / Remotion) with their pros & cons for the picker."""
    return {"engines": catalog.RENDER_ENGINES, "remotion_backends": catalog.REMOTION_BACKENDS}


@router.get("/resolutions")
def resolutions():
    """Output resolutions (480/720/1080) the user can pick at the render step."""
    return {"default": catalog.DEFAULT_RES, "options": catalog.RESOLUTIONS}
