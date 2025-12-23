# Entity Filtering Perspective Fix - Generic Improvement

## Problem Identified

Entity filtering was following the **wrong perspective** when filtered entities had negative outcomes.

### Example Scenario (Generic Pattern)

**Tournament brackets (could be any sport):**
- User filters for entity: "Windom-Mountain Lake" (WML)
- System finds person from WML: "Hyatt Hansen (WML)"
- But Hansen LOST his match to "Judah Perrault"
- **Bug**: System outputs Perrault's path (the winner) instead of Hansen's path
- **Expected**: Output should show Hansen's path even though he lost

### Same Issue Occurs In:

**Company Reports:**
- Filter for: "Sales Department"
- Sales underperformed compared to Marketing
- **Bug**: System shows Marketing's results instead
- **Expected**: Show Sales Department results regardless

**School Rankings:**
- Filter for: "Lincoln School"
- Lincoln ranked low, beaten by Jefferson School
- **Bug**: System shows Jefferson's achievements instead
- **Expected**: Show Lincoln's results regardless of rank

**Conference Schedules:**
- Filter for: "AI Track"
- AI Track had lower attendance than Web Track
- **Bug**: System switches to Web Track sessions
- **Expected**: Show AI Track sessions regardless

---

## Charter Compliance ✅

This is a **GENERIC entity filtering improvement** that aligns with the PROJECT CHARTER:

| Charter Rule | Status | Alignment |
|-------------|--------|-----------|
| ✅ Makes LEARNING system smarter | ✅ YES | Better entity filtering across all document types |
| ❌ NO sport-specific logic | ✅ PASS | Examples include sports, business, schools - generic |
| ✅ Works for unseen doc types | ✅ PASS | Applies to ANY entity filtering scenario |
| ❌ Requires knowing what doc is | ✅ PASS | Generic perspective rule, not doc-specific |

**Green Flags:**
- ✅ Improving pattern recognition across ANY document
- ✅ Better example-to-rule synthesis
- ✅ User can teach system new formats without code changes

---

## Root Cause Analysis

### What Was Happening:

