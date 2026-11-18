"""Locate preserved user assets independently of the flattened source layout."""
from pathlib import Path


def original_research_root(workspace_root: Path | None = None) -> Path:
    root = Path(workspace_root) if workspace_root is not None else Path(__file__).resolve().parents[1]
    # Existing assets stay in their original location until the user reviews them.
    return root / 'stitched_output' / 'stitched_output' / 'stitched_output'
