"""
Claude Vision-based document extractor.

This is the primary extraction engine. It uses Claude's vision capabilities
to "see" documents and extract structured data.
"""
from __future__ import annotations

import base64
import json
import logging
from io import BytesIO
from typing import Any, Optional

import anthropic
import fitz  # PyMuPDF
from PIL import Image

from src.extractors.base import BaseExtractor
from src.schemas.common import DocumentType, ExtractionResult

logger = logging.getLogger(__name__)


# =============================================================================
# EXTRACTION PROMPTS
# =============================================================================

CLASSIFICATION_PROMPT = """Analyze this document image and classify it into one of these categories:

SPORTS:
- basketball: Basketball box score or game statistics
- hockey: Hockey box score or game statistics  
- wrestling: Wrestling match results or tournament brackets
- gymnastics: Gymnastics meet scores
- baseball: Baseball box score
- football: Football box score
- volleyball: Volleyball box score
- soccer: Soccer box score
- golf: Golf tournament scores
- tennis: Tennis match scores
- track: Track & field meet results
- cross_country: Cross country race results
- swimming: Swimming meet results

LEGAL/PUBLIC NOTICES:
- assumed_name: Certificate of Assumed Name / DBA filing
- summons: Legal summons or court filing
- public_notice: Generic public notice

SCHOOL:
- honor_roll: Honor roll list
- gpa_report: GPA or grade report

OTHER:
- tabular: Generic tabular/structured data
- unknown: Cannot determine type

Respond with ONLY the category name (e.g., "basketball" or "assumed_name").
If you're uncertain, respond with "unknown".
"""

BASKETBALL_EXTRACTION_PROMPT = """Extract ALL basketball game statistics from this box score image.

IMPORTANT: Capture EVERY statistic visible in the document. Different newspapers need different stats, so extract everything available.

TEAM NAME RULES:
- Use the team abbreviation or short name shown in the document (e.g., "WHS", "WOR", "Pipestone")
- Do NOT use generic labels like "Boys Varsity Basketball" - find the actual school/team name
- Look for team names in: title bar, period stats table, team stats headers, player stats section headers
- If you see "WHS vs Worthington", the teams are "WHS" and "Worthington"
- The abbreviation in the stats table (WHS, WOR, etc.) is the team identifier

Return a JSON object with this structure:
{
  "sport": "basketball",
  "game_date": "YYYY-MM-DD or null",
  "venue": "location or null",
  "gender": "boys/girls/mens/womens or null",
  "level": "varsity/jv/freshman or null",
  
  "home_team": {
    "name": "WHS",
    "abbreviation": "WHS",
    "final_score": 104,
    "period_scores": [51, 53],
    
    "fg_made": 42,
    "fg_attempted": 88,
    "two_made": 26,
    "two_attempted": 49,
    "three_made": 16,
    "three_attempted": 39,
    "ft_made": 4,
    "ft_attempted": 12,
    
    "fg_percentage": 47.7,
    "two_percentage": 53.1,
    "three_percentage": 41.0,
    "ft_percentage": 33.3,
    "effective_fg_percentage": 56.8,
    
    "total_rebounds": 47,
    "offensive_rebounds": 17,
    "defensive_rebounds": 30,
    
    "assists": 26,
    "steals": 13,
    "blocks": 2,
    "turnovers": 12,
    "deflections": 20,
    "charges_taken": 0,
    
    "fouls": 23,
    "technical_fouls": 0,
    "fouled_out": ["Player Name"],
    
    "points_per_possession": 1.17,
    "transition_points": 21,
    "points_off_turnovers": 36,
    "second_chance_points": 27,
    "points_in_paint": 46,
    
    "players": [
      {
        "name": "Job Ogeka",
        "jersey_number": "1",
        "points": 18,
        
        "fg_made": 8,
        "fg_attempted": 18,
        "three_made": 0,
        "three_attempted": 2,
        "ft_made": 2,
        "ft_attempted": 3,
        
        "offensive_rebounds": 3,
        "defensive_rebounds": 5,
        "total_rebounds": 8,
        
        "assists": 5,
        "steals": 1,
        "blocks": 0,
        "turnovers": 3,
        "deflections": 2,
        "charges_taken": 0,
        
        "fouls": 2,
        "minutes": 19,
        "plus_minus": 22
      }
    ]
  },
  
  "away_team": {
    // Same structure as home_team
  }
}

CRITICAL INSTRUCTIONS:
1. TEAM NAMES: Use the actual team name/abbreviation from the document, NOT "Boys Varsity Basketball" or similar generic labels
2. TEAM STATS: Look for the "Team Stats" section - it has columns like "WHS" and "WOR" with all shooting stats
   - "2FG Made/Attempted" row = two_made and two_attempted
   - "3FG Made/Attempted" row = three_made and three_attempted  
   - "FT Made/Attempted" row = ft_made and ft_attempted
   - Calculate fg_made = two_made + three_made, fg_attempted = two_attempted + three_attempted
3. PLAYER STATS: Extract ALL players from the player stats table
   - "FG" column typically shows total field goals (made/attempted)
   - "3FG" column shows three-pointers (made/attempted)
   - "FT" column shows free throws (made/attempted)
   - Parse "8/18" as made=8, attempted=18
4. HOME vs AWAY: The first team listed in "X vs Y" title is typically home team
5. PERIOD SCORES: Extract from the Period Stats section
6. Extract ALL players visible, including bench players with 0 stats
7. If player fouled out (5 fouls), add their name to the "fouled_out" array
8. Player names: Use EXACTLY as shown in document (first and last name if shown)

Return ONLY valid JSON, no markdown formatting.
"""

