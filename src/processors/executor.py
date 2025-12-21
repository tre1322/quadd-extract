"""
Processor Executor - applies learned rules to documents.

Takes a DocumentIR and a Processor, finds anchors, defines regions,
extracts fields, and validates the results.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from src.ir.document_ir import DocumentIR, TextBlock, BoundingBox
from src.processors.models import Processor, Anchor, Region, ExtractionOp
from src.processors.validator import ProcessorValidator, ValidationResult

logger = logging.getLogger(__name__)


class ProcessorExecutor:
    """
    Executes processors to extract structured data from documents.

    This is the deterministic execution engine that applies learned rules
    to new documents without requiring LLM calls.
    """

    def __init__(self):
        self.validator = ProcessorValidator()

    def execute(self, ir: DocumentIR, processor: Processor) -> dict:
        """
        Execute a processor on a DocumentIR.

        Args:
            ir: Document intermediate representation
            processor: Processor with extraction rules

        Returns:
            Extracted structured data

        Raises:
            ValueError: If required anchors not found or validation fails
        """
        logger.info(f"Executing processor '{processor.name}' on '{ir.filename}'")

        # Step 1: Find anchors
        anchor_positions = self._find_anchors(ir, processor.anchors)

        # Check for required anchors
        for anchor in processor.anchors:
            if anchor.required and anchor.name not in anchor_positions:
                raise ValueError(f"Required anchor '{anchor.name}' not found in document")

        # Step 2: Define regions based on anchors
        regions = self._define_regions(ir, anchor_positions, processor.regions)

        # Step 3: Extract data using extraction ops
        data = {}
        for op in processor.extraction_ops:
            try:
                value = self._extract_field(ir, regions, anchor_positions, op, processor)
                self._set_nested_field(data, op.field_path, value)
            except Exception as e:
                logger.warning(f"Failed to extract field '{op.field_path}': {e}")

        # Step 4: Execute calculations (sum player stats -> team totals)
        if processor.calculations:
            logger.debug(f"Executing {len(processor.calculations)} calculations")
            for calc in processor.calculations:
                try:
                    value = self._execute_calculation(data, calc)
                    self._set_nested_field(data, calc.field, value)
                    logger.debug(f"Calculated {calc.field} = {value}")
                except Exception as e:
                    logger.warning(f"Failed to calculate '{calc.field}': {e}")

        # Step 5: Validate
        if processor.validations:
            result = self.validator.validate(data, processor.validations)
            if not result.success:
                logger.warning(f"Validation failed: {', '.join(result.errors)}")
                # Don't raise - continue to see what was extracted
            if result.warnings:
                logger.warning(f"Validation warnings: {', '.join(result.warnings)}")

        logger.info(f"Successfully extracted data with {len(data)} top-level fields")
        return data

    def _find_anchors(self, ir: DocumentIR, anchors: List[Anchor]) -> Dict[str, TextBlock]:
        """
        Find anchor blocks in the document.

        Args:
            ir: Document IR
            anchors: List of anchors to find

        Returns:
            Dict mapping anchor names to their TextBlock positions
        """
        found_anchors = {}

        for anchor in anchors:
            block = self._find_anchor_block(ir, anchor)
            if block:
                found_anchors[anchor.name] = block
                logger.debug(f"Found anchor '{anchor.name}' at {block.bbox}")
            elif anchor.required:
                logger.warning(f"Required anchor '{anchor.name}' not found")

        logger.info(f"Found {len(found_anchors)}/{len(anchors)} anchors")
        return found_anchors

    def _find_anchor_block(self, ir: DocumentIR, anchor: Anchor) -> Optional[TextBlock]:
        """Find a single anchor in the document."""
        for pattern in anchor.patterns:
            blocks = []

            if anchor.pattern_type == "exact":
                blocks = ir.find_text_exact(pattern, case_sensitive=False)
            elif anchor.pattern_type == "regex":
                blocks = self._find_regex(ir, pattern)
            else:  # contains
                blocks = ir.find_text(pattern, case_sensitive=False)

            # If no exact match found and pattern has multiple words, try proximity matching
            if not blocks and ' ' in pattern:
                blocks = self._find_proximity_match(ir, pattern)

            if blocks:
                # If location hint provided, filter by it
                if anchor.location_hint:
                    blocks = self._filter_by_location_hint(blocks, anchor.location_hint)

                if blocks:
                    # Return first match
                    return blocks[0]

        return None

    def _find_regex(self, ir: DocumentIR, pattern: str) -> List[TextBlock]:
        """Find blocks matching a regex pattern."""
        regex = re.compile(pattern, re.IGNORECASE)
        return [b for b in ir.blocks if regex.search(b.text)]

    def _find_proximity_match(self, ir: DocumentIR, pattern: str, proximity: float = 0.1) -> List[TextBlock]:
        """
        Find blocks where words in pattern appear near each other.

        Args:
            ir: Document IR
            pattern: Multi-word pattern like "Player Stats" or "Box Score Report"
            proximity: Max distance in normalized coordinates (default 0.1 = 10% of page)

        Returns:
            List of synthetic blocks representing matched word groups
        """
        words = pattern.lower().split()
        if len(words) < 2:
            return []

        # Find blocks for each word
        word_blocks = {}
        for word in words:
            matches = [b for b in ir.blocks if word in b.text.lower()]
            if not matches:
                # If any word not found, pattern can't match
                return []
            word_blocks[word] = matches

        # Find groups where all words appear close together
        matched_groups = []

        # Start with first word's blocks
        for first_block in word_blocks[words[0]]:
            # Try to find remaining words near this block
            group = [first_block]

            for word in words[1:]:
                # Find closest block with this word on same page
                # IMPORTANT: Calculate distance from PREVIOUS block, not first block
                # This allows long patterns to work (sequential matching)
                prev_block = group[-1]
                closest = None
                min_dist = proximity

                for candidate in word_blocks[word]:
                    if candidate.bbox.page != prev_block.bbox.page:
                        continue

                    # Calculate distance from PREVIOUS block (not first)
                    dx = candidate.bbox.x0 - prev_block.bbox.x1
                    dy = abs(candidate.bbox.y0 - prev_block.bbox.y0)
                    dist = (dx**2 + dy**2) ** 0.5

                    if dist < min_dist:
                        min_dist = dist
                        closest = candidate

                if closest:
                    group.append(closest)
                else:
                    # Word not found nearby, this group doesn't match
                    break

            # If we found all words, this is a match
            if len(group) == len(words):
                # Create synthetic block spanning the group
                min_x = min(b.bbox.x0 for b in group)
                max_x = max(b.bbox.x1 for b in group)
                min_y = min(b.bbox.y0 for b in group)
                max_y = max(b.bbox.y1 for b in group)

                synthetic_block = TextBlock(
                    id=f"proximity_{first_block.id}",
                    text=" ".join(b.text for b in group),
                    bbox=BoundingBox(
                        x0=min_x,
                        y0=min_y,
                        x1=max_x,
                        y1=max_y,
                        page=first_block.bbox.page
                    ),
                    confidence=min(b.confidence for b in group),
                    font_size=first_block.font_size,
                    is_bold=first_block.is_bold,
                    block_type=first_block.block_type
                )
                matched_groups.append(synthetic_block)
                logger.debug(f"Proximity match: '{pattern}' -> '{synthetic_block.text}' at {synthetic_block.bbox}")

        return matched_groups

    def _filter_by_location_hint(self, blocks: List[TextBlock], hint: str) -> List[TextBlock]:
        """Filter blocks by location hint like 'top_third', 'left_half', 'first_occurrence', etc."""
        if not blocks:
            return blocks

        # Occurrence-based hints
        if hint == "first_occurrence":
            # Sort by page then position, return first
            sorted_blocks = sorted(blocks, key=lambda b: (b.bbox.page, b.bbox.y0, b.bbox.x0))
            return [sorted_blocks[0]] if sorted_blocks else []
        elif hint == "second_occurrence":
            # Sort by page then position, return second
            sorted_blocks = sorted(blocks, key=lambda b: (b.bbox.page, b.bbox.y0, b.bbox.x0))
            return [sorted_blocks[1]] if len(sorted_blocks) > 1 else []
        elif hint == "last_occurrence":
            # Sort by page then position, return last
            sorted_blocks = sorted(blocks, key=lambda b: (b.bbox.page, b.bbox.y0, b.bbox.x0))
            return [sorted_blocks[-1]] if sorted_blocks else []

        # Position-based hints
        if hint == "top_third":
            return [b for b in blocks if b.bbox.y0 < 0.33]
        elif hint == "top_half":
            return [b for b in blocks if b.bbox.y0 < 0.5]
        elif hint == "bottom_half":
            return [b for b in blocks if b.bbox.y0 >= 0.5]
        elif hint == "left_half":
            return [b for b in blocks if b.bbox.x0 < 0.5]
        elif hint == "right_half":
            return [b for b in blocks if b.bbox.x0 >= 0.5]

        return blocks

    def _define_regions(
        self,
        ir: DocumentIR,
        anchor_positions: Dict[str, TextBlock],
        region_specs: List[Region]
    ) -> Dict[str, List[TextBlock]]:
        """
        Define regions based on anchor positions.

        Args:
            ir: Document IR
            anchor_positions: Found anchors
            region_specs: Region specifications

        Returns:
            Dict mapping region names to lists of blocks in that region
        """
        regions = {}

        for region_spec in region_specs:
            start_anchor = anchor_positions.get(region_spec.start_anchor)

            # Handle special "end_of_document" anchor
            if region_spec.end_anchor == "end_of_document":
                end_anchor = "END_OF_DOC"  # Special marker
            else:
                end_anchor = anchor_positions.get(region_spec.end_anchor)

            if not start_anchor:
                logger.warning(
                    f"Region '{region_spec.name}' missing start anchor: {region_spec.start_anchor}"
                )
                continue

            if end_anchor is None and region_spec.end_anchor != "end_of_document":
                logger.warning(
                    f"Region '{region_spec.name}' missing end anchor: {region_spec.end_anchor}"
                )
                continue

            # Get all blocks between start and end anchors
            region_blocks = self._get_blocks_between(ir, start_anchor, end_anchor)
            regions[region_spec.name] = region_blocks

            logger.debug(f"Region '{region_spec.name}' has {len(region_blocks)} blocks")

        return regions

    def _get_blocks_between(
        self,
        ir: DocumentIR,
        start: TextBlock,
        end
    ) -> List[TextBlock]:
        """Get all blocks between two anchor blocks."""
        # Handle special "end of document" marker
        if end == "END_OF_DOC":
            page_blocks = ir.get_blocks_by_page(start.bbox.page)
            start_y = start.bbox.y1  # After start block
            between = []
            for block in page_blocks:
                if block.bbox.y0 >= start_y:
                    between.append(block)
            return between

        # Same page only
        if start.bbox.page != end.bbox.page:
            return []

        page_blocks = ir.get_blocks_by_page(start.bbox.page)

        # Get blocks between start and end y-coordinates
        start_y = start.bbox.y1  # After start block
        end_y = end.bbox.y0  # Before end block

        between = []
        for block in page_blocks:
            if start_y <= block.bbox.y0 <= end_y:
                between.append(block)

        return sorted(between, key=lambda b: (b.bbox.y0, b.bbox.x0))

    def _extract_field(
        self,
        ir: DocumentIR,
        regions: Dict[str, List[TextBlock]],
        anchors: Dict[str, TextBlock],
        op: ExtractionOp,
        processor: Processor
    ) -> Any:
        """
        Extract a single field value.

        Args:
            ir: Document IR
            regions: Defined regions
            anchors: Found anchors
            op: Extraction operation
            processor: Processor with learned field mapping

        Returns:
            Extracted value
        """
        # Parse source specification
        # Examples: "region.away_players.column[0]", "anchor.team_name.text"

        if op.source.startswith("region."):
            return self._extract_from_region(regions, anchors, op, processor)
        elif op.source.startswith("anchor."):
            return self._extract_from_anchor(anchors, ir, op)
        elif op.source.startswith("table."):
            return self._extract_from_table(ir, op)
        elif op.source == "literal":
            # Handle literal sources by inferring from field path
            return self._extract_literal(anchors, op)
        else:
            logger.warning(f"Unknown source type in: {op.source}")
            return None

    def _extract_from_region(
        self,
        regions: Dict[str, List[TextBlock]],
        anchors: Dict[str, TextBlock],
        op: ExtractionOp,
        processor: Processor
    ) -> Any:
        """Extract value from a region."""
        # Parse: "region.away_players.column[0]"
        parts = op.source.split('.')
        if len(parts) < 2:
            return None

        region_name = parts[1]
        region_blocks = regions.get(region_name, [])

        if not region_blocks:
            return None

        # Simple extraction: just concatenate text
        if len(parts) == 2:
            text = " ".join(b.text for b in region_blocks)
            return self._apply_transform(text, op.transform)

        # Column extraction: "column[0]" means first column
        if len(parts) >= 3 and "column" in parts[2]:
            col_match = re.search(r'column\[(\d+)\]', parts[2])
            if col_match:
                col_idx = int(col_match.group(1))

                # Try to infer correct column from field name
                # Extract field name from path (e.g., "team1.players[].oreb" -> "oreb")
                field_name = op.field_path.split('.')[-1].replace('[]', '').lower()

                # Use learned field-to-column mapping from processor
                # Fall back to empty dict if not available (backward compatibility)
                field_to_column_map = processor.field_column_mapping or {}

                # Use position-based column extraction with field-aware correction
                values = self._extract_column_by_position(
                    region_blocks, col_idx, anchors, field_name, field_to_column_map
                )

                # Return list or single value
                if '[]' in op.field_path:
                    return [self._apply_transform(v, op.transform) if v else None for v in values]
                else:
                    return self._apply_transform(values[0] if values else None, op.transform)

        return None

    def _extract_from_anchor(
        self,
        anchors: Dict[str, TextBlock],
        ir: DocumentIR,
        op: ExtractionOp
    ) -> Any:
        """Extract value from an anchor."""
        # Parse: "anchor.team_name.text" or "anchor.team_scores.next_number[1]"
        parts = op.source.split('.')
        if len(parts) < 2:
            return None

        anchor_name = parts[1]
        anchor_block = anchors.get(anchor_name)

        if not anchor_block:
            return None

        # Check for special extraction patterns
        if len(parts) >= 3:
            pattern = parts[2]

            # Handle next_number and next_number[N]
            if pattern.startswith("next_number"):
                # Find numbers after this anchor on same row
                numbers = self._find_numbers_after_anchor(ir, anchor_block)

                # Check for index like next_number[1]
                if '[' in pattern:
                    idx_match = re.search(r'\[(\d+)\]', pattern)
                    if idx_match and numbers:
                        idx = int(idx_match.group(1))
                        if idx < len(numbers):
                            return self._apply_transform(numbers[idx], op.transform)
                elif numbers:
                    # Return first number
                    return self._apply_transform(numbers[0], op.transform)

                return None

        # Default: Get text from anchor
        text = anchor_block.text
        return self._apply_transform(text, op.transform)

    def _extract_from_table(self, ir: DocumentIR, op: ExtractionOp) -> Any:
        """Extract value from a table."""
        # Parse: "table.0.row[1].col[2]"
        # For Phase 1, this is a placeholder - tables are complex
        logger.warning("Table extraction not yet fully implemented")
        return None

    def _extract_literal(self, anchors: Dict[str, TextBlock], op: ExtractionOp) -> Any:
        """
        Extract from literal source by inferring anchor from field path.

        When LLM generates source="literal", we map field names to anchors.
        """
        # Extract field name from path (e.g., "team1.name" -> "team1")
        field_path = op.field_path.lower()

        # Map field paths to anchor names
        if "team1" in field_path and "name" in field_path:
            anchor_name = "team1_scores"
        elif "team2" in field_path and "name" in field_path:
            anchor_name = "team2_scores"
        else:
            logger.warning(f"Cannot infer anchor for literal field: {op.field_path}")
            return None

        # Get anchor text
        anchor_block = anchors.get(anchor_name)
        if anchor_block:
            return self._apply_transform(anchor_block.text, op.transform)

        return None

    def _find_numbers_after_anchor(
        self,
        ir: DocumentIR,
        anchor_block: TextBlock,
        max_distance: float = 0.5
    ) -> List[str]:
        """
        Find number blocks on the same row after an anchor.

        Args:
            ir: Document IR
            anchor_block: The anchor block
            max_distance: Maximum X-distance to search

        Returns:
            List of number strings found after the anchor
        """
        # Get blocks on the same page
        page_blocks = ir.get_blocks_by_page(anchor_block.bbox.page)

        # Find blocks on same row (within Y-tolerance)
        y_tolerance = 0.015
        same_row_blocks = []

        for block in page_blocks:
            # Same row and to the right of anchor
            if (abs(block.bbox.center_y - anchor_block.bbox.center_y) <= y_tolerance and
                block.bbox.x0 > anchor_block.bbox.x1 and
                block.bbox.x0 - anchor_block.bbox.x1 < max_distance):
                same_row_blocks.append(block)

        # Sort by x-position
        same_row_blocks.sort(key=lambda b: b.bbox.x0)

        # Extract number values
        numbers = []
        for block in same_row_blocks:
            # Check if text looks like a number
            text = block.text.strip()
            if text.replace('.', '').replace('-', '').replace('+', '').isdigit():
                numbers.append(text)

        return numbers

    def _group_blocks_by_row(self, blocks: List[TextBlock], tolerance: float = 0.015) -> List[List[TextBlock]]:
        """Group blocks into rows by y-coordinate."""
        if not blocks:
            return []

        sorted_blocks = sorted(blocks, key=lambda b: b.bbox.center_y)

        rows = []
        current_row = [sorted_blocks[0]]
        current_y = sorted_blocks[0].bbox.center_y

        for block in sorted_blocks[1:]:
            if abs(block.bbox.center_y - current_y) <= tolerance:
                current_row.append(block)
            else:
                rows.append(sorted(current_row, key=lambda b: b.bbox.x0))
                current_row = [block]
                current_y = block.bbox.center_y

        if current_row:
            rows.append(sorted(current_row, key=lambda b: b.bbox.x0))

        return rows

    def _extract_column_by_position(
        self,
        region_blocks: List[TextBlock],
        col_idx: int,
        anchors: Dict[str, TextBlock],
        field_name: str = None,
        field_to_column_map: dict = None,
        x_tolerance: float = 0.03
    ) -> List[str]:
        """
        Extract a column from a table region using x-position range mapping.

        Maps blocks to columns based on X-position ranges defined by headers,
        handling multi-block columns and missing data correctly.

        Args:
            region_blocks: All blocks in the region
            col_idx: Column index to extract (may be incorrect if LLM counted wrong)
            anchors: Found anchor blocks (including column headers)
            field_name: The field being extracted (e.g., "oreb", "fouls")
            field_to_column_map: Map of field names to column header names
            x_tolerance: Tolerance for x-position matching

        Returns:
            List of values for this column (one per row, empty string if missing)
        """
        # Group blocks into rows
        rows = self._group_blocks_by_row(region_blocks)

        if not rows:
            return []

        # Determine which page this region is on
        # All blocks in a region should be on the same page
        region_page = region_blocks[0].bbox.page if region_blocks else None

        # Build column definitions from anchors
        # Column headers are outside the region, so we use anchors to find them

        columns = []

        # Collect all potential column header anchors
        # Map anchor names to their blocks
        # IMPORTANT: Only include anchors from the same page as the region
        potential_columns = {}

        # Dynamically find ALL column anchors (anchors ending with '_column')
        # This ensures we include MINS, +/-, and any other columns the synthesizer created
        for anchor_name, anchor_block in anchors.items():
            if anchor_name.endswith('_column'):
                # Only include anchors from the same page as the region
                if region_page is None or anchor_block.bbox.page == region_page:
                    potential_columns[anchor_name] = anchor_block

        # Special case: Find region start anchor as Name column
        # Look for team1_player_table_start or team2_player_table_start
        region_start_patterns = ['team1_player_table_start', 'team2_player_table_start',
                                  'player_table_start', 'name_column']
        for pattern in region_start_patterns:
            if pattern in anchors:
                anchor_block = anchors[pattern]
                # Only use if on the same page as the region
                if region_page is None or anchor_block.bbox.page == region_page:
                    columns.append({
                        'name': 'Name',
                        'x_center': anchor_block.bbox.x0
                    })
                    break

        # Add all other column anchors
        for anchor_name, anchor_block in sorted(potential_columns.items(),
                                                  key=lambda x: x[1].bbox.x0):
            columns.append({
                'name': anchor_block.text,
                'x_center': anchor_block.bbox.x0
            })

        # If still no columns found, use first row as fallback
        if not columns:
            header_row = rows[0]
            for header_block in header_row:
                columns.append({
                    'name': header_block.text,
                    'x_center': header_block.bbox.x0
                })

        # Sort columns by x-position
        columns.sort(key=lambda c: c['x_center'])

        # Calculate X-ranges for each column
        for i in range(len(columns)):
            if i == 0:
                # First column starts at left edge
                columns[i]['x_start'] = 0.0
            else:
                # Start at midpoint with previous column
                midpoint = (columns[i - 1]['x_center'] + columns[i]['x_center']) / 2
                columns[i]['x_start'] = midpoint

            if i == len(columns) - 1:
                # Last column ends at right edge
                columns[i]['x_end'] = 1.0
            else:
                # End at midpoint with next column
                midpoint = (columns[i]['x_center'] + columns[i + 1]['x_center']) / 2
                columns[i]['x_end'] = midpoint

        # Find target column using field name if available
        target_column = None

        if field_name and field_to_column_map:
            # Try to find column by field name
            target_column_name = field_to_column_map.get(field_name)
            if target_column_name:
                for col in columns:
                    if col['name'] == target_column_name:
                        target_column = col
                        break

        # Fall back to index-based lookup if field name didn't work
        if not target_column:
            if col_idx >= len(columns):
                # Index out of range
                return [""] * len(rows)
            target_column = columns[col_idx]

        # Extract values from ALL data rows (don't skip first row)
        values = []
        for row in rows:
            # Find all blocks that belong to this column
            column_blocks = []
            for block in row:
                block_x = block.bbox.x0
                if target_column['x_start'] <= block_x < target_column['x_end']:
                    column_blocks.append(block)

            # Sort blocks by x-position and concatenate
            column_blocks.sort(key=lambda b: b.bbox.x0)

            if column_blocks:
                # Concatenate multiple blocks with space
                value = ' '.join(b.text for b in column_blocks)
                # DEBUG: Show name extraction
                if field_name == 'name' and value:
                    print(f"DEBUG Name extraction: row {len(values)}: '{value}'")
                values.append(value)
            else:
                # No data in this column for this row
                values.append("")

        return values

    def _apply_transform(self, value: Any, transform: Optional[str]) -> Any:
        """Apply transformation to extracted value."""
        if value is None or transform is None:
            return value

        if transform == "to_int":
            try:
                return int(value)
            except (ValueError, TypeError):
                return 0

        elif transform == "to_float":
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0

        elif transform == "strip":
            return str(value).strip() if value else ""

        elif transform == "last_name_only":
            # Extract last name from "First Last"
            parts = str(value).split()
            return parts[-1] if parts else value

        elif transform == "upper":
            return str(value).upper() if value else ""

        elif transform == "lower":
            return str(value).lower() if value else ""

        return value

    def _set_nested_field(self, data: dict, field_path: str, value: Any):
        """
        Set a nested field in data dictionary.

        Args:
            data: Dictionary to modify
            field_path: Dot-separated path like "home_team.players[].name"
            value: Value to set
        """
        parts = field_path.split('.')
        current = data

        for i, part in enumerate(parts[:-1]):
            # Handle array notation
            if part.endswith('[]'):
                part = part[:-2]
                if part not in current:
                    current[part] = []
                # If value is a list, we're setting multiple items
                if isinstance(value, list):
                    # Create list of dicts if needed
                    while len(current[part]) < len(value):
                        current[part].append({})
                current = current[part]
            else:
                if part not in current:
                    current[part] = {}
                current = current[part]

        # Set final value
        final_key = parts[-1]
        if final_key.endswith('[]'):
            final_key = final_key[:-2]
            if isinstance(current, list):
                # Setting array items
                for idx, item in enumerate(current):
                    if isinstance(value, list) and idx < len(value):
                        item[final_key] = value[idx]
            else:
                current[final_key] = value if isinstance(value, list) else [value]
        else:
            if isinstance(current, list):
                # Distribute values across array items if value is also a list
                if isinstance(value, list) and len(value) == len(current):
                    # Distribute: players[0].name = value[0], players[1].name = value[1], etc.
                    for idx, item in enumerate(current):
                        item[final_key] = value[idx]
                else:
                    # Set same value on all items
                    for item in current:
                        item[final_key] = value
            else:
                current[final_key] = value

    def _execute_calculation(self, data: dict, calc: Any) -> Any:
        """
        Execute a calculation formula.

        Args:
            data: Extracted data dictionary
            calc: Calculation with formula to evaluate

        Returns:
            Calculated value

        Supported formulas:
            - sum(team1.players[].fouls) - Sum a field across array items
            - sum(players[].oreb) + sum(players[].dreb) - Compound calculations
        """
        formula = calc.formula.strip()

        # Handle compound formulas (e.g., "sum(x) + sum(y)")
        if '+' in formula or '-' in formula or '*' in formula or '/' in formula:
            return self._evaluate_compound_formula(data, formula)

        # Handle simple sum formula: sum(path.to.array[].field)
        if formula.startswith('sum(') and formula.endswith(')'):
            path = formula[4:-1].strip()  # Extract "team1.players[].fouls"
            return self._sum_field(data, path)

        logger.warning(f"Unsupported calculation formula: {formula}")
        return None

    def _evaluate_compound_formula(self, data: dict, formula: str) -> Any:
        """Evaluate compound formulas like 'sum(a) + sum(b)'."""
        import re

        # Find all sum() expressions
        sum_pattern = r'sum\([^)]+\)'
        sums = re.findall(sum_pattern, formula)

        # Replace each sum with its value
        result_formula = formula
        for sum_expr in sums:
            path = sum_expr[4:-1].strip()
            value = self._sum_field(data, path)
            result_formula = result_formula.replace(sum_expr, str(value if value is not None else 0))

        # Evaluate the resulting arithmetic expression
        try:
            # Safe evaluation with restricted globals
            result = eval(result_formula, {"__builtins__": {}}, {})
            return result
        except Exception as e:
            logger.warning(f"Failed to evaluate formula '{formula}': {e}")
            return None

    def _sum_field(self, data: dict, path: str) -> float:
        """
        Sum a field across an array.

        Args:
            data: Data dictionary
            path: Path like "team1.players[].fouls" or "players[].oreb"

        Returns:
            Sum of values
        """
        # Parse path: "team1.players[].fouls" -> ["team1", "players[]", "fouls"]
        parts = path.split('.')
        current = data

        # Navigate to the array
        for part in parts[:-1]:
            if part.endswith('[]'):
                part = part[:-2]

            if isinstance(current, dict):
                current = current.get(part)
            else:
                logger.warning(f"Cannot navigate path {path}: expected dict at {part}")
                return 0.0

            if current is None:
                logger.warning(f"Path {path} not found in data")
                return 0.0

        # Current should now be an array
        if not isinstance(current, list):
            logger.warning(f"Expected array at {path}, got {type(current)}")
            return 0.0

        # Sum the final field across all array items
        final_field = parts[-1]
        total = 0.0
        for item in current:
            if isinstance(item, dict):
                value = item.get(final_field)
                if value is not None:
                    try:
                        total += float(value)
                    except (ValueError, TypeError):
                        logger.warning(f"Cannot convert {value} to number in sum")
            else:
                logger.warning(f"Expected dict in array, got {type(item)}")

        return total
