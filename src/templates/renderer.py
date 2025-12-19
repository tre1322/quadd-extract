"""
Template rendering engine.

Renders extracted data into newspaper-ready text using Jinja2 templates.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, BaseLoader, FileSystemLoader, TemplateNotFound

from src.schemas.common import DocumentType, ExtractionResult, RenderResult

logger = logging.getLogger(__name__)


# =============================================================================
# CUSTOM JINJA FILTERS
# =============================================================================

def dot_pad(text: str, width: int = 40) -> str:
    """Pad text with dots to specified width."""
    if len(text) >= width:
        return text
    dots_needed = width - len(text)
    return text + "." * dots_needed


def pct(made: Optional[int], attempted: Optional[int]) -> str:
    """Calculate and format percentage."""
    if made is None or attempted is None or attempted == 0:
        return ""
    percentage = round(made / attempted * 100)
    return f"({percentage}%)"


def format_stat(made: Optional[int], attempted: Optional[int]) -> str:
    """Format made/attempted stat."""
    if made is None or attempted is None:
        return "N/A"
    return f"{made}-{attempted}"


def format_score(score: Optional[int]) -> str:
    """Format score, handling None."""
    if score is None:
        return "—"
    return str(score)


def period_display(periods: list[int]) -> str:
    """Format period scores for display."""
    if not periods:
        return "—"
    return " ".join(str(p) for p in periods)


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert to int."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert to float."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def player_name_short(name: str, max_length: int = 15) -> str:
    """Shorten player name if needed."""
    if len(name) <= max_length:
        return name
    # Try last name only
    parts = name.split()
    if len(parts) > 1:
        return parts[-1][:max_length]
    return name[:max_length]


# =============================================================================
# BUILT-IN TEMPLATES
# =============================================================================

# Classic "Windom Style" basketball template
BASKETBALL_WINDOM_TEMPLATE = """
{%- set away = data.away_team -%}
{%- set home = data.home_team -%}
{#- Calculate team totals from player stats (more reliable than team stats table) -#}
{%- set away_fg_made = namespace(val=0) -%}
{%- set away_fg_att = namespace(val=0) -%}
{%- set away_3_made = namespace(val=0) -%}
{%- set away_3_att = namespace(val=0) -%}
{%- set away_ft_made = namespace(val=0) -%}
{%- set away_ft_att = namespace(val=0) -%}
{%- for p in away.players -%}
  {%- set away_fg_made.val = away_fg_made.val + (p.fg_made or 0) -%}
  {%- set away_fg_att.val = away_fg_att.val + (p.fg_attempted or 0) -%}
  {%- set away_3_made.val = away_3_made.val + (p.three_made or 0) -%}
  {%- set away_3_att.val = away_3_att.val + (p.three_attempted or 0) -%}
  {%- set away_ft_made.val = away_ft_made.val + (p.ft_made or 0) -%}
  {%- set away_ft_att.val = away_ft_att.val + (p.ft_attempted or 0) -%}
{%- endfor -%}
{%- set home_fg_made = namespace(val=0) -%}
{%- set home_fg_att = namespace(val=0) -%}
{%- set home_3_made = namespace(val=0) -%}
{%- set home_3_att = namespace(val=0) -%}
{%- set home_ft_made = namespace(val=0) -%}
{%- set home_ft_att = namespace(val=0) -%}
{%- for p in home.players -%}
  {%- set home_fg_made.val = home_fg_made.val + (p.fg_made or 0) -%}
  {%- set home_fg_att.val = home_fg_att.val + (p.fg_attempted or 0) -%}
  {%- set home_3_made.val = home_3_made.val + (p.three_made or 0) -%}
  {%- set home_3_att.val = home_3_att.val + (p.three_attempted or 0) -%}
  {%- set home_ft_made.val = home_ft_made.val + (p.ft_made or 0) -%}
  {%- set home_ft_att.val = home_ft_att.val + (p.ft_attempted or 0) -%}
{%- endfor -%}
{#- Build 3PT shooters list for each team -#}
{%- set away_3pt_shooters = [] -%}
{%- for p in away.players -%}
  {%- if p.three_made and p.three_made > 0 -%}
    {%- set shooter = p.name.split()[-1] ~ (' ' ~ p.three_made | string if p.three_made > 1 else '') -%}
    {%- set _ = away_3pt_shooters.append(shooter) -%}
  {%- endif -%}
{%- endfor -%}
{%- set home_3pt_shooters = [] -%}
{%- for p in home.players -%}
  {%- if p.three_made and p.three_made > 0 -%}
    {%- set shooter = p.name.split()[-1] ~ (' ' ~ p.three_made | string if p.three_made > 1 else '') -%}
    {%- set _ = home_3pt_shooters.append(shooter) -%}
  {%- endif -%}
{%- endfor -%}
{#- Get fouled out players (5+ fouls) -#}
{%- set away_fouled_out = [] -%}
{%- for p in away.players -%}
  {%- if p.fouls and p.fouls >= 5 -%}
    {%- set _ = away_fouled_out.append(p.name.split()[-1]) -%}
  {%- endif -%}
{%- endfor -%}
{%- set home_fouled_out = [] -%}
{%- for p in home.players -%}
  {%- if p.fouls and p.fouls >= 5 -%}
    {%- set _ = home_fouled_out.append(p.name.split()[-1]) -%}
  {%- endif -%}
{%- endfor -%}
{{ away.name | dot_pad(40) }}{{ away.period_scores | period_display }} — {{ away.final_score }}
{{ home.name | dot_pad(40) }}{{ home.period_scores | period_display }} — {{ home.final_score }}

{{ away.name }} (FG-FT-TP): {% for p in away.players %}{{ p.name.split()[-1] }} {{ p.fg_made | safe_int }}-{{ p.ft_made | safe_int }}-{{ p.points | safe_int }}{% if not loop.last %}; {% endif %}{% endfor %}. FG: {{ away_fg_made.val }}-{{ away_fg_att.val }} {{ pct(away_fg_made.val, away_fg_att.val) }}. FT: {{ away_ft_made.val }}-{{ away_ft_att.val }} {{ pct(away_ft_made.val, away_ft_att.val) }}. 3Pt. FG: {{ away_3_made.val }}-{{ away_3_att.val }} {{ pct(away_3_made.val, away_3_att.val) }}{% if away_3pt_shooters %} — {{ away_3pt_shooters | join(', ') }}{% endif %}. Fouls: {{ away.fouls | safe_int }}. Fouled out: {% if away_fouled_out %}{{ away_fouled_out | join(', ') }}{% else %}None{% endif %}. Rebs: {{ away.total_rebounds | safe_int }}. TOs: {{ away.turnovers | safe_int }}.

{{ home.name }} (FG-FT-TP): {% for p in home.players %}{{ p.name.split()[-1] }} {{ p.fg_made | safe_int }}-{{ p.ft_made | safe_int }}-{{ p.points | safe_int }}{% if not loop.last %}; {% endif %}{% endfor %}. FG: {{ home_fg_made.val }}-{{ home_fg_att.val }} {{ pct(home_fg_made.val, home_fg_att.val) }}. FT: {{ home_ft_made.val }}-{{ home_ft_att.val }} {{ pct(home_ft_made.val, home_ft_att.val) }}. 3Pt. FG: {{ home_3_made.val }}-{{ home_3_att.val }} {{ pct(home_3_made.val, home_3_att.val) }}{% if home_3pt_shooters %} — {{ home_3pt_shooters | join(', ') }}{% endif %}. Fouls: {{ home.fouls | safe_int }}. Fouled out: {% if home_fouled_out %}{{ home_fouled_out | join(', ') }}{% else %}None{% endif %}. Rebs: {{ home.total_rebounds | safe_int }}. TOs: {{ home.turnovers | safe_int }}.
""".strip()


# Detailed box score template with all stats
BASKETBALL_DETAILED_TEMPLATE = """
{%- set away = data.away_team -%}
{%- set home = data.home_team -%}
{{ away.name }} {{ away.final_score }}, {{ home.name }} {{ home.final_score }}

Score by Period:
{{ "Team" | dot_pad(20) }}{% for i in range(away.period_scores | length) %}{{ "Q" ~ (i+1) }}  {% endfor %}Final
{{ away.name | dot_pad(20) }}{% for p in away.period_scores %}{{ p }}  {% endfor %}{{ away.final_score }}
{{ home.name | dot_pad(20) }}{% for p in home.period_scores %}{{ p }}  {% endfor %}{{ home.final_score }}

{{ away.name }}
Player                  Pts  FG      3PT     FT      Reb  Ast  Stl  Blk  TO
{% for p in away.players -%}
{{ p.name[:22] | dot_pad(22) }}  {{ "%3d" | format(p.points | safe_int) }}  {{ format_stat(p.fg_made, p.fg_attempted) }}  {{ format_stat(p.three_made, p.three_attempted) }}  {{ format_stat(p.ft_made, p.ft_attempted) }}  {{ "%3d" | format(p.total_rebounds | safe_int) }}  {{ "%3d" | format(p.assists | safe_int) }}  {{ "%3d" | format(p.steals | safe_int) }}  {{ "%3d" | format(p.blocks | safe_int) }}  {{ "%2d" | format(p.turnovers | safe_int) }}
{% endfor %}
TOTALS                  {{ "%3d" | format(away.final_score) }}  {{ format_stat(away.fg_made, away.fg_attempted) }}  {{ format_stat(away.three_made, away.three_attempted) }}  {{ format_stat(away.ft_made, away.ft_attempted) }}  {{ "%3d" | format(away.total_rebounds | safe_int) }}  {{ "%3d" | format(away.assists | safe_int) }}  {{ "%3d" | format(away.steals | safe_int) }}  {{ "%3d" | format(away.blocks | safe_int) }}  {{ "%2d" | format(away.turnovers | safe_int) }}

{{ home.name }}
Player                  Pts  FG      3PT     FT      Reb  Ast  Stl  Blk  TO
{% for p in home.players -%}
{{ p.name[:22] | dot_pad(22) }}  {{ "%3d" | format(p.points | safe_int) }}  {{ format_stat(p.fg_made, p.fg_attempted) }}  {{ format_stat(p.three_made, p.three_attempted) }}  {{ format_stat(p.ft_made, p.ft_attempted) }}  {{ "%3d" | format(p.total_rebounds | safe_int) }}  {{ "%3d" | format(p.assists | safe_int) }}  {{ "%3d" | format(p.steals | safe_int) }}  {{ "%3d" | format(p.blocks | safe_int) }}  {{ "%2d" | format(p.turnovers | safe_int) }}
{% endfor %}
TOTALS                  {{ "%3d" | format(home.final_score) }}  {{ format_stat(home.fg_made, home.fg_attempted) }}  {{ format_stat(home.three_made, home.three_attempted) }}  {{ format_stat(home.ft_made, home.ft_attempted) }}  {{ "%3d" | format(home.total_rebounds | safe_int) }}  {{ "%3d" | format(home.assists | safe_int) }}  {{ "%3d" | format(home.steals | safe_int) }}  {{ "%3d" | format(home.blocks | safe_int) }}  {{ "%2d" | format(home.turnovers | safe_int) }}
""".strip()


# Hockey newspaper template
HOCKEY_TEMPLATE = """
{%- set away = data.away_team -%}
{%- set home = data.home_team -%}
{%- set plays = data.scoring_plays or [] -%}
{{ away.name | dot_pad(45) }}{{ away.period_scores | join(' ') }} — {{ away.final_score }}
{{ home.name | dot_pad(45) }}{{ home.period_scores | join(' ') }} — {{ home.final_score }}

{#- Group scoring plays by period -#}
{%- set periods = {'1st': [], '2nd': [], '3rd': [], 'OT': [], 'OT1': [], 'OT2': []} -%}
{%- for play in plays -%}
  {%- set period_key = play.period if play.period in periods else 'OT' -%}
  {%- set _ = periods[period_key].append(play) -%}
{%- endfor -%}

{%- set goal_num = namespace(value=1) -%}
{%- for period_name, period_label in [('1st', 'FIRST PERIOD'), ('2nd', 'SECOND PERIOD'), ('3rd', 'THIRD PERIOD'), ('OT', 'OVERTIME'), ('OT1', 'OVERTIME'), ('OT2', 'SECOND OVERTIME')] -%}
{%- if periods[period_name] %}
{{ period_label }}: {% for play in periods[period_name] -%}
{{ goal_num.value }}. {{ play.team }}: {{ play.scorer | player_name_short }}{% if play.assists %} ({% for a in play.assists %}{{ a | player_name_short }}{% if not loop.last %}, {% endif %}{% endfor %}){% else %} (u/a){% endif %} {{ play.time }}{% if play.type == 'power_play' %}, pp{% elif play.type == 'shorthanded' %}, shorthanded{% endif %}{% if play.empty_net %}, en{% endif %}. {% set goal_num.value = goal_num.value + 1 %}{% endfor %}
{% endif -%}
{%- endfor %}
SUMMARY: Shots on goal: {{ away.name }} {{ away.shots_on_goal | safe_int }}, {{ home.name }} {{ home.shots_on_goal | safe_int }}. Power plays: {{ away.name }} {{ away.power_play_goals | safe_int }}-{{ away.power_play_opportunities | safe_int }}, {{ home.name }} {{ home.power_play_goals | safe_int }}-{{ home.power_play_opportunities | safe_int }}. Goalies: {{ away.name }}{% for g in away.goalies %}, {{ g.name }} ({{ g.shots_faced | safe_int }} shots, {{ g.saves | safe_int }} saves){% endfor %}; {{ home.name }}{% for g in home.goalies %}, {{ g.name }} ({{ g.shots_faced | safe_int }} shots, {{ g.saves | safe_int }} saves){% endfor %}.
""".strip()


# Wrestling dual meet template
WRESTLING_TEMPLATE = """
{{ data.team_1_name }} {{ data.team_1_score }}, {{ data.team_2_name }} {{ data.team_2_score }}

{% for m in data.matches -%}
{{ m.weight_class }}: {{ m.winner_name }} ({{ m.winner_school[:3] | upper }}) {% if m.win_type == "pin" %}pinned{{ " " ~ m.loser_name ~ " in " ~ m.time if m.time }}{% elif m.win_type == "decision" %}dec. {{ m.loser_name }}, {{ m.score }}{% elif m.win_type == "major_decision" %}major dec. {{ m.loser_name }}, {{ m.score }}{% elif m.win_type == "tech_fall" %}tech. fall {{ m.loser_name }}, {{ m.score }}{% elif m.win_type == "forfeit" %}won by forfeit{% else %}{{ m.win_type }} {{ m.loser_name }}{% endif %}
{% endfor %}
""".strip()


# Gymnastics meet template
GYMNASTICS_TEMPLATE = """
{% if data.teams | length > 1 -%}
Team Scores:
{% for t in data.teams -%}
{{ t.name }}: {{ t.final_score }}
{% endfor %}
{% endif %}

{% for event in data.events %}
{{ event.event_name | title }}:
{% for r in event.results -%}
{{ loop.index }}. {{ r.name }} - {% if event.event_name == "vault" %}{{ r.vault_score }}{% elif event.event_name == "bars" %}{{ r.bars_score }}{% elif event.event_name == "beam" %}{{ r.beam_score }}{% elif event.event_name == "floor" %}{{ r.floor_score }}{% endif %}
{% endfor %}

{% endfor %}
{% if data.all_around %}
All-Around:
{% for r in data.all_around -%}
{{ loop.index }}. {{ r.name }} - {{ r.all_around_score }}
{% endfor %}
{% endif %}
""".strip()


# Generic/fallback template
GENERIC_TEMPLATE = """
{% if data.title %}{{ data.title }}{% endif %}
{% if data.date %}Date: {{ data.date }}{% endif %}

{% if data.parties %}
Parties: {{ data.parties | join(", ") }}
{% endif %}

{% if data.key_values %}
{% for key, value in data.key_values.items() %}
{{ key }}: {{ value }}
{% endfor %}
{% endif %}

{% if data.tables %}
{% for table in data.tables %}
{% if table.headers %}{{ table.headers | join(" | ") }}{% endif %}
{% for row in table.rows %}
{{ row | join(" | ") }}
{% endfor %}

{% endfor %}
{% endif %}

{% if data.body_text %}
{{ data.body_text }}
{% endif %}
""".strip()


# =============================================================================
# BUILT-IN TEMPLATE REGISTRY
# =============================================================================

BUILTIN_TEMPLATES = {
    # Basketball
    "basketball_windom": {
        "id": "basketball_windom",
        "name": "Windom Style Basketball",
        "document_types": [DocumentType.BASKETBALL],
        "template": BASKETBALL_WINDOM_TEMPLATE,
        "description": "Classic Windom newspaper style with (FG-FT-TP) player lines",
    },
    "basketball_detailed": {
        "id": "basketball_detailed",
        "name": "Detailed Box Score",
        "document_types": [DocumentType.BASKETBALL],
        "template": BASKETBALL_DETAILED_TEMPLATE,
        "description": "Full box score with all player stats in table format",
    },
    
    # Hockey
    "hockey_standard": {
        "id": "hockey_standard",
        "name": "Standard Hockey",
        "document_types": [DocumentType.HOCKEY],
        "template": HOCKEY_TEMPLATE,
        "description": "Standard hockey game summary with scoring plays",
    },
    
    # Wrestling
    "wrestling_dual": {
        "id": "wrestling_dual",
        "name": "Wrestling Dual Meet",
        "document_types": [DocumentType.WRESTLING],
        "template": WRESTLING_TEMPLATE,
        "description": "Wrestling dual meet results by weight class",
    },
    
    # Gymnastics
    "gymnastics_meet": {
        "id": "gymnastics_meet",
        "name": "Gymnastics Meet",
        "document_types": [DocumentType.GYMNASTICS],
        "template": GYMNASTICS_TEMPLATE,
        "description": "Gymnastics meet results by event",
    },
    
    # Generic
    "generic": {
        "id": "generic",
        "name": "Generic Document",
        "document_types": [DocumentType.UNKNOWN, DocumentType.TABULAR],
        "template": GENERIC_TEMPLATE,
        "description": "Fallback template for unclassified documents",
    },
}


# =============================================================================
# TEMPLATE RENDERER
# =============================================================================

class TemplateRenderer:
    """
    Renders extracted data to newspaper text using Jinja2 templates.
    """
    
    def __init__(self, templates_dir: Optional[Path] = None):
        """
        Initialize the renderer.
        
        Args:
            templates_dir: Optional directory for custom templates
        """
        self.templates_dir = templates_dir
        self._custom_templates: dict[str, dict] = {}
        
        # Create Jinja environment
        if templates_dir and templates_dir.exists():
            self.env = Environment(loader=FileSystemLoader(str(templates_dir)))
        else:
            self.env = Environment(loader=BaseLoader())
        
        # Register custom filters
        self.env.filters["dot_pad"] = dot_pad
        self.env.filters["pct"] = pct
        self.env.filters["format_stat"] = format_stat
        self.env.filters["format_score"] = format_score
        self.env.filters["period_display"] = period_display
        self.env.filters["safe_int"] = safe_int
        self.env.filters["safe_float"] = safe_float
        self.env.filters["player_name_short"] = player_name_short
        
        # Register helper functions as globals
        self.env.globals["pct"] = pct
        self.env.globals["format_stat"] = format_stat
        self.env.globals["safe_int"] = safe_int
        self.env.globals["safe_float"] = safe_float
    
    def get_template(self, template_id: str) -> Optional[dict]:
        """Get template definition by ID."""
        # Check custom templates first
        if template_id in self._custom_templates:
            return self._custom_templates[template_id]
        
        # Check built-in templates
        if template_id in BUILTIN_TEMPLATES:
            return BUILTIN_TEMPLATES[template_id]
        
        return None
    
    def list_templates(self, document_type: Optional[DocumentType] = None) -> list[dict]:
        """List available templates, optionally filtered by document type."""
        all_templates = {**BUILTIN_TEMPLATES, **self._custom_templates}
        
        if document_type is None:
            return [
                {"id": t["id"], "name": t["name"], "description": t.get("description", "")}
                for t in all_templates.values()
            ]
        
        return [
            {"id": t["id"], "name": t["name"], "description": t.get("description", "")}
            for t in all_templates.values()
            if document_type in t.get("document_types", [])
        ]
    
    def register_template(
        self,
        template_id: str,
        name: str,
        template: str,
        document_types: list[DocumentType],
        description: str = "",
    ) -> None:
        """Register a custom template."""
        self._custom_templates[template_id] = {
            "id": template_id,
            "name": name,
            "template": template,
            "document_types": document_types,
            "description": description,
        }
    
    def find_template_for_type(self, document_type: DocumentType) -> Optional[str]:
        """Find a suitable template ID for a document type."""
        # Check custom templates first
        for template_id, template in self._custom_templates.items():
            if document_type in template.get("document_types", []):
                return template_id
        
        # Check built-in templates
        for template_id, template in BUILTIN_TEMPLATES.items():
            if document_type in template.get("document_types", []):
                return template_id
        
        # Fallback to generic
        return "generic"
    
    def render(
        self,
        extraction: ExtractionResult,
        template_id: Optional[str] = None,
    ) -> RenderResult:
        """
        Render extracted data using a template.
        
        Args:
            extraction: Extraction result to render
            template_id: Template to use (auto-selects if not provided)
            
        Returns:
            RenderResult with formatted text
        """
        warnings = []
        
        # Auto-select template if not provided
        if template_id is None:
            template_id = self.find_template_for_type(extraction.document_type)
            if template_id:
                warnings.append(f"Auto-selected template: {template_id}")
        
        # Get template
        template_def = self.get_template(template_id)
        if template_def is None:
            return RenderResult(
                success=False,
                newspaper_text="",
                template_id=template_id or "unknown",
                extraction=extraction,
                warnings=[f"Template not found: {template_id}"],
            )
        
        # Render
        try:
            template = self.env.from_string(template_def["template"])
            rendered = template.render(data=extraction.data)
            
            # Clean up whitespace
            lines = [line.rstrip() for line in rendered.split("\n")]
            rendered = "\n".join(lines)
            rendered = rendered.strip()
            
            return RenderResult(
                success=True,
                newspaper_text=rendered,
                template_id=template_id,
                extraction=extraction,
                warnings=warnings,
            )
            
        except Exception as e:
            logger.error(f"Template render error: {e}")
            return RenderResult(
                success=False,
                newspaper_text="",
                template_id=template_id,
                extraction=extraction,
                warnings=warnings + [f"Render error: {str(e)}"],
            )