HOCKEY_EXTRACTION_PROMPT = """Extract ALL hockey game statistics from this box score.

IMPORTANT: Capture EVERY statistic visible in the document. Different newspapers need different stats, so extract everything available.

Return a JSON object with this structure:
{
  "sport": "hockey",
  "game_date": "YYYY-MM-DD or null",
  "venue": "location or null",
  "gender": "boys/girls/mens/womens or null",
  "level": "varsity/jv or null",
  
  "away_team": {
    "name": "Team Name",
    "abbreviation": "ABC or null",
    "final_score": 4,
    "period_scores": [1, 2, 1, 0],
    
    "shots_on_goal": 28,
    "shots_by_period": [8, 12, 8, 0],
    "power_play_goals": 1,
    "power_play_opportunities": 4,
    "power_play_percentage": 25.0,
    "penalty_minutes": 8,
    "penalties_count": 4,
    "faceoff_wins": null,
    "faceoff_losses": null,
    "hits": null,
    "blocked_shots": null,
    "giveaways": null,
    "takeaways": null,
    
    "players": [
      {
        "name": "Player Name",
        "jersey_number": "17",
        "goals": 1,
        "hockey_assists": 2,
        "points": 3,
        "shots_on_goal": 4,
        "penalty_minutes": 2,
        "plus_minus_hockey": 2,
        "faceoff_wins": null,
        "faceoff_losses": null,
        "hits": null,
        "blocked_shots": null,
        "time_on_ice": null,
        "power_play_goals": 0,
        "shorthanded_goals": 0
      }
    ],
    
    "goalies": [
      {
        "name": "Goalie Name",
        "jersey_number": "30",
        "minutes_played": 60.0,
        "shots_faced": 27,
        "goals_against": 3,
        "saves": 24,
        "save_percentage": 88.9,
        "decision": "L"
      }
    ]
  },
  
  "home_team": {
    // Same structure as away_team
  },
  
  "scoring_plays": [
    {
      "period": "1st",
      "time": "5:23",
      "team": "Away Team Name",
      "scorer": "Player Name",
      "scorer_number": "8",
      "assists": ["Assist1 Name", "Assist2 Name"],
      "assist_numbers": ["21", "6"],
      "type": "even_strength",
      "away_score": 0,
      "home_score": 1,
      "empty_net": false,
      "game_winning": false
    }
  ],
  
  "penalties": [
    {
      "period": "1st",
      "time": "4:00",
      "team": "Home Team Name",
      "player": "Player Name",
      "player_number": "10",
      "infraction": "Tripping",
      "severity": "Minor",
      "minutes": 2
    }
  ],
  
  "three_stars": ["1. Player Name", "2. Player Name", "3. Player Name"]
}

CRITICAL INSTRUCTIONS:
- Extract ALL players visible, including those with 0 stats
- Period scores should be in order [1st, 2nd, 3rd, OT1, OT2...] - use 0 for scoreless periods
- For scoring plays, parse the scorer and assists from descriptions like "#8 Landyn Lais (even strength) (#21 Maddux Domagala, #6 Blake Sauer)"
- type values: "even_strength", "power_play", "shorthanded", "penalty_shot"
- For goalies: calculate save_percentage if not shown (saves / shots_faced * 100)
- If a stat column does NOT exist, use null
- Plus/minus: keep as integer, can be negative

Return ONLY valid JSON, no markdown formatting.
"""

