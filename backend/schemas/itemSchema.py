from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
import json, re

@dataclass(frozen=True)
class ItemSchema:
    # --- required inputs for the simple pipeline ---
    modid: str
    base_package: str

    item_id: str
    item_class_name: str           # main custom Java class for this item
    display_name: str
    texture_prompt: str

    creative_tab_key: str          # e.g., "minecraft:ingredients"
    model_type: str                # one of: basicItem, buttonItem, fenceItem, wallItem, handheldItem
    description: str               # concise, includes custom functionality

    # --- optional inputs ---
    recipe_ingredients: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    tooltip_text: Optional[str] = None
    object_ids_for_context: Optional[List[str]] = None

    # ---------- helpers & derived (read-only) ----------
    @staticmethod
    def _upper_snake(s: str) -> str:
        s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s)
        s = re.sub(r'[^A-Za-z0-9]+', '_', s)
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

    # --- Custom main class (package, FQCN, and file path helpers) ---
    @property
    def custom_class_package(self) -> str:
        return f"{self.items_package}.custom"

    @property
    def custom_class_package_path(self) -> str:
        return self._pkg_to_path(self.custom_class_package)

    @property
    def custom_class_fqcn(self) -> str:
        return f"{self.custom_class_package}.{self.item_class_name}"

    @property
    def custom_class_relpath(self) -> str:
        # Java sources root relative path
        return f"src/main/java/{self.custom_class_package_path}/{self.item_class_name}.java"

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
        """Dict your subgraph expects (updated to new schema)."""
        return {
            "modid": self.modid,
            "base_package": self.base_package,

            "item_id": self.item_id,
            "registry_constant": self.registry_constant,
            "item_class_name": self.item_class_name,
            "display_name": self.display_name,
            "texture_prompt": self.texture_prompt,

            "creative_tab_key": self.creative_tab_key,
            "model_type": self.model_type,
            "description": self.description,

            # optional
            "recipe_ingredients": self.recipe_ingredients,
            "tags": self.tags,
            "tooltip_text": self.tooltip_text,
            "object_ids_for_context": self.object_ids_for_context,

            # derived paths/keys used by templates & file writes
            "base_package_path": self.base_package_path,
            "items_package": self.items_package,
            "items_package_path": self.items_package_path,
            "custom_class_package": self.custom_class_package,
            "custom_class_package_path": self.custom_class_package_path,
            "custom_class_fqcn": self.custom_class_fqcn,
            "custom_class_relpath": self.custom_class_relpath,
            "lang_key": self.lang_key,
            "model_relpath": self.model_relpath,
            "texture_relpath": self.texture_relpath,
            "lang_relpath": self.lang_relpath,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":"))

    # ---- Class-level helpers for deriving main class info without an instance ----
    @classmethod
    def custom_class_package_for(cls, base_package: str) -> str:
        return f"{base_package}.item.custom"

    @classmethod
    def custom_class_fqcn_for(cls, base_package: str, item_class_name: str) -> str:
        return f"{cls.custom_class_package_for(base_package)}.{item_class_name}"

    @classmethod
    def custom_class_relpath_for(cls, base_package: str, item_class_name: str) -> str:
        base_path = base_package.replace('.', '/')
        return f"src/main/java/{base_path}/item/custom/{item_class_name}.java"
