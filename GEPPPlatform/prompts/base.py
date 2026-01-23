"""
Base prompt loader utilities using LangChain
"""

from pathlib import Path
from typing import Optional, Dict, Any
from langchain_core.prompts import load_prompt, PromptTemplate


class PromptLoader:
    """Utility class for loading prompt templates"""

    def __init__(self, base_dir: Optional[Path] = None):
        """
        Initialize the prompt loader

        Args:
            base_dir: Base directory for prompts. Defaults to the prompts directory.
        """
        if base_dir is None:
            base_dir = Path(__file__).parent
        self.base_dir = base_dir

    def load_yaml_prompt(self, relative_path: str) -> PromptTemplate:
        """
        Load a prompt template from a YAML file

        Args:
            relative_path: Path relative to base_dir (e.g., "ai_audit/default/recyclable.yaml")

        Returns:
            Loaded PromptTemplate

        Raises:
            FileNotFoundError: If the prompt file doesn't exist
        """
        full_path = self.base_dir / relative_path

        if not full_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {full_path}")

        return load_prompt(str(full_path))

    def load_ai_audit_prompt(
        self,
        rule_set: str = "default",
        waste_type: str = "general"
    ) -> PromptTemplate:
        """
        Load an AI audit prompt for a specific rule set and waste type

        Args:
            rule_set: Rule set name ("default", "bma", etc.)
            waste_type: Waste type ("general", "organic", "recyclable", "hazardous")

        Returns:
            Loaded PromptTemplate
        """
        return self.load_yaml_prompt(f"ai_audit/{rule_set}/{waste_type}.yaml")

    def get_ai_audit_prompts_for_rule_set(
        self,
        rule_set: str = "default"
    ) -> Dict[str, PromptTemplate]:
        """
        Load all AI audit prompts for a specific rule set

        Args:
            rule_set: Rule set name ("default", "bma", etc.)

        Returns:
            Dictionary mapping waste type to PromptTemplate
        """
        waste_types = ["general", "organic", "recyclable", "hazardous"]
        prompts = {}

        for waste_type in waste_types:
            try:
                prompts[waste_type] = self.load_ai_audit_prompt(rule_set, waste_type)
            except FileNotFoundError:
                # Skip if prompt doesn't exist for this waste type
                continue

        return prompts
