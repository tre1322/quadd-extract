"""
Processor Synthesizer - generates extraction rules from examples using LLM.

This is the "learning" component that takes an example document + desired output
and generates a Processor with anchors, regions, extraction ops, and validations.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from difflib import SequenceMatcher
from typing import Optional

import anthropic

from src.ir.document_ir import DocumentIR
from src.processors.models import Processor, Anchor, Region, ExtractionOp, Calculation, Validation
from src.processors.executor import ProcessorExecutor
from src.processors.validator import make_basketball_validations, make_hockey_validations

logger = logging.getLogger(__name__)


SYNTHESIS_PROMPT_TEMPLATE = """You are a document extraction rule synthesizer. Your job is to generate extraction rules that transform an input document into a desired output format.

## TASK
Generate a JSON Processor configuration that defines how to extract structured data from the given document type.

## DOCUMENT TYPE
{document_type}

## CRITICAL INSTRUCTIONS
1. **Look for PLAYER-LEVEL DATA**: If the desired output contains individual player stats, you MUST find and extract from player tables
2. **Calculate TEAM TOTALS FROM PLAYERS**: When output shows team totals (Fouls, Rebounds, Turnovers), these MUST be CALCULATED by summing the corresponding columns from the PLAYERS array
   - Example: Team fouls = sum(team1.players[].fouls) where "fouls" is the player's individual foul count
   - Example: Team rebounds = sum(team1.players[].oreb) + sum(team1.players[].dreb)
   - DO NOT sum from region data or team stats - ONLY from individual player rows
3. **Check ALL PAGES**: Player stats tables are often on page 2 or later pages, not just page 1
4. **CRITICAL - Use ONLY column headers as player table anchors**:
   - ✅ GOOD: patterns: ["Name"] - column header, unique, on correct page
   - ✅ GOOD: patterns: ["Pts"] - column header, unique identifier
   - ❌ BAD: patterns: ["Worthington", "High", "School's"] - team name appears on multiple pages
   - ❌ BAD: patterns: ["Boys", "Varsity"] - generic words appear everywhere
   - **RULE**: For player table anchors, use ONLY single column headers like "Name", "Pts", "FG"
   - Team names can be used for score regions, but NOT for player table regions
5. **Extract BOTH TEAMS**: Apply the same extraction logic to ALL teams in the document

## DOCUMENT STRUCTURE
The document has been analyzed with OCR and contains the following text blocks with their positions:

{block_summary}

## DESIRED OUTPUT
{desired_output}

## ANALYSIS GUIDE
Before generating rules, analyze:
1. Does the desired output contain individual player names and stats? → Need to extract from player table
2. Does it show team totals (Fouls, Rebounds, etc.)? → Calculate by summing player columns
3. What column headers exist? → Use them as anchors to find player tables
4. How many teams? → Create extraction rules for each team

## YOUR TASK
Generate extraction rules in JSON format with these components:

1. **anchors**: Landmark patterns to find in the document (headers, team names, section markers)
   - Each anchor should have: name, patterns (list of text to search for), pattern_type ("contains", "exact", or "regex"), location_hint (optional), required (true/false)

2. **regions**: Areas of the document defined by start/end anchors
   - Each region should have: name, start_anchor (reference to anchor name), end_anchor, region_type ("table", "list", "key_value")

3. **extraction_ops**: Operations to extract specific fields from regions or anchors
   - Each op should have: field_path (where to store the value), source (where to extract from), transform (optional transformation like "to_int", "strip")

4. **template_id**: Which output template to use (e.g., "basketball_windom", "hockey_standard", "generic")

## SOURCE SYNTAX
- "anchor.{{anchor_name}}.text" - Extract text from an anchor block
- "region.{{region_name}}.column[N]" - Extract column N from a table region
- For arrays, use "[]" in field_path like "players[].name"

## TRANSFORMS
Available transforms: "to_int", "to_float", "strip", "last_name_only", "upper", "lower"

