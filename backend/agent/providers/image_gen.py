from __future__ import annotations

import os
from typing import Optional, Dict, Any
from langchain_core.runnables import Runnable

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore

try:
    from ..wrappers.image_gen import make_item_texture_generator
except Exception:  # pragma: no cover
    make_item_texture_generator = None  # type: ignore


API_URL = "https://api.retrodiffusion.ai/v1/inferences"


def build_item_texture_generator() -> Optional[Runnable]:
    """
    Build a Runnable that generates a 16x16 item texture using Retro Diffusion.
    Returns None if provider is unavailable or misconfigured.

    Expected input to the runnable:
      {"prompt": str, "width": int=16, "height": int=16, "num_images": 1, "prompt_style": str}
    Output:
      {"image_bytes": bytes, "width": int, "height": int, "provider": "retro_diffusion"}
    """
    if make_item_texture_generator is None or requests is None:
        return None

    api_key = os.getenv("RETRO_DIFFUSION_API_KEY")
    if not api_key:
        return None

    def _transport(payload: Dict[str, Any]) -> Dict[str, Any]:
        # Prepare request adhering to Retro Diffusion API
        json_payload = {
            "width": int(payload.get("width", 16)),
            "height": int(payload.get("height", 16)),
            "prompt": str(payload.get("prompt", "")),
            "num_images": int(payload.get("num_images", 1)),
        }
        prompt_style = payload.get("prompt_style")
        if prompt_style:
            json_payload["prompt_style"] = str(prompt_style)

        headers = {
            "X-RD-Token": api_key,
        }

        try:
            resp = requests.post(API_URL, headers=headers, json=json_payload, timeout=60)
            resp.raise_for_status()
        except Exception as e:
            # Wrap into a standard shape for the wrapper to handle uniformly
            raise RuntimeError(f"Retro Diffusion request failed: {e}")

        try:
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"Retro Diffusion returned non-JSON response: {e}")

        # Basic validation; wrapper will also validate presence of base64_images
        if not isinstance(data, dict):
            raise RuntimeError("Retro Diffusion response is not a JSON object")

        return data

    return make_item_texture_generator(_transport)