WRESTLING_EXTRACTION_PROMPT = """Extract all wrestling match results from this document.

Return a JSON object with this structure:
{
  "sport": "wrestling",
  "meet_date": "YYYY-MM-DD or null",
  "venue": "location or null",
  "meet_name": "Tournament Name or null",
  
  "team_1_name": "Team A",
  "team_1_score": 42,
  "team_2_name": "Team B", 
  "team_2_score": 30,
  
  "matches": [
    {
      "weight_class": "106",
      "winner_name": "John Smith",
      "winner_school": "School A",
      "loser_name": "Mike Jones",
      "loser_school": "School B",
      "win_type": "pin",
      "score": null,
      "time": "3:45",
      "winner_team_points": 6
    },
    {
      "weight_class": "113",
      "winner_name": "Bob Wilson",
      "winner_school": "School B",
      "loser_name": "Tom Brown",
      "loser_school": "School A",
      "win_type": "decision",
      "score": "8-3",
      "time": null,
      "winner_team_points": 3
    }
  ]
}

Win types: "pin", "tech_fall" (15+ point lead), "major_decision" (8-14 points), 
"decision" (1-7 points), "forfeit", "default", "disqualification"

Team points: pin=6, tech_fall=5, major_decision=4, decision=3, forfeit=6

Return ONLY valid JSON, no markdown formatting.
"""

GYMNASTICS_EXTRACTION_PROMPT = """Extract all gymnastics meet results from this document.

Return a JSON object with this structure:
{
  "sport": "gymnastics",
  "meet_date": "YYYY-MM-DD or null",
  "venue": "location or null",
  "meet_name": "Meet Name or null",
  
  "teams": [
    {
      "name": "Team Name",
      "final_score": 142.5,
      "team_vault": 35.8,
      "team_bars": 34.9,
      "team_beam": 35.2,
      "team_floor": 36.6
    }
  ],
  
  "events": [
    {
      "event_name": "vault",
      "results": [
        {"name": "Gymnast Name", "position": "1", "vault_score": 9.45},
        {"name": "Gymnast Name", "position": "2", "vault_score": 9.30}
      ]
    },
    {
      "event_name": "bars",
      "results": [
        {"name": "Gymnast Name", "position": "1", "bars_score": 9.50}
      ]
    },
    {
      "event_name": "beam",
      "results": [
        {"name": "Gymnast Name", "position": "1", "beam_score": 9.40}
      ]
    },
    {
      "event_name": "floor",
      "results": [
        {"name": "Gymnast Name", "position": "1", "floor_score": 9.65}
      ]
    }
  ],
  
  "all_around": [
    {
      "name": "Gymnast Name",
      "all_around_score": 37.85,
      "vault_score": 9.45,
      "bars_score": 9.50,
      "beam_score": 9.40,
      "floor_score": 9.50
    }
  ]
}

Return ONLY valid JSON, no markdown formatting.
"""

GENERIC_EXTRACTION_PROMPT = """Extract all structured data from this document.

Return a JSON object with:
{
  "document_type": "description of what this document is",
  "title": "document title if visible",
  "date": "any date found, YYYY-MM-DD format",
  "parties": ["names of people/organizations mentioned"],
  "key_values": {
    "field_name": "value",
    "another_field": "another value"
  },
  "tables": [
    {
      "headers": ["col1", "col2", "col3"],
      "rows": [
        ["val1", "val2", "val3"],
        ["val4", "val5", "val6"]
      ]
    }
  ],
  "body_text": "main text content if any",
  "extraction_notes": "any notes about what couldn't be extracted"
}

Return ONLY valid JSON, no markdown formatting.
"""

