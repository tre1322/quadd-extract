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
                value = self._extract_field(ir, regions, anchor_positions, op)
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
                closest = None
                min_dist = proximity

                for candidate in word_blocks[word]:
                    if candidate.bbox.page != first_block.bbox.page:
                        continue

                    # Calculate distance (Euclidean in normalized space)
                    dx = candidate.bbox.x0 - first_block.bbox.x1
                    dy = abs(candidate.bbox.y0 - first_block.bbox.y0)
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
            end_anchor = anchor_positions.get(region_spec.end_anchor)

            if not start_anchor or not end_anchor:
                logger.warning(
                    f"Region '{region_spec.name}' missing anchors: "
                    f"start={start_anchor is not None}, end={end_anchor is not None}"
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
        end: TextBlock
    ) -> List[TextBlock]:
        """Get all blocks between two anchor blocks."""
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
        op: ExtractionOp
    ) -> Any:
        """
        Extract a single field value.

        Args:
            ir: Document IR
            regions: Defined regions
            anchors: Found anchors
            op: Extraction operation

        Returns:
            Extracted value
        """
        # Parse source specification
        # Examples: "region.away_players.column[0]", "anchor.team_name.text"

        if op.source.startswith("region."):
            return self._extract_from_region(regions, op)
        elif op.source.startswith("anchor."):
            return self._extract_from_anchor(anchors, op)
        elif op.source.startswith("table."):
            return self._extract_from_table(ir, op)
        else:
            logger.warning(f"Unknown source type in: {op.source}")
            return None

    def _extract_from_region(self, regions: Dict[str, List[TextBlock]], op: ExtractionOp) -> Any:
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
                # Group blocks by row, extract specified column
                rows = self._group_blocks_by_row(region_blocks)
                values = []
                for row in rows:
                    if col_idx < len(row):
                        values.append(row[col_idx].text)
                # Return list or single value
                if '[]' in op.field_path:
                    return [self._apply_transform(v, op.transform) for v in values]
                else:
                    return self._apply_transform(values[0] if values else None, op.transform)

        return None

    def _extract_from_anchor(self, anchors: Dict[str, TextBlock], op: ExtractionOp) -> Any:
        """Extract value from an anchor."""
        # Parse: "anchor.team_name.text"
        parts = op.source.split('.')
        if len(parts) < 2:
            return None

        anchor_name = parts[1]
        anchor_block = anchors.get(anchor_name)

        if not anchor_block:
            return None

        # Get text
        text = anchor_block.text
        return self._apply_transform(text, op.transform)

    def _extract_from_table(self, ir: DocumentIR, op: ExtractionOp) -> Any:
        """Extract value from a table."""
        # Parse: "table.0.row[1].col[2]"
        # For Phase 1, this is a placeholder - tables are complex
        logger.warning("Table extraction not yet fully implemented")
        return None

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
                # Setting same value on all items
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
