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


FIELD_MAPPING_SYNTHESIS_PROMPT = """You are a field mapping analyzer. Your job is to map field names from desired output to column headers in the source document.

## TASK
Analyze the source document's column headers and the desired output field names, then generate a mapping dictionary.

## SOURCE DOCUMENT COLUMNS
{source_columns}

## DESIRED OUTPUT
{desired_output}

## INSTRUCTIONS
1. **Identify fields in desired output** - Look for data elements (player names, scores, stats, etc.)
2. **Match to source columns** - Map each field to the corresponding column header in the source
3. **Use exact column names** - Column names must match exactly as they appear in source (case-sensitive)
4. **Be generic** - Field names should describe the data, not the sport/domain

## OUTPUT FORMAT
Return ONLY a JSON object mapping field names to column headers. No explanations, no markdown code blocks.

Example for a basketball document:
```json
{{
  "player_name": "Name",
  "points": "Pts",
  "field_goals": "FG",
  "three_pointers": "3FG",
  "free_throws": "FT",
  "offensive_rebounds": "OREB",
  "defensive_rebounds": "DREB",
  "assists": "AST",
  "turnovers": "TO",
  "fouls": "FOUL"
}}
```

Example for an honor roll document:
```json
{{
  "student_name": "Name",
  "grade_level": "Grade",
  "gpa": "GPA"
}}
```

## IMPORTANT
- Field names should be descriptive and generic (use "student_name" not "name", "total_points" not "points")
- Column names must match source exactly (case-sensitive)
- Only include mappings for fields that appear in the desired output
- If a field in the output doesn't have a corresponding column in the source, omit it from the mapping

Generate the mapping now:"""


TEMPLATE_SYNTHESIS_PROMPT = """You are a Jinja2 template generator. Your job is to analyze a desired output string and generate a Jinja2 template that can reproduce that exact format.

## TASK
Generate a Jinja2 template that, when given the appropriate data structure, will produce output matching the desired format exactly.

## DESIRED OUTPUT
{desired_output}

## ANALYSIS INSTRUCTIONS
1. **Identify the structure**: Look for repeating patterns, sections, headers
2. **Identify placeholders**: Find values that would come from data (team names, scores, player names, stats)
3. **Infer data structure**: Determine what the data dictionary should look like
4. **Generate template**: Create Jinja2 syntax that produces this output

## TEMPLATE REQUIREMENTS
1. Use Jinja2 syntax: `{{{{ variable }}}}`, `{{% for item in list %}}...{{% endfor %}}`
2. Assume data is available in a dict called `data`
3. **ONLY use the filters listed below** - no other filters are available
4. Handle missing/optional data gracefully with defaults
5. Match the exact spacing, punctuation, and line breaks of the desired output
6. Use comments `{{#- ... -#}}` to explain non-obvious logic
7. Do spacing with literal spaces in the template, NOT with ljust/rjust/center filters

## AVAILABLE JINJA2 FILTERS (USE ONLY THESE)
- `dot_pad(width)` - Pad text with dots to width (e.g., "Team Name" becomes "Team Name..........")
- `safe_int(default=0)` - Convert to int, return default if None
- `safe_float(default=0.0)` - Convert to float, return default if None
- Standard Jinja filters: `join`, `length`, `default`, `round`, `int`, `string`

## AVAILABLE JINJA2 FUNCTIONS (callable in expressions)
- `pct(made, attempted)` - Calculate percentage as "(X%)"
- `safe_int(value)` - Convert to int safely

## IMPORTANT: Spacing and Alignment
- Use `dot_pad()` for dot leaders (e.g., team names)
- Use literal spaces for fixed-width columns
- Use `"value"|string` to convert numbers to strings
- Do NOT use ljust, rjust, or center - these are not available

## EXAMPLE DATA STRUCTURE PATTERNS
For sports with two teams:
```
{{{{
  "team1": {{"name": "...", "final_score": 72, "players": [...]}},
  "team2": {{"name": "...", "final_score": 68, "players": [...]}}
}}}}
```
or
```
{{{{
  "away_team": {{"name": "...", "final_score": 72}},
  "home_team": {{"name": "...", "final_score": 68}}
}}}}
```

For lists of items:
```
{{{{
  "items": [
    {{"name": "Item 1", "value": 10}},
    {{"name": "Item 2", "value": 20}}
  ]
}}}}
```

## OUTPUT FORMAT
Return ONLY the Jinja2 template text. No explanations, no markdown code blocks, just the raw template.

## IMPORTANT
- The template must be GENERIC - it should work for ANY document of this type, not just this example
- Use loops for repeated elements (player lists, scores, etc.)
- Use conditionals for optional elements
- Preserve exact formatting (dots, spaces, line breaks) from the desired output
- If you see "..." in the desired output, that indicates a loop - use `{{% for %}}` syntax

Generate the template now:"""


