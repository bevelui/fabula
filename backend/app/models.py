# -*- coding: utf-8 -*-
"""Request/response schemas."""
from pydantic import BaseModel, Field
from typing import Optional


class ProjectCreate(BaseModel):
    title: Optional[str] = None
    channel_url: str = ""                    # required only when script_source == 'channel'
    script_source: str = "channel"           # 'channel' | 'own'
    user_script: Optional[str] = None        # the user's pasted script (when source == 'own')
    script_mode: str = "asis"                # own-script: 'asis' | 'polish' | 'reference'
    format: str = "long"                     # 'long' (16:9) or 'short' (9:16)
    language: str = "en"
    style_id: str = "ink-wash"
    style_custom: Optional[str] = None
    image_provider: str = "pollinations"     # free by default
    audio_provider: str = "edge"             # free by default
    # per-task Claude models ('custom' + *_custom lets you type an exact model id)
    script_model: str = "claude-sonnet-5"    # writing the narration
    script_model_custom: Optional[str] = None
    scene_model: str = "claude-sonnet-5"     # directing the scenes / image prompts
    scene_model_custom: Optional[str] = None
    voice_id: Optional[str] = Field(None, description="voice id for the chosen TTS provider")
    length_words: int = Field(1200, ge=100, le=8000)
    num_images: int = Field(0, ge=0, le=200, description="0 = auto (~1 per 120 words)")


class KeyCreate(BaseModel):
    provider: str = Field(..., description="e.g. 'fish', 'gemini', 'anthropic'")
    api_key: str


class RegenImage(BaseModel):
    index: int = Field(..., ge=1, le=200)
    prompt: Optional[str] = None              # optional edited prompt; else reuse the scene's


class FeedbackCreate(BaseModel):
    kind: str = Field("idea", description="idea | bug | other")
    message: str = Field(..., min_length=1, max_length=4000)
    email: Optional[str] = None
    page: Optional[str] = None
