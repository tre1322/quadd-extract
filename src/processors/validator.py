"""
Validation logic for extracted data.

Validates that extracted data meets the requirements defined in a processor's
validation rules. Supports schema validation, math validation, and custom checks.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List

from src.processors.models import Validation

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of running validations on extracted data."""
    success: bool
    errors: List[str]
    warnings: List[str]

    def __bool__(self) -> bool:
        """Allow using result in boolean context."""
        return self.success


class ProcessorValidator:
    """
    Validates extracted data against processor rules.

    Executes validation checks defined in a processor and returns
    errors/warnings for any violations.
    """

    def validate(self, data: dict, validations: List[Validation]) -> ValidationResult:
        """
        Run all validation rules on extracted data.

        Args:
            data: Extracted data dictionary
            validations: List of validation rules to check

        Returns:
            ValidationResult with success flag, errors, and warnings
        """
        errors = []
        warnings = []

        for validation in validations:
            try:
                # Evaluate the check expression
                # Available in scope: data, sum, len, min, max, all, any
                safe_globals = {
                    'data': data,
                    'sum': sum,
                    'len': len,
                    'min': min,
                    'max': max,
                    'all': all,
                    'any': any,
                    'abs': abs,
                    'round': round,
                }

                result = eval(validation.check, safe_globals, {})

                if not result:
                    msg = f"Validation failed: {validation.name}"

                    if validation.severity == "error":
                        errors.append(msg)
                        logger.warning(f"Validation error: {validation.name}")
                    else:
                        warnings.append(msg)
                        logger.debug(f"Validation warning: {validation.name}")

            except KeyError as e:
                # Missing field in data
                msg = f"Validation '{validation.name}' failed: Missing field {e}"
                if validation.severity == "error":
                    errors.append(msg)
                else:
                    warnings.append(msg)
                logger.warning(f"Validation error: {msg}")

            except Exception as e:
                # Unexpected error in validation check
                msg = f"Validation '{validation.name}' error: {str(e)}"
                errors.append(msg)
                logger.error(f"Validation exception: {msg}")

        success = len(errors) == 0

        if not success:
            logger.info(f"Validation failed with {len(errors)} errors, {len(warnings)} warnings")
        elif warnings:
            logger.info(f"Validation passed with {len(warnings)} warnings")
        else:
            logger.debug("Validation passed")

        return ValidationResult(
            success=success,
            errors=errors,
            warnings=warnings
        )

    def validate_schema(self, data: dict, required_fields: List[str]) -> ValidationResult:
        """
        Simple schema validation - check for required fields.

        Args:
            data: Data to validate
            required_fields: List of required field paths (e.g., "home_team.name")

        Returns:
            ValidationResult
        """
        errors = []

        for field_path in required_fields:
            if not self._has_field(data, field_path):
                errors.append(f"Missing required field: {field_path}")

        return ValidationResult(
            success=len(errors) == 0,
            errors=errors,
            warnings=[]
        )

    def _has_field(self, data: dict, field_path: str) -> bool:
        """
        Check if a nested field exists in data.

        Args:
            data: Data dictionary
            field_path: Dot-separated field path (e.g., "home_team.name")

        Returns:
            True if field exists and is not None
        """
        parts = field_path.split('.')
        current = data

        for part in parts:
            # Handle array notation like "players[]"
            if part.endswith('[]'):
                part = part[:-2]

            if isinstance(current, dict):
                if part not in current:
                    return False
                current = current[part]
            elif isinstance(current, list):
                # For lists, check if any item has the field
                if not current:
                    return False
                current = current[0]  # Check first item
                if isinstance(current, dict) and part not in current:
                    return False
                current = current.get(part) if isinstance(current, dict) else None
            else:
                return False

        return current is not None


# Common validation patterns for sports documents

def make_basketball_validations() -> List[Validation]:
    """Create common validations for basketball documents."""
    return [
        Validation(
            name="Both teams present",
            check="'home_team' in data and 'away_team' in data",
            severity="error"
        ),
        Validation(
            name="Team names not empty",
            check="data.get('home_team', {}).get('name') and data.get('away_team', {}).get('name')",
            severity="error"
        ),
        Validation(
            name="Final scores present",
            check="'final_score' in data.get('home_team', {}) and 'final_score' in data.get('away_team', {})",
            severity="error"
        ),
        Validation(
            name="Period scores sum to final (home)",
            check="sum(data.get('home_team', {}).get('period_scores', [])) == data.get('home_team', {}).get('final_score', 0)",
            severity="warning"
        ),
        Validation(
            name="Period scores sum to final (away)",
            check="sum(data.get('away_team', {}).get('period_scores', [])) == data.get('away_team', {}).get('final_score', 0)",
            severity="warning"
        ),
    ]


def make_hockey_validations() -> List[Validation]:
    """Create common validations for hockey documents."""
    return [
        Validation(
            name="Both teams present",
            check="'home_team' in data and 'away_team' in data",
            severity="error"
        ),
        Validation(
            name="Final scores present",
            check="'final_score' in data.get('home_team', {}) and 'final_score' in data.get('away_team', {})",
            severity="error"
        ),
    ]
