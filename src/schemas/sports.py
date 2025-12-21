"""
DEPRECATED - Sports schema models (NOT USED).

⚠️ WARNING: These Pydantic schemas are NOT used anywhere in the codebase.
⚠️ They exist for backward compatibility only.

## Why Deprecated

These hardcoded schemas violate the project charter (transformer.md):
- ❌ Sport-specific code (basketball, hockey, wrestling fields)
- ❌ Won't work for new document types (honor roll, legal notices, invoices)
- ❌ Prevents the system from learning new structures

## Current Approach (Charter-Compliant)

The system uses **dynamic dict-based data structures** learned from examples:

1. **Schema is implicit in extraction_ops**:
   - field_path defines structure: "items[].student_name"
   - transform defines type: "to_int", "to_float", "strip"

2. **ExtractionResult.data is dict[str, Any]** (see src/schemas/common.py):
   - Generic - works for ANY document type
   - Flexible - adapts to learned structure
   - No hardcoded fields

3. **Examples**:

   Honor roll extraction:
   {
       "items": [
           {"student_name": "John", "grade_level": 9, "gpa": 3.8}
       ]
   }

   Basketball extraction:
   {
       "team1": {"name": "Windom", "final_score": 72, "players": [...]}
   }

   Legal notice extraction:
   {
       "cases": [
           {"case_number": "2024-CV-1234", "plaintiff": "Smith", ...}
       ]
   }

All use the SAME generic dict structure - no sport-specific models needed!

## Original Documentation (Historical)

These models were designed to be universal across different sports while
capturing sport-specific details when available. However, they became too
rigid and prevented the system from learning new document types.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, computed_field, model_validator


# =============================================================================
# ENUMS
# =============================================================================

class SportType(str, Enum):
    """Types of sports we support."""
    BASKETBALL = "basketball"
    HOCKEY = "hockey"
    WRESTLING = "wrestling"
    GYMNASTICS = "gymnastics"
    BASEBALL = "baseball"
    FOOTBALL = "football"
    VOLLEYBALL = "volleyball"
    SOCCER = "soccer"
    GOLF = "golf"
    TENNIS = "tennis"
    TRACK = "track"
    CROSS_COUNTRY = "cross_country"
    SWIMMING = "swimming"


class Gender(str, Enum):
    """Gender designation for teams."""
    BOYS = "boys"
    GIRLS = "girls"
    MENS = "mens"
    WOMENS = "womens"
    COED = "coed"


class Level(str, Enum):
    """Competition level."""
    VARSITY = "varsity"
    JV = "jv"
    FRESHMAN = "freshman"
    MIDDLE_SCHOOL = "middle_school"
    YOUTH = "youth"


class GameResult(str, Enum):
    """Game result from perspective of first team listed."""
    WIN = "W"
    LOSS = "L"
    TIE = "T"
    OT_WIN = "OTW"
    OT_LOSS = "OTL"
    SO_WIN = "SOW"  # Shootout win (hockey)
    SO_LOSS = "SOL"  # Shootout loss


# =============================================================================
# PLAYER STATS - Universal model with sport-specific optional fields
# =============================================================================

class PlayerStats(BaseModel):
    """
    Universal player statistics model.
    
    Core fields work for all sports. Sport-specific fields are optional
    and only populated when relevant. We capture EVERYTHING available
    and let templates decide what to display.
    """
    # Identity
    name: str
    jersey_number: Optional[str] = None
    position: Optional[str] = None
    
    # Universal stats (most sports have some form of these)
    points: Optional[int] = None
    
    # Basketball specific - Shooting
    fg_made: Optional[int] = None
    fg_attempted: Optional[int] = None
    two_made: Optional[int] = None  # 2-point field goals
    two_attempted: Optional[int] = None
    three_made: Optional[int] = None
    three_attempted: Optional[int] = None
    ft_made: Optional[int] = None
    ft_attempted: Optional[int] = None
    
    # Basketball specific - Rebounds
    offensive_rebounds: Optional[int] = None
    defensive_rebounds: Optional[int] = None
    total_rebounds: Optional[int] = None
    
    # Basketball specific - Playmaking/Defense
    assists: Optional[int] = None
    steals: Optional[int] = None
    blocks: Optional[int] = None
    turnovers: Optional[int] = None
    deflections: Optional[int] = None  # ADDED
    charges_taken: Optional[int] = None  # ADDED
    
    # Basketball specific - Other
    fouls: Optional[int] = None
    technical_fouls: Optional[int] = None  # ADDED
    flagrant_fouls: Optional[int] = None  # ADDED
    minutes: Optional[float] = None  # Changed to float for partial minutes
    plus_minus: Optional[int] = None
    
    # Basketball advanced stats (if available)
    effective_fg_pct: Optional[float] = None  # ADDED
    true_shooting_pct: Optional[float] = None  # ADDED
    usage_rate: Optional[float] = None  # ADDED
    
    # Basketball lineup/rotation
    starter: Optional[bool] = None  # ADDED - was player a starter?
    dnp: Optional[bool] = None  # ADDED - Did Not Play
    dnp_reason: Optional[str] = None  # ADDED - "Coach's Decision", "Injury", etc.
    
    # Hockey specific - Skater stats
    goals: Optional[int] = None
    hockey_assists: Optional[int] = None  # Different from basketball assists
    primary_assists: Optional[int] = None  # ADDED
    secondary_assists: Optional[int] = None  # ADDED
    penalty_minutes: Optional[int] = None
    minor_penalties: Optional[int] = None  # ADDED
    major_penalties: Optional[int] = None  # ADDED
    shots_on_goal: Optional[int] = None
    shot_percentage: Optional[float] = None  # ADDED
    faceoff_wins: Optional[int] = None
    faceoff_losses: Optional[int] = None
    faceoff_percentage: Optional[float] = None  # ADDED
    plus_minus_hockey: Optional[int] = None
    hits: Optional[int] = None  # ADDED
    blocked_shots: Optional[int] = None  # ADDED
    giveaways: Optional[int] = None  # ADDED
    takeaways: Optional[int] = None  # ADDED
    time_on_ice: Optional[str] = None  # ADDED - "18:45" format
    power_play_goals: Optional[int] = None  # ADDED
    power_play_assists: Optional[int] = None  # ADDED
    shorthanded_goals: Optional[int] = None  # ADDED
    game_winning_goal: Optional[bool] = None  # ADDED
    
    # Wrestling specific
    match_result: Optional[str] = None  # "W", "L", "Pin", "Dec", "MD", "TF", "FF"
    win_type: Optional[str] = None  # "pin", "decision", "major_decision", "tech_fall", "forfeit", "default", "dq"
    match_time: Optional[str] = None  # Time of pin/match "3:45"
    match_score: Optional[str] = None  # ADDED - "8-3" for decisions
    opponent_name: Optional[str] = None
    opponent_school: Optional[str] = None
    weight_class: Optional[str] = None
    team_points_earned: Optional[float] = None  # Points earned for team (6 for pin, etc.)
    takedowns: Optional[int] = None  # ADDED
    escapes: Optional[int] = None  # ADDED
    reversals: Optional[int] = None  # ADDED
    near_fall_2: Optional[int] = None  # ADDED - 2-point near falls
    near_fall_3: Optional[int] = None  # ADDED - 3-point near falls
    riding_time: Optional[str] = None  # ADDED - "1:23" format
    riding_time_points: Optional[int] = None  # ADDED - 0 or 1
    warnings: Optional[int] = None  # ADDED
    stalling_calls: Optional[int] = None  # ADDED
    seed: Optional[int] = None  # ADDED - tournament seed
    placement: Optional[int] = None  # ADDED - tournament placement (1st, 2nd, etc.)
    
    # Gymnastics specific
    vault_score: Optional[float] = None
    vault_difficulty: Optional[float] = None  # ADDED
    vault_execution: Optional[float] = None  # ADDED
    bars_score: Optional[float] = None
    bars_difficulty: Optional[float] = None  # ADDED
    bars_execution: Optional[float] = None  # ADDED
    beam_score: Optional[float] = None
    beam_difficulty: Optional[float] = None  # ADDED
    beam_execution: Optional[float] = None  # ADDED
    floor_score: Optional[float] = None
    floor_difficulty: Optional[float] = None  # ADDED
    floor_execution: Optional[float] = None  # ADDED
    all_around_score: Optional[float] = None
    event_placement: Optional[int] = None  # ADDED - placement in individual event
    all_around_placement: Optional[int] = None  # ADDED
    
    # Baseball specific (for batting) - capture EVERYTHING
    at_bats: Optional[int] = None
    runs: Optional[int] = None
    hits: Optional[int] = None
    rbis: Optional[int] = None
    walks: Optional[int] = None
    strikeouts: Optional[int] = None
    doubles: Optional[int] = None
    triples: Optional[int] = None
    home_runs: Optional[int] = None
    stolen_bases: Optional[int] = None
    caught_stealing: Optional[int] = None  # ADDED
    sacrifice_bunts: Optional[int] = None  # ADDED
    sacrifice_flies: Optional[int] = None  # ADDED
    hit_by_pitch: Optional[int] = None  # ADDED
    ground_into_dp: Optional[int] = None  # ADDED - grounded into double play
    left_on_base: Optional[int] = None  # ADDED
    total_bases: Optional[int] = None  # ADDED
    batting_average: Optional[float] = None  # ADDED - if shown
    on_base_pct: Optional[float] = None  # ADDED
    slugging_pct: Optional[float] = None  # ADDED
    
    # Baseball fielding
    putouts: Optional[int] = None  # ADDED
    fielding_assists: Optional[int] = None  # ADDED
    errors: Optional[int] = None  # ADDED
    fielding_percentage: Optional[float] = None  # ADDED
    
    # Computed fields
    @computed_field
    @property
    def rebounds(self) -> Optional[int]:
        """Total rebounds (computed if not directly set)."""
        if self.total_rebounds is not None:
            return self.total_rebounds
        if self.offensive_rebounds is not None and self.defensive_rebounds is not None:
            return self.offensive_rebounds + self.defensive_rebounds
        return None
    
    @computed_field
    @property
    def fg_percentage(self) -> Optional[float]:
        """Field goal percentage."""
        if self.fg_made is not None and self.fg_attempted and self.fg_attempted > 0:
            return round(self.fg_made / self.fg_attempted * 100, 1)
        return None


class GoalieStats(BaseModel):
    """Hockey goalie-specific stats - capture EVERYTHING."""
    name: str
    jersey_number: Optional[str] = None
    
    # Basic stats
    saves: Optional[int] = None
    goals_against: Optional[int] = None
    shots_faced: Optional[int] = None
    minutes_played: Optional[float] = None  # Changed to float for partial minutes
    
    # Result
    decision: Optional[str] = None  # "W", "L", "OTL", "SOL", None (no decision)
    shutout: Optional[bool] = None
    
    # Period breakdown
    first_period_saves: Optional[int] = None
    first_period_shots: Optional[int] = None
    second_period_saves: Optional[int] = None
    second_period_shots: Optional[int] = None
    third_period_saves: Optional[int] = None
    third_period_shots: Optional[int] = None
    ot_saves: Optional[int] = None
    ot_shots: Optional[int] = None
    
    # Additional
    goals_against_average: Optional[float] = None  # Season GAA if shown
    penalty_minutes: Optional[int] = None
    assists: Optional[int] = None  # Goalies can get assists
    
    @computed_field
    @property
    def save_percentage(self) -> Optional[float]:
        if self.saves is not None and self.shots_faced and self.shots_faced > 0:
            return round(self.saves / self.shots_faced * 100, 1)
        return None


class PitcherStats(BaseModel):
    """Baseball pitcher-specific stats - capture EVERYTHING."""
    name: str
    jersey_number: Optional[str] = None
    
    # Basic stats
    innings_pitched: Optional[float] = None  # 6.2 = 6 and 2/3 innings
    hits_allowed: Optional[int] = None
    runs_allowed: Optional[int] = None
    earned_runs: Optional[int] = None
    walks_allowed: Optional[int] = None
    strikeouts_pitched: Optional[int] = None
    home_runs_allowed: Optional[int] = None
    
    # Decision
    decision: Optional[str] = None  # "W", "L", "S" (save), "H" (hold), "BS" (blown save)
    win: Optional[bool] = None
    loss: Optional[bool] = None
    save: Optional[bool] = None
    hold: Optional[bool] = None
    blown_save: Optional[bool] = None
    
    # Pitch counts
    pitch_count: Optional[int] = None
    strikes: Optional[int] = None
    balls: Optional[int] = None
    
    # Batters faced
    batters_faced: Optional[int] = None
    
    # Additional
    wild_pitches: Optional[int] = None
    hit_by_pitch: Optional[int] = None
    balks: Optional[int] = None
    ground_outs: Optional[int] = None
    fly_outs: Optional[int] = None
    
    # Inherited runners
    inherited_runners: Optional[int] = None
    inherited_runners_scored: Optional[int] = None
    
    @computed_field
    @property
    def era(self) -> Optional[float]:
        """Calculated ERA."""
        if self.earned_runs is not None and self.innings_pitched and self.innings_pitched > 0:
            return round((self.earned_runs / self.innings_pitched) * 9, 2)
        return None
    
    @computed_field
    @property
    def whip(self) -> Optional[float]:
        """Walks + Hits per Inning Pitched."""
        if self.innings_pitched and self.innings_pitched > 0:
            walks = self.walks_allowed or 0
            hits = self.hits_allowed or 0
            return round((walks + hits) / self.innings_pitched, 2)
        return None


# =============================================================================
# TEAM STATS
# =============================================================================

class TeamStats(BaseModel):
    """
    Team-level statistics.
    
    Works for all sports with sport-specific optional fields.
    We capture EVERYTHING available and let templates decide what to display.
    """
    # Identity
    name: str
    abbreviation: Optional[str] = None
    
    # Score
    final_score: int
    period_scores: list[int] = Field(default_factory=list)
    
    # Record
    record: Optional[str] = None  # e.g., "10-5"
    conference_record: Optional[str] = None
    
    # Basketball team totals - Shooting
    fg_made: Optional[int] = None
    fg_attempted: Optional[int] = None
    two_made: Optional[int] = None  # 2-point field goals
    two_attempted: Optional[int] = None
    three_made: Optional[int] = None
    three_attempted: Optional[int] = None
    ft_made: Optional[int] = None
    ft_attempted: Optional[int] = None
    
    # Basketball team totals - Shooting Percentages (pre-calculated)
    fg_percentage: Optional[float] = None
    two_percentage: Optional[float] = None
    three_percentage: Optional[float] = None
    ft_percentage: Optional[float] = None
    effective_fg_percentage: Optional[float] = None  # ADDED
    
    # Basketball team totals - Rebounds
    total_rebounds: Optional[int] = None
    offensive_rebounds: Optional[int] = None
    defensive_rebounds: Optional[int] = None
    
    # Basketball team totals - Playmaking/Defense
    assists: Optional[int] = None
    steals: Optional[int] = None
    blocks: Optional[int] = None
    turnovers: Optional[int] = None
    deflections: Optional[int] = None  # ADDED
    charges_taken: Optional[int] = None  # ADDED
    
    # Basketball team totals - Fouls
    fouls: Optional[int] = None
    technical_fouls: Optional[int] = None  # ADDED
    flagrant_fouls: Optional[int] = None  # ADDED
    
    # Basketball team totals - Advanced/Situational
    points_per_possession: Optional[float] = None  # ADDED
    transition_points: Optional[int] = None  # ADDED
    points_off_turnovers: Optional[int] = None  # ADDED
    second_chance_points: Optional[int] = None  # ADDED
    points_in_paint: Optional[int] = None  # ADDED
    bench_points: Optional[int] = None
    fast_break_points: Optional[int] = None
    
    # Basketball team totals - Timeouts/Other
    timeouts_remaining: Optional[int] = None  # ADDED
    timeouts_taken: Optional[int] = None
    largest_lead: Optional[int] = None  # ADDED
    time_of_possession: Optional[str] = None  # ADDED
    
    # Hockey team totals
    shots_on_goal: Optional[int] = None
    power_play_goals: Optional[int] = None
    power_play_opportunities: Optional[int] = None
    power_play_percentage: Optional[float] = None  # ADDED
    penalty_kill_percentage: Optional[float] = None  # ADDED
    penalty_minutes: Optional[int] = None
    minor_penalties: Optional[int] = None  # ADDED
    major_penalties: Optional[int] = None  # ADDED
    hits: Optional[int] = None  # ADDED
    blocked_shots: Optional[int] = None  # ADDED
    giveaways: Optional[int] = None  # ADDED
    takeaways: Optional[int] = None  # ADDED
    faceoff_wins: Optional[int] = None  # ADDED
    faceoff_losses: Optional[int] = None  # ADDED
    faceoff_percentage: Optional[float] = None  # ADDED
    
    # Wrestling team totals
    matches_won: Optional[int] = None
    matches_lost: Optional[int] = None
    pins: Optional[int] = None
    tech_falls: Optional[int] = None  # ADDED
    major_decisions: Optional[int] = None  # ADDED
    decisions: Optional[int] = None  # ADDED
    forfeits_won: Optional[int] = None  # ADDED
    forfeits_lost: Optional[int] = None  # ADDED
    
    # Gymnastics team totals
    team_vault: Optional[float] = None
    team_bars: Optional[float] = None
    team_beam: Optional[float] = None
    team_floor: Optional[float] = None
    team_all_around: Optional[float] = None
    
    # Players
    players: list[PlayerStats] = Field(default_factory=list)
    
    # Sport-specific player lists
    goalies: list[GoalieStats] = Field(default_factory=list)  # Hockey
    pitchers: list[PitcherStats] = Field(default_factory=list)  # Baseball


# =============================================================================
# GAME/MATCH/MEET MODEL
# =============================================================================

class WrestlingMatch(BaseModel):
    """Individual wrestling match within a dual meet."""
    weight_class: str
    
    # Winner info
    winner_name: str
    winner_school: str
    
    # Loser info
    loser_name: str
    loser_school: str
    
    # Result
    win_type: str  # "pin", "decision", "major_decision", "tech_fall", "forfeit", "dq"
    score: Optional[str] = None  # e.g., "8-3" for decision
    time: Optional[str] = None  # e.g., "3:45" for pin time
    
    # Points
    winner_team_points: float  # 6 for pin, 3 for decision, etc.


class GymnasticsEvent(BaseModel):
    """Individual gymnastics event results."""
    event_name: str  # "vault", "bars", "beam", "floor", "all_around"
    results: list[PlayerStats] = Field(default_factory=list)


class SportsGame(BaseModel):
    """
    Universal game/match/meet model.
    
    Works for team sports (basketball, hockey) and individual sports
    (wrestling, gymnastics) with appropriate fields for each.
    """
    # Sport identification
    sport: SportType
    gender: Optional[Gender] = None
    level: Optional[Level] = None
    
    # Game info
    game_date: Optional[date] = None
    venue: Optional[str] = None
    attendance: Optional[int] = None
    
    # Teams (for team sports)
    home_team: Optional[TeamStats] = None
    away_team: Optional[TeamStats] = None
    
    # For sports where home/away doesn't apply or is ambiguous
    team_1: Optional[TeamStats] = None
    team_2: Optional[TeamStats] = None
    
    # Result
    result: Optional[GameResult] = None
    is_overtime: bool = False
    is_shootout: bool = False
    
    # Wrestling specific (dual meet)
    wrestling_matches: list[WrestlingMatch] = Field(default_factory=list)
    
    # Gymnastics specific
    gymnastics_events: list[GymnasticsEvent] = Field(default_factory=list)
    
    # Hockey specific
    three_stars: list[str] = Field(default_factory=list)  # ["1. Player Name", ...]
    
    # Scoring summary (hockey, soccer, etc.)
    scoring_plays: list[str] = Field(default_factory=list)
    
    # Penalties (hockey)
    penalties: list[str] = Field(default_factory=list)
    
    # Raw/extra data that didn't fit structured fields
    extra_data: dict[str, Any] = Field(default_factory=dict)
    
    # Validation warnings
    validation_warnings: list[str] = Field(default_factory=list)
    
    @model_validator(mode='after')
    def validate_teams(self):
        """Ensure we have team data."""
        has_home_away = self.home_team is not None or self.away_team is not None
        has_team_12 = self.team_1 is not None or self.team_2 is not None
        
        if not has_home_away and not has_team_12:
            # For individual sports like gymnastics, this might be okay
            if self.sport not in [SportType.GYMNASTICS, SportType.WRESTLING, SportType.GOLF, SportType.TENNIS]:
                self.validation_warnings.append("No team data found")
        
        return self
    
    @computed_field
    @property
    def final_score_string(self) -> str:
        """Format: 'Away 72 - Home 68' or 'Team1 vs Team2'."""
        if self.away_team and self.home_team:
            return f"{self.away_team.name} {self.away_team.final_score} - {self.home_team.name} {self.home_team.final_score}"
        if self.team_1 and self.team_2:
            return f"{self.team_1.name} {self.team_1.final_score} - {self.team_2.name} {self.team_2.final_score}"
        return "Score not available"


# =============================================================================
# MULTI-GAME MODELS (for tournaments, meets with multiple matches)
# =============================================================================

class WrestlingMeet(BaseModel):
    """Wrestling dual meet or tournament."""
    meet_date: Optional[date] = None
    venue: Optional[str] = None
    meet_name: Optional[str] = None
    
    # Team scores (for dual meet)
    team_1_name: Optional[str] = None
    team_1_score: Optional[float] = None
    team_2_name: Optional[str] = None
    team_2_score: Optional[float] = None
    
    # Individual matches
    matches: list[WrestlingMatch] = Field(default_factory=list)
    
    # For tournaments with multiple teams
    team_standings: list[dict[str, Any]] = Field(default_factory=list)


class GymnasticsMeet(BaseModel):
    """Gymnastics meet results."""
    meet_date: Optional[date] = None
    venue: Optional[str] = None
    meet_name: Optional[str] = None
    
    # Team scores
    teams: list[TeamStats] = Field(default_factory=list)
    
    # Individual event results
    events: list[GymnasticsEvent] = Field(default_factory=list)
    
    # All-around results
    all_around: list[PlayerStats] = Field(default_factory=list)
