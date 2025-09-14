from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any
import json, re

@dataclass(frozen=True)
class ItemSchema:
    # --- required inputs for the simple pipeline ---
    modid: str
    base_package: str
    main_class_name: str

    item_id: str
    display_name: str
    texture_prompt: str

    add_to_creative: bool
    creative_tab_key: str  # e.g., "CreativeModeTabs.INGREDIENTS"

    # model file parent (used in item_model.json.tmpl)
    model_parent: str = "minecraft:item/generated"

    # ---------- helpers & derived (read-only) ----------
    @staticmethod
    def _upper_snake(s: str) -> str:
        s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s)  # camelCase -> snake_case
        s = re.sub(r'[^A-Za-z0-9]+', '_', s)           # non-alnum -> _
        return s.strip('_').upper()

    @staticmethod
    def _pkg_to_path(pkg: str) -> str:
        return pkg.replace('.', '/')

    @property
    def registry_constant(self) -> str:
        return self._upper_snake(self.item_id)

    @property
    def base_package_path(self) -> str:
        return self._pkg_to_path(self.base_package)

    @property
    def items_package(self) -> str:
        return f"{self.base_package}.item"

    @property
    def items_package_path(self) -> str:
        return self._pkg_to_path(self.items_package)

    @property
    def lang_key(self) -> str:
        return f"item.{self.modid}.{self.item_id}"

    @property
    def model_relpath(self) -> str:
        return f"assets/{self.modid}/models/item/{self.item_id}.json"

    @property
    def texture_relpath(self) -> str:
        return f"assets/{self.modid}/textures/item/{self.item_id}.png"

    @property
    def lang_relpath(self) -> str:
        return f"assets/{self.modid}/lang/en_us.json"

    def to_payload(self) -> Dict[str, Any]:
        """Dict your subgraph expects (only fields used by the simple pipeline)."""
        return {
            "modid": self.modid,
            "base_package": self.base_package,
            "main_class_name": self.main_class_name,

            "item_id": self.item_id,
            "registry_constant": self.registry_constant,
            "display_name": self.display_name,
            "texture_prompt": self.texture_prompt,

            "add_to_creative": self.add_to_creative,
            "creative_tab_key": self.creative_tab_key,

            "model_parent": self.model_parent,

            # derived paths/keys used by templates & file writes
            "base_package_path": self.base_package_path,
            "items_package": self.items_package,
            "items_package_path": self.items_package_path,
            "lang_key": self.lang_key,
            "model_relpath": self.model_relpath,
            "texture_relpath": self.texture_relpath,
            "lang_relpath": self.lang_relpath,
        }

    def to_json(self) -> str:
        """Canonical JSON (stable ordering) if you persist/hash."""
        return json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":"))