# Map document types to prompts
EXTRACTION_PROMPTS = {
    DocumentType.BASKETBALL: BASKETBALL_EXTRACTION_PROMPT,
    DocumentType.HOCKEY: HOCKEY_EXTRACTION_PROMPT,
    DocumentType.WRESTLING: WRESTLING_EXTRACTION_PROMPT,
    DocumentType.GYMNASTICS: GYMNASTICS_EXTRACTION_PROMPT,
    DocumentType.UNKNOWN: GENERIC_EXTRACTION_PROMPT,
}


# =============================================================================
# VISION EXTRACTOR
# =============================================================================

class VisionExtractor(BaseExtractor):
    """
    Claude Vision-based document extractor.
    
    Uses Claude's multimodal capabilities to see and understand documents.
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-20250514"):
        """
        Initialize the Vision extractor.
        
        Args:
            api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if not provided)
            model: Model to use for extraction
        """
        import os
        
        # Check for API key
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found!\n"
                "Please set it before running:\n"
                "  Windows CMD: set ANTHROPIC_API_KEY=sk-ant-api03-...\n"
                "  PowerShell:  $env:ANTHROPIC_API_KEY='sk-ant-api03-...'\n"
                "  Linux/Mac:   export ANTHROPIC_API_KEY=sk-ant-api03-..."
            )
        
        if not resolved_key.startswith("sk-ant-"):
            logger.warning(
                f"API key doesn't look right (should start with 'sk-ant-'). "
                f"Got: {resolved_key[:10]}..."
            )
        
        self.client = anthropic.Anthropic(api_key=resolved_key)
        self.model = model
        logger.info(f"VisionExtractor initialized with model: {model}")
    
    def _pdf_to_images(self, pdf_bytes: bytes, dpi: int = 200) -> list[Image.Image]:
        """Convert PDF pages to PIL Images."""
        images = []
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page in doc:
                # Render at specified DPI
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat)
                
                # Convert to PIL Image
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                images.append(img)
            doc.close()
        except Exception as e:
            logger.error(f"Error converting PDF to images: {e}")
            raise
        
        return images
    
    def _image_to_base64(self, image: Image.Image, format: str = "PNG") -> str:
        """Convert PIL Image to base64 string."""
        buffer = BytesIO()
        image.save(buffer, format=format)
        return base64.standard_b64encode(buffer.getvalue()).decode("utf-8")
    
    def _prepare_document_images(self, document_bytes: bytes, filename: str) -> list[dict]:
        """
        Prepare document as content blocks for Claude.
        
        Returns list of content blocks (images for PDFs/images, text for text files).
        """
        content_blocks = []
        
        # Check if it's plain text
        is_text = filename.lower().endswith(('.txt', '.csv', '.json', '.xml', '.html'))
        if not is_text:
            # Try to detect text by checking if content is valid UTF-8 and has no binary markers
            try:
                text_content = document_bytes.decode('utf-8')
                # Check if it looks like text (no PDF header, no image markers)
                if not document_bytes[:4] == b'%PDF' and not document_bytes[:8] == b'\x89PNG\r\n\x1a\n':
                    # Check if mostly printable characters
                    printable_ratio = sum(c.isprintable() or c.isspace() for c in text_content) / len(text_content)
                    if printable_ratio > 0.9:
                        is_text = True
            except UnicodeDecodeError:
                is_text = False
        
        if is_text:
            # Handle as plain text - send as text content block
            try:
                text_content = document_bytes.decode('utf-8')
                content_blocks.append({
                    "type": "text",
                    "text": f"Here is the document content to extract data from:\n\n{text_content}"
                })
                return content_blocks
            except UnicodeDecodeError:
                pass  # Fall through to binary handling
        
        # Check if it's a PDF
        if filename.lower().endswith('.pdf') or document_bytes[:4] == b'%PDF':
            images = self._pdf_to_images(document_bytes)
            for i, img in enumerate(images):
                # Resize if too large (Claude has limits)
                max_dimension = 2048
                if img.width > max_dimension or img.height > max_dimension:
                    ratio = min(max_dimension / img.width, max_dimension / img.height)
                    new_size = (int(img.width * ratio), int(img.height * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                
                base64_image = self._image_to_base64(img)
                content_blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64_image
                    }
                })
        else:
            # Assume it's an image file
            img = Image.open(BytesIO(document_bytes))
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            base64_image = self._image_to_base64(img)
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64_image
                }
            })
        
        return content_blocks
    
    async def classify_document(self, document_bytes: bytes, filename: str) -> DocumentType:
        """Classify document type using vision."""
        try:
            image_blocks = self._prepare_document_images(document_bytes, filename)
            
            # Only send first page for classification
            content = [image_blocks[0]] if image_blocks else []
            content.append({"type": "text", "text": CLASSIFICATION_PROMPT})
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=50,
                messages=[{"role": "user", "content": content}]
            )
            
            # Parse response
            result_text = response.content[0].text.strip().lower()
            
            # Try to match to DocumentType
            try:
                return DocumentType(result_text)
            except ValueError:
                logger.warning(f"Unknown document type: {result_text}")
                return DocumentType.UNKNOWN
                
        except Exception as e:
            logger.error(f"Classification error: {e}")
            return DocumentType.UNKNOWN
    
    async def extract(
        self,
        document_bytes: bytes,
        filename: str,
        document_type: Optional[DocumentType] = None,
    ) -> ExtractionResult:
        """Extract structured data from document."""
        warnings = []
        errors = []
        
        try:
            # Classify if needed
            if document_type is None:
                document_type = await self.classify_document(document_bytes, filename)
                if document_type == DocumentType.UNKNOWN:
                    warnings.append("Could not confidently classify document type")
            
            # Get appropriate prompt
            prompt = EXTRACTION_PROMPTS.get(document_type, GENERIC_EXTRACTION_PROMPT)
            
            # Prepare images
            image_blocks = self._prepare_document_images(document_bytes, filename)
            
            # Build content
            content = image_blocks.copy()
            content.append({"type": "text", "text": prompt})
            
            # Call Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8000,
                messages=[{"role": "user", "content": content}]
            )
            
            # Parse JSON response
            result_text = response.content[0].text.strip()
            
            # Clean up response (remove markdown code blocks if present)
            if result_text.startswith("```"):
                # Remove first line and last line
                lines = result_text.split("\n")
                result_text = "\n".join(lines[1:-1])
            
            try:
                data = json.loads(result_text)
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error: {e}")
                errors.append(f"Failed to parse extraction result as JSON: {str(e)}")
                data = {"raw_response": result_text}
            
            # Extract any warnings from the data
            if "extraction_warnings" in data:
                warnings.extend(data.pop("extraction_warnings"))
            
            return ExtractionResult(
                success=len(errors) == 0,
                document_type=document_type,
                confidence=0.9 if len(errors) == 0 else 0.5,
                data=data,
                warnings=warnings,
                errors=errors,
                source_filename=filename,
                model_used=self.model,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            )
            
        except Exception as e:
            logger.error(f"Extraction error: {e}")
            return ExtractionResult(
                success=False,
                document_type=document_type or DocumentType.UNKNOWN,
                confidence=0.0,
                data={},
                errors=[str(e)],
                source_filename=filename,
                model_used=self.model,
            )
    
    async def extract_with_schema(
        self,
        document_bytes: bytes,
        filename: str,
        schema: dict[str, Any],
    ) -> ExtractionResult:
        """Extract data according to a custom schema."""
        prompt = f"""Extract data from this document according to this JSON schema:

{json.dumps(schema, indent=2)}

Return ONLY valid JSON matching this schema, no markdown formatting.
"""
        
        try:
            image_blocks = self._prepare_document_images(document_bytes, filename)
            content = image_blocks.copy()
            content.append({"type": "text", "text": prompt})
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8000,
                messages=[{"role": "user", "content": content}]
            )
            
            result_text = response.content[0].text.strip()
            if result_text.startswith("```"):
                lines = result_text.split("\n")
                result_text = "\n".join(lines[1:-1])
            
            data = json.loads(result_text)
            
            return ExtractionResult(
                success=True,
                document_type=DocumentType.UNKNOWN,
                confidence=0.85,
                data=data,
                source_filename=filename,
                model_used=self.model,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            )
            
        except Exception as e:
            logger.error(f"Schema extraction error: {e}")
            return ExtractionResult(
                success=False,
                document_type=DocumentType.UNKNOWN,
                confidence=0.0,
                data={},
                errors=[str(e)],
                source_filename=filename,
                model_used=self.model,
            )
