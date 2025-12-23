# Tournament Results Feature - Implementation Summary

## Overview

Added a new "Tournament" tab to the quadd-extract app for extracting wrestling tournament box scores filtered by team name. This feature allows users to upload tournament bracket images/PDFs and get results for only their wrestlers.

## Features

### Frontend (frontend/index.html)

#### New Tournament Tab
- **Location**: Between "Use Template" and "Manage" tabs
- **Components**:
  1. **File Upload Section**
     - Supports multiple files (PDF or images)
     - Shows file count when multiple files selected
     - Visual feedback with "has-file" state

  2. **Team Filter Input**
     - Textarea for team names (one per line)
     - Placeholder with examples (Windom-Mountain Lake, Albert Lea, etc.)
     - Helper text explaining partial matching

  3. **Extract Button**
     - Label: "🏆 Extract Tournament Results"
     - Loading state with spinner during extraction
     - Disabled during processing

#### JavaScript Functionality
- **File Upload Handler** (lines 1232-1250)
  - Handles multiple file selection
  - Shows "Selected: X files" when multiple files uploaded
  - Updates UI with visual feedback

- **Tournament Button Handler** (lines 1487-1571)
  - Validates files and team names
  - Parses team names (one per line)
  - Sends FormData with files and teams to backend
  - Handles success/error states
  - **Clears form after successful extraction** (lines 1555-1558)
  - Supports multiple extractions without page refresh

### Backend (src/api/main.py)

#### New Endpoint: POST /api/extract/tournament (lines 864-1046)

**Parameters:**
- `files`: List[UploadFile] - Bracket images/PDFs
- `teams`: str - JSON array of team names
- `current_user`: dict - Requires authentication

**Process:**
1. Validates input (files and team names)
2. Parses team names from JSON
3. Creates specialized extraction prompt with:
   - Team filtering instructions
   - Fuzzy matching rules
   - Output format specification
4. Processes each file using VisionExtractor
5. If multiple files: Consolidates and deduplicates results
6. Returns formatted box scores

**Extraction Prompt Features:**
- **Fuzzy Team Matching**:
  - "Albert Lea" matches "Albert Lea Area" ✓
  - "WML" matches "Windom-Mountain Lake" ✓
  - "Martin County" matches "Martin County Red Bulls" ✓

- **Output Format**:
  ```
  TEAM NAME (all caps)
  Weight: Wrestler Name (Team Abbr) match1; match2; ... Placement
  ```

- **Match Result Formats**:
  - Decision: "dec. Opponent (Team) 5-3"
  - Pin: "pin Opponent (Team) 2:45"
  - Technical Fall: "TF Opponent (Team) 18-3"
  - Major Decision: "maj. dec. Opponent (Team) 12-4"

**Multi-File Handling:**
- Processes each bracket image separately
- Consolidates results using a second Claude API call
- Removes duplicates (same wrestler, same weight)
- Sorts by team name, then weight class

**Response:**
```json
{
  "success": true,
  "results": "formatted box scores text",
  "teams": ["Team1", "Team2"],
  "files_processed": 3,
  "tokens_used": 12500
}
```

## Example Usage

### User Flow:
1. User clicks "Tournament" tab
2. Uploads bracket images (e.g., 152lb.jpg, 160lb.jpg, 170lb.jpg)
3. Enters team names:
   ```
   Windom-Mountain Lake
   Albert Lea
   ```
4. Clicks "Extract Tournament Results"
5. Waits 30-60 seconds for processing
6. Receives formatted output:
   ```
   WINDOM-MOUNTAIN LAKE
   152: Kameron Koerner (WML) TF Blake Stancek (Hutch) 19-4; Koerner pin Lucas Kuball (FMCC) 4:32; ... Third place

   ALBERT LEA AREA
   145: Mike Johnson (ALA) bye; Johnson pin Tom Anderson (Marshall) 3:21; ... Second place
   ```
7. Form automatically clears, ready for next extraction

## Technical Details

### Dependencies
- Uses existing VisionExtractor for image/PDF analysis
- Requires authentication (uses `get_current_user` dependency)
- Uses Claude Sonnet 4 model for extraction and consolidation

### Error Handling
- Validates file upload (at least 1 file required)
- Validates team names (at least 1 team required)
- Handles JSON parsing errors
- Catches API authentication errors
- Handles API connection errors
- Provides clear error messages to user

### Token Usage Tracking
- Tracks tokens used for each file extraction
- Tracks tokens used for consolidation (if multiple files)
- Returns total token count in response
- Logs token usage for monitoring

## Files Modified

1. **frontend/index.html**
   - Added Tournament tab HTML (lines 826-852)
   - Added tournament file upload handler (lines 1232-1250)
   - Added tournament button click handler (lines 1487-1571)

2. **src/api/main.py**
   - Added imports: `List` from typing, `json` module (lines 15-16)
   - Added `/api/extract/tournament` endpoint (lines 864-1046)

## Benefits

✅ **Targeted Extraction**: Only shows results for specified teams
✅ **Fuzzy Matching**: Handles team name variations and abbreviations
✅ **Multi-File Support**: Processes multiple weight classes at once
✅ **Deduplication**: Removes duplicate results across files
✅ **Clean UI**: Form clears after each extraction
✅ **No Refresh Needed**: Can run multiple extractions in sequence
✅ **Error Handling**: Clear feedback for validation and processing errors
✅ **Token Tracking**: Monitors API usage

## Testing Recommendations

1. **Single File Test**:
   - Upload one bracket image
   - Enter one team name
   - Verify output format

2. **Multi-File Test**:
   - Upload 3-4 bracket images
   - Enter 2-3 team names
   - Verify consolidation and deduplication

3. **Fuzzy Matching Test**:
   - Enter abbreviated team name (e.g., "WML")
   - Verify it matches full name (e.g., "Windom-Mountain Lake")

4. **Multiple Extraction Test**:
   - Run one extraction
   - Verify form clears
   - Run another extraction immediately
   - Verify no page refresh needed

5. **Error Handling Test**:
   - Try submitting without files
   - Try submitting without team names
   - Verify error messages display correctly

## Future Enhancements

- Support for other sports (basketball, hockey tournaments)
- CSV/Excel export of results
- Save tournament results to database
- Historical tournament comparison
- Team performance analytics