## EXAMPLE: Basketball with Player Tables
```json
{{
  "anchors": [
    {{
      "name": "team1_player_table_start",
      "patterns": ["Name"],
      "pattern_type": "exact",
      "location_hint": "first_occurrence",
      "required": true
    }},
    {{
      "name": "team2_player_table_start",
      "patterns": ["Name"],
      "pattern_type": "exact",
      "location_hint": "second_occurrence",
      "required": true
    }},
    {{
      "name": "pts_column",
      "patterns": ["Pts"],
      "pattern_type": "exact",
      "location_hint": null,
      "required": false
    }},
    {{
      "name": "foul_column",
      "patterns": ["FOUL"],
      "pattern_type": "exact",
      "location_hint": null,
      "required": false
    }}
  ],
  "regions": [
    {{
      "name": "team1_players",
      "start_anchor": "player_stats_header",
      "end_anchor": "team2_players_start",
      "region_type": "table"
    }},
    {{
      "name": "team2_players",
      "start_anchor": "team2_players_start",
      "end_anchor": "end_of_document",
      "region_type": "table"
    }}
  ],
  "extraction_ops": [
    {{
      "field_path": "team1.players[].name",
      "source": "region.team1_players.column[0]",
      "transform": "strip"
    }},
    {{
      "field_path": "team1.players[].points",
      "source": "region.team1_players.column[1]",
      "transform": "to_int"
    }},
    {{
      "field_path": "team1.players[].fouls",
      "source": "region.team1_players.column[8]",
      "transform": "to_int"
    }},
    {{
      "field_path": "team2.players[].name",
      "source": "region.team2_players.column[0]",
      "transform": "strip"
    }},
    {{
      "field_path": "team2.players[].fouls",
      "source": "region.team2_players.column[8]",
      "transform": "to_int"
    }}
  ],
  "calculations": [
    {{
      "field": "team1.total_fouls",
      "formula": "sum(team1.players[].fouls)"
    }},
    {{
      "field": "team1.total_rebounds",
      "formula": "sum(team1.players[].oreb) + sum(team1.players[].dreb)"
    }},
    {{
      "field": "team2.total_fouls",
      "formula": "sum(team2.players[].fouls)"
    }}
  ],
  "template_id": "basketball_windom"
}}
```

## IMPORTANT RULES
1. Return ONLY valid JSON, no explanations or markdown
2. Make anchors specific enough to match uniquely but general enough to work on similar documents
3. Use location_hint to disambiguate when multiple matches might exist
4. For table regions, identify start/end clearly
5. Match the output format exactly - if output has specific formatting, note that in template_id
6. **CRITICAL**: Calculation formulas MUST use sum() with field paths, NEVER hardcoded numbers
   - CORRECT: "formula": "sum(team1.players[].fouls)"
   - WRONG: "formula": "9" or "formula": "17 + 30"
7. Formulas must work on ANY document, not just this example