1. User creates template with filtered example (e.g., shows winners' results)
2. User filters new document for entity X
3. System finds entity X in document
4. Entity X has negative outcome (loses, underperforms, ranks low)
5. **Bug**: System switches to opponent/competitor with better outcome
6. Output shows wrong entity's perspective

### Why This Happened:

The filtering prompt said:
> "Include ONLY entries related to these entities"

But didn't specify **perspective**:
- "Related to" is ambiguous - Hansen vs Perrault are both related
- No guidance on following entities with negative outcomes
- Missing instruction to maintain entity perspective regardless of results

### The Generic Pattern:

This is a fundamental entity filtering issue:
- **Entity filtering** = Show entity X's data
- **Entity perspective** = From entity X's viewpoint
- **Outcome independence** = Regardless of whether X won/lost/succeeded/failed

---

## The Solution

Added **explicit perspective rules** to entity filtering prompts.

### New Instructions (Generic, Not Sport-Specific):

**Critical Perspective Rule:**
```
Output should follow the FILTERED ENTITY'S path/journey/results from THEIR perspective

- Show the entity's results REGARDLESS of outcomes (wins, losses, rankings, performance)
- Do NOT switch to opponents/competitors/other entities just because they had better outcomes
```

**Generic Examples Provided:**
- ✅ Tournament: Filter for Team A → Show Team A's matches (even if they lost)
- ✅ Company report: Filter for Sales Dept → Show Sales Dept metrics (even if underperformed)
- ✅ Rankings: Filter for School A → Show School A's results (even if ranked low)

---

## Files Modified

**src/api/main.py** - `/api/extract/tournament` endpoint

### Multi-File Filter Prompt (lines 970-976):
```python
2. CRITICAL - Perspective Rule: Output should follow the FILTERED ENTITY'S path/journey/results from THEIR perspective
   - If filtering for entity X, show X's results/journey, REGARDLESS of outcomes (wins, losses, rankings, etc.)
   - Do NOT switch to opponents/competitors/other entities just because they had better outcomes
   - Examples:
     * Tournament: Filter for Team A → Show Team A's matches (even if they lost)
     * Company report: Filter for Sales Dept → Show Sales Dept metrics (even if they underperformed)
     * School rankings: Filter for School A → Show School A's results (even if they ranked low)
```

### Single-File Filter Prompt (lines 991-999):
```python
CRITICAL - Perspective Rule:
- Output should follow the FILTERED ENTITY'S path/journey/results from THEIR perspective
- Show the entity's results REGARDLESS of outcomes (wins, losses, rankings, performance, etc.)
- Do NOT switch to opponents/competitors/other entities just because they had better outcomes

Examples of correct filtering:
- Tournament: Filter for "Team A" → Show Team A's matches even if they lost
- Company report: Filter for "Sales Dept" → Show Sales Dept even if they underperformed
- Rankings: Filter for "School A" → Show School A even if they ranked low
```

---

## How It Works Now

### Scenario: Tournament Bracket Filtering

**User filters for:** "Windom-Mountain Lake" (WML)

**Document contains:**
- Hyatt Hansen (WML) - LOST to Judah Perrault (opposing team)
- Kameron Koerner (WML) - WON his matches

**Old Behavior (Bug):**
```
Output:
- Judah Perrault defeated Hyatt Hansen... [follows Perrault's path]
- Kameron Koerner defeated... [follows Koerner's path]
```
Result: Mixed perspectives - opponent's path for losers, own path for winners ❌

**New Behavior (Fixed):**
```
Output:
- Hyatt Hansen (WML) lost to Judah Perrault... [follows Hansen's path even though he lost]
- Kameron Koerner (WML) defeated... [follows Koerner's path]
```
Result: Consistent WML perspective for ALL wrestlers ✅

---

### Scenario: Company Report Filtering

**User filters for:** "Sales Department"

**Document contains:**
- Sales Dept: $500K revenue (underperformed)
- Marketing Dept: $2M revenue (outperformed)

**Old Behavior (Bug):**
```
Output:
Marketing Department achieved $2M... [switches to better performer]
```
Result: Shows wrong department ❌

**New Behavior (Fixed):**
```
Output:
Sales Department achieved $500K... [shows filtered dept even with low numbers]
```
Result: Shows correct department regardless of performance ✅

---

## Generic Document Types This Helps

✅ **Sports Tournaments** - Show filtered team even when they lose
✅ **Company Reports** - Show filtered dept even when they underperform
✅ **School Rankings** - Show filtered school even when they rank low
✅ **Employee Reviews** - Show filtered employee even with poor ratings
✅ **Product Comparisons** - Show filtered product even when it scores lower
✅ **Conference Schedules** - Show filtered track even with lower attendance
✅ **Patient Records** - Show filtered patient even with complications
✅ **ANY entity-based filtering** where entities may have negative outcomes

---

## Key Insight

**Entity filtering is about WHO, not about OUTCOME.**

When user says "filter for entity X":
- They want X's data, X's perspective, X's journey
- They do NOT want "entities similar to X"
- They do NOT want "entities that outperformed X"
- They do NOT want "winners X competed against"

**Outcome independence is critical:**
- Show entity X when X wins ✅
- Show entity X when X loses ✅
- Show entity X when X succeeds ✅
- Show entity X when X fails ✅

---

## Testing Scenarios

### Test 1: Tournament - Entity Lost
- **Filter:** "Team A"
- **Document:** Team A wrestler lost to Team B wrestler
- **Expected:** Show Team A wrestler's path (even though they lost) ✅
- **Old behavior:** Showed Team B wrestler's path ❌

### Test 2: Company Report - Department Underperformed
- **Filter:** "Sales Department"
- **Document:** Sales underperformed vs Marketing
- **Expected:** Show Sales Department metrics ✅
- **Old behavior:** Switched to Marketing Department ❌

### Test 3: School Rankings - School Ranked Low
- **Filter:** "Lincoln School"
- **Document:** Lincoln ranked 15th, Jefferson ranked 1st
- **Expected:** Show Lincoln's ranking and achievements ✅
- **Old behavior:** Showed Jefferson's achievements ❌

### Test 4: Mixed Outcomes
- **Filter:** "Organization X"
- **Document:** Org X won some contests, lost others
- **Expected:** Show ALL of Org X's results (wins AND losses) ✅
- **Old behavior:** Only showed wins, or switched to opponents for losses ❌

---

## Charter Alignment

| Charter Requirement | How This Fix Meets It |
|---------------------|----------------------|
| ❌ NO sport-specific code | ✅ Generic entity filtering - examples span sports, business, schools |
| ❌ NO hardcoded patterns | ✅ Generic perspective rule, not pattern-specific |
| ✅ System learns from examples | ✅ Better at understanding entity filtering from user examples |
| ✅ Works for unseen docs | ✅ Applies to ANY entity filtering scenario |
| ✅ Zero code changes for new types | ✅ Same logic works for tournaments, reports, rankings, etc. |

---

## Impact

### For Users:
- ✅ Filtering now maintains consistent perspective
- ✅ See filtered entity's results regardless of outcomes
- ✅ No more unexpected switches to other entities

### For the System:
- ✅ Better entity filtering across ALL document types
- ✅ Clearer prompt instructions for Claude
- ✅ Handles negative outcomes correctly

### For Pattern Learning:
- ✅ System better understands "filter by entity" pattern
- ✅ Maintains perspective consistency
- ✅ Outcome-independent filtering

---

## Future Enhancements (Charter-Compliant)

Potential improvements that remain generic:

1. **Confidence scoring** - How confident is the system in entity identification?
2. **Relationship mapping** - Understand entity relationships in documents
3. **Multi-perspective output** - Optionally show both entity's perspective and opponent's
4. **Perspective detection** - Auto-detect if template uses entity or opponent perspective

All remain **generic** and **charter-compliant**.

---

## Summary

**Problem:** Entity filtering switched to opponents/competitors when filtered entity had negative outcomes

**Root Cause:** No explicit instruction to maintain entity perspective regardless of results

**Solution:** Added "Perspective Rule" to filtering prompts with generic examples

**Result:** Filtering now maintains entity perspective for wins AND losses

**Charter Status:** ✅ Fully compliant - generic entity filtering improvement
