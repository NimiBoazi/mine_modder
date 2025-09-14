from __future__ import annotations

from typing import Any, Callable, Dict
from langchain_core.runnables import Runnable, RunnableLambda
import base64


def make_item_texture_generator(
    transport: Callable[[Dict[str, Any]], Dict[str, Any]]
) -> Runnable[Dict[str, Any], Dict[str, Any]]:
    """
    Returns a Runnable that accepts a payload:
      {
        "prompt": str,
        "width": int = 16,
        "height": int = 16,
        "num_images": int = 1,
        "prompt_style": str = "rd_fast__mc_item"
      }
    and returns a dict:
      {
        "image_bytes": bytes,  # PNG bytes
        "width": int,
        "height": int,
        "provider": "retro_diffusion"
      }

    The provided `transport` performs the vendor/API call and should return
    a dict containing at least {"base64_images": [str, ...]}.
    """

    def _run(payload: Dict[str, Any]) -> Dict[str, Any]:
        prompt = (payload.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("Texture generator requires a non-empty 'prompt'.")

        width = int(payload.get("width", 16))
        height = int(payload.get("height", 16))
        num_images = int(payload.get("num_images", 1))
        prompt_style = payload.get("prompt_style") or "rd_fast__mc_item"

        # Call underlying transport (vendor-specific) to get base64 images
        resp = transport({
            "prompt": prompt,
            "width": width,
            "height": height,
            "num_images": num_images,
            "prompt_style": prompt_style,
        })

        images64 = list(resp.get("base64_images") or [])
        if not images64:
            raise ValueError("Image API did not return any base64 images.")

        # Take first image only
        img_b64 = images64[0]
        try:
            img_bytes = base64.b64decode(img_b64)
        except Exception as e:
            raise ValueError(f"Failed to decode base64 image: {e}")

        return {
            "image_bytes": img_bytes,
            "width": width,
            "height": height,
            "provider": "retro_diffusion",
        }

    return RunnableLambda(lambda x: _run(x))

