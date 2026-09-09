# -*- coding: utf-8 -*-
"""The language and art-style catalogs — the user-facing 'any language, any style'.

Language and style are just parameters the engine consumes: language flows to the
script LLM, the TTS voice and the captions; style is a prompt prefix for the image
model. Adding a language or style here surfaces it in the product with no code change.
"""

# Latin-script languages ship at launch (space-delimited words -> caption splitting
# works today). CJK / RTL are marked launch=False until caption + font handling lands.
LANGUAGES = [
    {"code": "en", "name": "English",    "native": "English",    "launch": True},
    {"code": "es", "name": "Spanish",    "native": "Español",    "launch": True},
    {"code": "fr", "name": "French",     "native": "Français",   "launch": True},
    {"code": "de", "name": "German",     "native": "Deutsch",    "launch": True},
    {"code": "nl", "name": "Dutch",      "native": "Nederlands", "launch": True},
    {"code": "it", "name": "Italian",    "native": "Italiano",   "launch": True},
    {"code": "pt", "name": "Portuguese", "native": "Português",  "launch": True},
    {"code": "pl", "name": "Polish",     "native": "Polski",     "launch": True},
    {"code": "sv", "name": "Swedish",    "native": "Svenska",    "launch": True},
    {"code": "id", "name": "Indonesian", "native": "Bahasa Indonesia", "launch": True},
    {"code": "zh", "name": "Chinese",    "native": "中文",        "launch": False},
    {"code": "ja", "name": "Japanese",   "native": "日本語",      "launch": False},
    {"code": "ar", "name": "Arabic",     "native": "العربية",     "launch": False},
]

# Shared clause every image prompt ends with, whatever the style.
_SUFFIX = ("Full-bleed image, no borders, absolutely no text, letters, words, "
           "captions or signatures anywhere.")

STYLE_PRESETS = [
    {"id": "ink-wash", "name": "Ink & wash", "realistic": False,
     "prompt": ("Cinematic illustration in a muted ink-and-wash style, fine black "
                "linework with cross-hatching over painted colour, strong chiaroscuro "
                "with one dominant light source and deep shadows. " + _SUFFIX)},
    {"id": "realistic", "name": "Realistic", "realistic": True,
     "prompt": ("Photorealistic cinematic still, natural lighting, shallow depth of "
                "field, subtle film grain, lifelike detail and skin texture. " + _SUFFIX)},
    {"id": "watercolor", "name": "Watercolour storybook", "realistic": False,
     "prompt": ("Soft watercolour storybook illustration, gentle washes, visible paper "
                "texture, warm tender palette, rounded gentle forms. " + _SUFFIX)},
    {"id": "anime", "name": "Anime / manga", "realistic": False,
     "prompt": ("Modern anime illustration, clean cel shading, expressive eyes, a soft "
                "but vivid palette and detailed painted backgrounds. " + _SUFFIX)},
    {"id": "graphic-novel", "name": "Graphic novel", "realistic": False,
     "prompt": ("Bold graphic-novel ink art, heavy inking, halftone shading, high "
                "contrast and dramatic full-bleed composition. " + _SUFFIX)},
    {"id": "render-3d", "name": "3D render", "realistic": False,
     "prompt": ("Stylized 3D render, soft global illumination, subsurface skin "
                "scattering, warm cinematic lighting and shallow depth of field. " + _SUFFIX)},
    {"id": "noir", "name": "Film noir", "realistic": False,
     "prompt": ("High-contrast black-and-white film-noir illustration, deep shadows, "
                "hard key light and a moody rain-slicked atmosphere. " + _SUFFIX)},
    {"id": "oil", "name": "Oil painting", "realistic": False,
     "prompt": ("Classical oil painting, visible brushwork, rich chiaroscuro, warm "
                "varnished tones and museum lighting. " + _SUFFIX)},
]

_STYLE_BY_ID = {s["id"]: s for s in STYLE_PRESETS}
_LANG_BY_CODE = {l["code"]: l for l in LANGUAGES}


def style_prompt(style_id, custom_text=None):
    """Return the image-prompt prefix for a preset id, or a custom description."""
    if style_id == "custom" and custom_text:
        return f"{custom_text.strip().rstrip('.')}. {_SUFFIX}"
    s = _STYLE_BY_ID.get(style_id)
    return s["prompt"] if s else _STYLE_BY_ID["ink-wash"]["prompt"]


def is_language_supported(code):
    l = _LANG_BY_CODE.get(code)
    return bool(l and l["launch"])
