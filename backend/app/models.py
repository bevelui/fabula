# -*- coding: utf-8 -*-
"""Request/response schemas."""
from pydantic import BaseModel, Field
from typing import Optional


class ProjectCreate(BaseModel):
    title: Optional[str] = None
    channel_url: str = Field(..., description="YouTube channel URL to learn the style from")
    language: str = "en"
    style_id: str = "ink-wash"
    style_custom: Optional[str] = None
    image_provider: str = "pollinations"     # free by default
    audio_provider: str = "edge"             # free by default
    llm_model: str = "claude-sonnet-5"       # Claude model for script + scene prompts
    voice_id: Optional[str] = Field(None, description="voice id for the chosen TTS provider")
    length_words: int = Field(1200, ge=100, le=8000)


class KeyCreate(BaseModel):
    provider: str = Field(..., description="e.g. 'fish', 'gemini', 'anthropic'")
    api_key: str


class FeedbackCreate(BaseModel):
    kind: str = Field("idea", description="idea | bug | other")
    message: str = Field(..., min_length=1, max_length=4000)
    email: Optional[str] = None
    page: Optional[str] = None