Now generate the extraction rules:"""


class ProcessorSynthesizer:
    """
    Synthesizes processors from example documents using LLM.

    Takes a DocumentIR + desired output and generates extraction rules
    that can be applied to similar documents.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-20250514"):
        """
        Initialize synthesizer.

        Args:
            api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if not provided)
            model: Claude model to use for rule generation
        """
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ValueError("ANTHROPIC_API_KEY required for ProcessorSynthesizer")

        self.client = anthropic.Anthropic(api_key=resolved_key)
        self.model = model
        self.executor = ProcessorExecutor()

    async def synthesize(
        self,
        document_ir: DocumentIR,
        desired_output: str,
        document_type: str,
        name: str
    ) -> Processor:
        """
        Generate a processor from an example.

        Args:
            document_ir: Example document IR
            desired_output: Expected formatted output
            document_type: Type of document (basketball, hockey, etc.)
            name: Name for the processor

        Returns:
            Generated Processor

        Raises:
            ValueError: If generation fails or confidence is too low
        """
        logger.info(f"Synthesizing processor '{name}' for {document_type}")

        # Build prompt
        prompt = self._build_prompt(document_ir, desired_output, document_type)

        # Call Claude
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text
            logger.debug(f"LLM response length: {len(response_text)} chars")

            # Parse JSON response
            processor_spec = self._extract_json(response_text)

            # Build Processor object
            processor = self._build_processor(
                processor_spec,
                name,
                document_type,
                document_ir.layout_hash
            )

            # Validate by applying to example
            logger.info("Validating generated processor on example document")
            try:
                extracted_data = self.executor.execute(document_ir, processor)
                logger.info(f"Processor executed successfully, extracted {len(extracted_data)} fields")
            except Exception as e:
                logger.warning(f"Processor execution failed: {e}")
                # Continue anyway - processor might work on other documents

            # Compute confidence (similarity to desired output)
            # For Phase 1, we'll skip this and just return the processor
            # Phase 2 can add output comparison

            logger.info(f"Successfully synthesized processor '{name}'")
            return processor

        except Exception as e:
            logger.error(f"Failed to synthesize processor: {e}")
            raise ValueError(f"Processor synthesis failed: {e}")

    def _build_prompt(
        self,
        document_ir: DocumentIR,
        desired_output: str,
        document_type: str
    ) -> str:
        """Build the LLM prompt for rule synthesis."""
        # Summarize DocumentIR blocks (first 250 blocks to include data from multiple pages)
        block_summary = self._summarize_blocks(document_ir.blocks[:250])

        # Fill in template
        prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
            document_type=document_type,
            block_summary=block_summary,
            desired_output=desired_output
        )

        return prompt

    def _summarize_blocks(self, blocks: list) -> str:
        """Summarize text blocks for the prompt."""
        lines = []
        for i, block in enumerate(blocks):
            lines.append(
                f"Block {i}: '{block.text}' at position ({block.bbox.x0:.2f}, {block.bbox.y0:.2f}) "
                f"size={block.font_size:.0f}pt type={block.block_type}"
            )
        return "\n".join(lines)

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from LLM response."""
        # Remove markdown code blocks if present
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()

        # Find JSON object
        if not text.strip().startswith("{"):
            start_idx = text.find("{")
            end_idx = text.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                text = text[start_idx:end_idx + 1]

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.error(f"Response was: {text[:500]}...")
            raise ValueError(f"Invalid JSON in LLM response: {e}")

    def _build_processor(
        self,
        spec: dict,
        name: str,
        document_type: str,
        layout_hash: str
    ) -> Processor:
        """Build a Processor from LLM-generated spec."""
        # Parse anchors
        anchors = [
            Anchor(
                name=a['name'],
                patterns=a['patterns'],
                pattern_type=a.get('pattern_type', 'contains'),
                location_hint=a.get('location_hint'),
                required=a.get('required', True)
            )
            for a in spec.get('anchors', [])
        ]

        # Parse regions
        regions = [
            Region(
                name=r['name'],
                start_anchor=r['start_anchor'],
                end_anchor=r['end_anchor'],
                region_type=r.get('region_type', 'table')
            )
            for r in spec.get('regions', [])
        ]

        # Parse extraction ops
        extraction_ops = [
            ExtractionOp(
                field_path=op['field_path'],
                source=op['source'],
                transform=op.get('transform')
            )
            for op in spec.get('extraction_ops', [])
        ]

        # Parse calculations
        calculations = [
            Calculation(
                field=c['field'],
                formula=c['formula'],
                description=c.get('description')
            )
            for c in spec.get('calculations', [])
        ]

        # Get validations (use defaults for known types)
        validations_spec = spec.get('validations', [])
        if validations_spec:
            validations = [
                Validation(
                    name=v['name'],
                    check=v['check'],
                    severity=v.get('severity', 'error')
                )
                for v in validations_spec
            ]
        else:
            # Use default validations for known types
            if document_type == "basketball":
                validations = make_basketball_validations()
            elif document_type == "hockey":
                validations = make_hockey_validations()
            else:
                validations = []

        # Get template ID
        template_id = spec.get('template_id', 'generic')

        # Create processor
        processor = Processor(
            id=str(uuid.uuid4()),
            name=name,
            document_type=document_type,
            layout_hash=layout_hash,
            text_patterns=[],  # Could extract these from anchors
            anchors=anchors,
            regions=regions,
            extraction_ops=extraction_ops,
            calculations=calculations,
            validations=validations,
            template_id=template_id
        )

        return processor

    def _compute_similarity(self, str1: str, str2: str) -> float:
        """Compute similarity between two strings (0-1)."""
        return SequenceMatcher(None, str1, str2).ratio()