SYNTHESIS_PROMPT_TEMPLATE = """You are a document extraction rule synthesizer. Your job is to analyze a source document and desired output, then generate extraction rules that transform the source into the output format.

## TASK
Generate a JSON Processor configuration that defines how to extract structured data from the source document.

## SOURCE DOCUMENT STRUCTURE
The document has been analyzed with OCR and contains the following text blocks with their positions:

{block_summary}

## DESIRED OUTPUT FORMAT
{desired_output}

## YOUR JOB
1. **Analyze the SOURCE document**:
   - Identify tables (repeating rows/columns of data)
   - Identify column headers (short text, often uppercase/title case)
   - Identify section markers (headers, dividers, labels)
   - Identify repeated patterns (lists, sequences)

2. **Analyze the DESIRED OUTPUT**:
   - What fields appear in the output?
   - What structure does it have? (lists, hierarchies, key-value pairs)
   - What aggregations are needed? (sums, counts, concatenations)

3. **Learn the mapping**:
   - Map output fields to source columns/sections
   - Determine how to extract each piece of data
   - Identify what calculations are needed

## EXTRACTION STRATEGY

### For Tabular Data
If you see a table in the source (columns with headers):
- Use column headers as anchors to locate the table
- Define a region for the table rows
- Extract each column as a field
- Use column position (column[0], column[1], etc.)

### For Lists/Sequences
If you see repeated items:
- Find the start/end markers
- Define a region for the list
- Extract each item's fields

### For Key-Value Pairs
If you see labeled data (e.g., "Date: 2024-01-15"):
- Use the label as an anchor
- Extract the text following the anchor

### For Aggregations
If the desired output shows totals/sums that aren't in the source:
- Identify which fields to sum/aggregate
- Create calculations using formulas

## OUTPUT FORMAT

Generate JSON with these components:

### 1. anchors
Landmark patterns to find in the document.

Each anchor:
- name: Descriptive identifier (e.g., "table_header_row", "section_marker")
- patterns: List of text to match (e.g., ["Name"], ["ID"], ["Total:"])
- pattern_type: "contains", "exact", or "regex"
- location_hint: Optional ("first_occurrence", "second_occurrence", "top_third")
- required: true/false

**Strategy**:
- Use short, distinctive text that uniquely identifies a location
- Column headers make good anchors for tables
- Section titles make good anchors for regions

### 2. regions
Areas of the document defined by start/end anchors.

Each region:
- name: Descriptive identifier (e.g., "data_table", "summary_section")
- start_anchor: Reference to anchor name
- end_anchor: Reference to anchor name
- region_type: "table", "list", or "key_value"

### 3. extraction_ops
Operations to extract specific fields.

Each extraction_op:
- field_path: Where to store (e.g., "items[].name", "metadata.date")
  - Use `[]` for arrays (e.g., "items[].value")
  - Use `.` for nested objects (e.g., "section.field")
- source: Where to extract from
  - "region.{{name}}.column[N]" for tables
  - "anchor.{{name}}.text" for single values
  - "region.{{name}}" for concatenated text
- transform: Optional ("to_int", "to_float", "strip", "upper", "lower")

### 4. calculations (optional)
Derived fields calculated from extracted data.

Each calculation:
- field: Output field name (e.g., "totals.sum", "statistics.count")
- formula: Python expression (e.g., "sum(items[].value)", "len(items)")
- description: What this calculates

## EXAMPLE: Generic Data Table

If source has:
```
Name    Value   Status
Item A  100     Active
Item B  200     Pending
```

And desired output is:
```
Items:
- Item A: 100 (Active)
- Item B: 200 (Pending)
Total: 300
```

Then generate:
```json
{{
  "anchors": [
    {{
      "name": "table_start",
      "patterns": ["Name"],
      "pattern_type": "exact",
      "required": true
    }}
  ],
  "regions": [
    {{
      "name": "data_rows",
      "start_anchor": "table_start",
      "end_anchor": "end_of_document",
      "region_type": "table"
    }}
  ],
  "extraction_ops": [
    {{
      "field_path": "items[].name",
      "source": "region.data_rows.column[0]",
      "transform": "strip"
    }},
    {{
      "field_path": "items[].value",
      "source": "region.data_rows.column[1]",
      "transform": "to_int"
    }},
    {{
      "field_path": "items[].status",
      "source": "region.data_rows.column[2]",
      "transform": "strip"
    }}
  ],
  "calculations": [
    {{
      "field": "totals.sum",
      "formula": "sum(items[].value)",
      "description": "Sum of all item values"
    }}
  ]
}}
```

## CRITICAL RULES

1. **NO ASSUMPTIONS**: Don't assume document type. Analyze what you SEE.
2. **LEARN FROM OUTPUT**: If output shows sums/totals not in source, use calculations.
3. **UNIQUE ANCHORS**: Use distinctive text that appears once (or use location_hint).
4. **EXACT COLUMN POSITIONS**: Map each output field to the correct source column.
5. **HANDLE ARRAYS**: Use `[]` in field_path for repeated items.
6. **VALIDATE**: Extraction rules should produce output matching desired format.
7. **RETURN ONLY JSON**: No explanations, no markdown code blocks.

Generate the extraction rules now:"""



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

    async def synthesize_field_mapping(
        self,
        document_ir: DocumentIR,
        desired_output: str
    ) -> dict:
        """
        Generate field-to-column mapping from source document and desired output.

        Args:
            document_ir: Source document with column headers
            desired_output: Example of desired formatted output

        Returns:
            Dictionary mapping field names to column headers

        Raises:
            ValueError: If mapping generation fails
        """
        logger.info("Synthesizing field-to-column mapping")

        # Extract column headers from document blocks
        # Look for blocks that appear to be column headers (short text, near top)
        source_columns = []
        for block in document_ir.blocks[:100]:  # Check first 100 blocks
            # Headers are typically short, uppercase or title case
            text = block.text.strip()
            if len(text) <= 20 and (text.isupper() or text.istitle()):
                source_columns.append(text)

        # Remove duplicates while preserving order
        seen = set()
        unique_columns = []
        for col in source_columns:
            if col not in seen:
                seen.add(col)
                unique_columns.append(col)

        source_columns_str = ", ".join(unique_columns[:30])  # Limit to first 30
        logger.debug(f"Found source columns: {source_columns_str}")

        # Build prompt
        prompt = FIELD_MAPPING_SYNTHESIS_PROMPT.format(
            source_columns=source_columns_str,
            desired_output=desired_output
        )

        # Call Claude
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text.strip()

            # Extract JSON from response
            mapping = self._extract_json(response_text)

            logger.info(f"Generated field mapping with {len(mapping)} fields")
            logger.debug(f"Mapping: {mapping}")
            return mapping

        except Exception as e:
            logger.error(f"Failed to synthesize field mapping: {e}")
            raise ValueError(f"Field mapping synthesis failed: {e}")

    async def synthesize_template(self, desired_output: str) -> str:
        """
        Generate a Jinja2 template from desired output format.

        Args:
            desired_output: Example of the desired formatted output

        Returns:
            Jinja2 template string that can reproduce the format

        Raises:
            ValueError: If template generation fails
        """
        logger.info("Synthesizing Jinja2 template from desired output")

        # Build prompt
        prompt = TEMPLATE_SYNTHESIS_PROMPT.format(desired_output=desired_output)

        # Call Claude
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )

            template = response.content[0].text.strip()

            # Remove markdown code blocks if present
            if template.startswith("```jinja") or template.startswith("```"):
                lines = template.split("\n")
                # Remove first and last lines (the ``` markers)
                template = "\n".join(lines[1:-1]) if len(lines) > 2 else template

            logger.debug(f"Generated template: {len(template)} chars")
            return template

        except Exception as e:
            logger.error(f"Failed to synthesize template: {e}")
            raise ValueError(f"Template synthesis failed: {e}")

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

        # Step 1: Synthesize field-to-column mapping
        logger.info("Step 1/3: Synthesizing field-to-column mapping...")
        field_mapping = await self.synthesize_field_mapping(document_ir, desired_output)
        logger.info(f"Generated mapping with {len(field_mapping)} fields")

        # Step 2: Synthesize Jinja2 template from desired output
        logger.info("Step 2/3: Synthesizing output template...")
        template = await self.synthesize_template(desired_output)
        logger.info(f"Generated template: {len(template)} chars")

        # Step 3: Synthesize extraction rules
        logger.info("Step 3/3: Synthesizing extraction rules...")
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
                document_ir.layout_hash,
                template,  # Pass learned template
                field_mapping  # Pass learned field mapping
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
        # Summarize ALL blocks to ensure LLM sees all column headers and data
        # (Previously limited to 250, but this could miss critical headers)
        block_summary = self._summarize_blocks(document_ir.blocks)

        # Fill in template (generic prompt doesn't need document_type)
        prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
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
        layout_hash: str,
        template: Optional[str] = None,
        field_mapping: Optional[dict] = None
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

        # Get template ID (legacy, for backward compatibility)
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
            template_id=template_id,
            template=template,  # Store learned template
            field_column_mapping=field_mapping  # Store learned field mapping
        )

        return processor

    def _compute_similarity(self, str1: str, str2: str) -> float:
        """Compute similarity between two strings (0-1)."""
        return SequenceMatcher(None, str1, str2).ratio()
