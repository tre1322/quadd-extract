"""
Processor data models for rule-based extraction.

Defines the structure of learned extraction rules (processors) and their components
like anchors, regions, extraction operations, and validations.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional, Any


@dataclass
class Anchor:
    """
    A landmark pattern to find in documents.

    Anchors are used to identify key locations in a document (like headers,
    team names, section dividers) that serve as reference points for defining
    extraction regions.
    """
    name: str  # "period_header", "team_name", "player_table_start"
    patterns: List[str]  # ["Q1", "H1", "Period 1"], ["Team:"], etc.
    pattern_type: str = "contains"  # "contains", "exact", "regex"
    location_hint: Optional[str] = None  # "top_third", "after:game_info", etc.
    required: bool = True  # If true, extraction fails if anchor not found

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Anchor:
        return cls(**data)


@dataclass
class Region:
    """
    An area of the document defined by anchors.

    Regions are bounded sections of the document (like "away team players",
    "score table", "header info") that contain related data to be extracted.
    """
    name: str  # "away_players", "score_table", "game_info"
    start_anchor: str  # Reference to Anchor.name
    end_anchor: str  # Reference to Anchor.name
    region_type: str = "table"  # "table", "list", "key_value", "text"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Region:
        return cls(**data)


@dataclass
class ExtractionOp:
    """
    An operation to extract a field from a region.

    Defines how to extract a specific piece of data from a region, including
    optional transformations to apply to the raw value.
    """
    field_path: str  # "away_team.players[].name", "home_team.final_score"
    source: str  # "region.away_players.column[0]", "block.text"
    transform: Optional[str] = None  # "to_int", "last_name_only", "strip"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ExtractionOp:
        return cls(**data)


@dataclass
class Calculation:
    """
    A derived field calculated from extracted data.

    Calculations define how to compute team totals or other aggregate values
    from player-level or other extracted data.
    """
    field: str  # "team1.total_fouls", "team2.total_rebounds"
    formula: str  # "sum(team1.players[].fouls)", "sum(players[].oreb) + sum(players[].dreb)"
    description: Optional[str] = None  # Human-readable description

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Calculation:
        return cls(**data)


@dataclass
class Validation:
    """
    A rule to validate extracted data.

    Validations are checks that ensure the extracted data is correct and complete.
    They can be errors (must pass) or warnings (informational).
    """
    name: str  # "Period scores sum to final", "All players have stats"
    check: str  # Python expression: "sum(periods) == final_score"
    severity: str = "error"  # "error" or "warning"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Validation:
        return cls(**data)


@dataclass
class Processor:
    """
    Learned transformation rules for a document type.

    A processor encapsulates all the rules needed to extract structured data
    from a specific type of document. It includes:
    - Anchors: Landmark patterns to find
    - Regions: Areas defined by anchors
    - Extraction ops: How to extract each field
    - Validations: Rules to verify correctness
    """

    # Identity
    id: str  # UUID
    name: str  # "windom_basketball", "mountain_lake_honor_roll"
    document_type: str  # "basketball", "hockey", "honor_roll"

    # Detection (for routing documents to the right processor)
    layout_hash: Optional[str] = None  # Hash of document structure
    text_patterns: List[str] = field(default_factory=list)  # Text patterns that identify this doc

    # Extraction rules
    anchors: List[Anchor] = field(default_factory=list)
    regions: List[Region] = field(default_factory=list)
    extraction_ops: List[ExtractionOp] = field(default_factory=list)

    # Calculations (derived fields)
    calculations: List[Calculation] = field(default_factory=list)

    # Validation
    validations: List[Validation] = field(default_factory=list)

    # Rendering
    template_id: str = "generic"  # Legacy: reference to built-in template (deprecated)
    template: Optional[str] = None  # Learned Jinja2 template (preferred over template_id)
    field_column_mapping: Optional[dict] = None  # Learned field-to-column mapping (e.g., {"player_name": "Name", "points": "Pts"})

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    version: int = 1

    def to_json(self) -> str:
        """Serialize to JSON for database storage."""
        data = asdict(self)
        # Convert datetime to string
        data['created_at'] = self.created_at.isoformat() if self.created_at else None
        data['updated_at'] = self.updated_at.isoformat() if self.updated_at else None
        return json.dumps(data, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> Processor:
        """Deserialize from JSON."""
        data = json.loads(json_str)

        # Convert nested dicts back to dataclasses
        data['anchors'] = [Anchor.from_dict(a) for a in data.get('anchors', [])]
        data['regions'] = [Region.from_dict(r) for r in data.get('regions', [])]
        data['extraction_ops'] = [ExtractionOp.from_dict(e) for e in data.get('extraction_ops', [])]
        data['calculations'] = [Calculation.from_dict(c) for c in data.get('calculations', [])]
        data['validations'] = [Validation.from_dict(v) for v in data.get('validations', [])]

        # Convert datetime strings back to datetime
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('updated_at'), str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])

        return cls(**data)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)

    def __repr__(self) -> str:
        return f"Processor(name='{self.name}', type='{self.document_type}', v{self.version})"
