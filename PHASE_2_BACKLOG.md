# Phase 2 Backlog

## Priority 1: Critical Fixes (Blocking Production Use)

### P1.1: Fix Row Extraction Logic
**Status:** In Progress
**Effort:** 2-3 days
**Blocking:** End-to-end extraction accuracy

**Problem:**
Currently extracting all column values into a single player object:
```json
{
  "players": [
    {
      "name": ["#1", "#2", "#3", ...],  // Should be separate rows
      "points": [0, 0, 0, ...]
    }
  ]
}
```

**Expected:**
```json
{
  "players": [
    {"name": "#1 Job Ogeka", "points": 20, "fouls": 2},
    {"name": "#2 Jackson Joyce", "points": 15, "fouls": 3},
    ...
  ]
}
```

**Root Cause:**
- `_extract_from_region()` in executor.py:251-286 treats regions as single columns
- `_group_blocks_by_row()` exists (line 312) but isn't being used properly
- Need to restructure column extraction to iterate rows, not columns

**Solution Approach:**
1. Update region extraction to use `_group_blocks_by_row()`
2. For `region.{name}.column[N]` sources:
   - Group region blocks into rows
   - Extract column N from each row
   - Return list of values (one per row)
3. Test with `[]` notation in field_path

**Files to Modify:**
- `src/processors/executor.py:251-286` (_extract_from_region)
- May need to update `_set_nested_field` logic for array handling

**Test Case:**
- Input: WHS player table with 12 rows
- Expected: 12 player objects with separate name/points/fouls
- Verify calculations sum correctly

---

### P1.2: Confidence Scoring System
**Status:** Not Started
**Effort:** 2 days
**Blocking:** Production confidence thresholds

**Requirements:**
- Processor-level confidence (how well anchors matched)
- Extraction-level confidence (data completeness)
- Field-level confidence (OCR quality per field)

**Proposed Scoring:**
```python
@dataclass
class ExtractionConfidence:
    overall: float  # 0-100
    anchor_match_quality: float  # How many anchors found, location quality
    data_completeness: float  # % of expected fields populated
    validation_pass_rate: float  # % of validations passed
    ocr_confidence: float  # Average OCR confidence from blocks
    field_scores: Dict[str, float]  # Per-field confidence
```

**Implementation:**
1. Track anchor match quality in `_find_anchors()`
   - Required vs optional anchors found
   - Location hint success rate
2. Calculate data completeness in `execute()`
   - Count non-null fields vs expected
3. Aggregate OCR confidence from TextBlocks
4. Return confidence object alongside extracted data

**Thresholds:**
- 90%+: High confidence, safe for production
- 70-90%: Medium confidence, flag for review
- <70%: Low confidence, manual review required

---

## Priority 2: Data Quality (User-Facing Improvements)

### P2.1: Name Normalization
**Status:** Not Started
**Effort:** 1 day

**Problems:**
- Names extracted as "JOHN SMITH" (all caps)
- Jersey numbers included: "#12 Kevin Bleess"
- Inconsistent spacing

**Requirements:**
- Title case: "John Smith"
- Strip jersey numbers: "Kevin Bleess" (no "#12")
- Consistent spacing (single space between words)

**Implementation:**
```python
# Add transform to executor.py
def _apply_transform(self, value: Any, transform: Optional[str]) -> Any:
    ...
    elif transform == "normalize_name":
        # Remove jersey numbers: #12, (12), etc.
        name = re.sub(r'#?\d+\s*', '', str(value))
        # Title case
        name = name.title()
        # Clean spacing
        name = ' '.join(name.split())
        return name
```

**Update Synthesis Prompt:**
Guide LLM to use `"transform": "normalize_name"` for player name fields.

---

### P2.2: Team Name Mapping Configuration
**Status:** Not Started
**Effort:** 1-2 days

**Problem:**
- OCR extracts "WHS" but user wants "Windom High School"
- Team names vary: "Worthington", "WOR", "Worthington HS"

**Solution:**
Add configurable team name mappings:

```json
{
  "team_mappings": {
    "WHS": "Windom High School",
    "Windom": "Windom High School",
    "WOR": "Worthington High School",
    "Worthington": "Worthington High School",
    "Edgerton": "Edgerton High School"
  }
}
```

**Implementation:**
1. Add `team_mappings` field to Processor model
2. Apply mapping in executor during extraction
3. Add UI/API endpoint for managing mappings
4. Store mappings in database per processor

**API:**
```python
POST /api/processors/{id}/mappings
{
  "WHS": "Windom High School"
}
```

---

### P2.3: Enhanced Validation Rules
**Status:** Partial (basic validations exist)
**Effort:** 1-2 days

**Current State:**
- Basic schema validations (team names present, scores exist)
- Math validations (period scores sum to final)

**Enhancements Needed:**

**1. Sport-Specific Validations:**
```python
# Basketball validations
- Player count: 5-15 players per team
- Score range: 0-200 per team (detect unrealistic scores)
- Stat ranges: Fouls 0-6, Points 0-50 per player

# Hockey validations
- Player count: 6-25 players per team
- Score range: 0-15 per team
- Period count: 3 periods
```

**2. Cross-Field Validations:**
```python
- Total fouls >= sum of player fouls (allow for team fouls)
- Total points == sum of player points
- Period scores sum == final score
- Player minutes sum <= game minutes * 5 (basketball)
```

**3. OCR Quality Validations:**
```python
- Flag fields with low OCR confidence (<70%)
- Detect garbled text (non-ASCII characters)
- Check for missing critical fields
```

**Implementation:**
- Add `make_advanced_validations()` functions
- Category system: "critical", "warning", "info"
- Return detailed validation report with field locations

---

## Priority 3: Robustness (Handle Edge Cases)

### P3.1: Multi-Pass Extraction with Voting
**Status:** Not Started
**Effort:** 3-4 days
**Value:** Significantly improved accuracy

**Concept:**
Run extraction multiple times with different parameter variations, then vote on consensus results.

**Variations to Try:**
1. **DPI variations:** 200, 300, 400 DPI
2. **Location hint relaxation:** Try ±10% Y-axis tolerance
3. **Pattern matching:** Try exact vs contains vs regex
4. **Column detection:** Try different Y-tolerance for row grouping (0.01, 0.015, 0.02)

**Voting Algorithm:**
```python
def multi_pass_extract(ir: DocumentIR, processor: Processor) -> ExtractionResult:
    results = []

    # Pass 1: Standard extraction
    results.append(executor.execute(ir, processor))

    # Pass 2: Relaxed row tolerance
    executor.row_tolerance = 0.02
    results.append(executor.execute(ir, processor))

    # Pass 3: Strict row tolerance
    executor.row_tolerance = 0.01
    results.append(executor.execute(ir, processor))

    # Vote on each field
    final = vote_on_fields(results)
    return final
```

**Voting Logic:**
- Numeric fields: Use median value
- String fields: Use most common value
- Arrays: Use result with most items
- Confidence: Average of all passes

**Files:**
- Create `src/processors/multi_pass.py`
- Integrate with executor

---

### P3.2: Adaptive Anchor Matching
**Status:** Not Started
**Effort:** 2-3 days

**Problem:**
Anchors sometimes fail on documents with:
- Slightly different layouts
- Missing sections
- Extra headers

**Enhancements:**

**1. Fuzzy Location Hints:**
```python
"location_hint": "top_quarter:0.1"  # Top 25% ± 10% tolerance
"location_hint": "near:other_anchor:0.05"  # Within 5% of another anchor
```

**2. Optional Anchor Fallbacks:**
```python
{
  "name": "player_table",
  "patterns": ["Name", "Player", "#"],  # Try in order
  "required": false,
  "fallback_anchor": "pts_column"  # Use this if not found
}
```

**3. Anchor Confidence Scoring:**
```python
- Pattern match quality (exact vs partial)
- Location match quality (expected vs actual position)
- Context match (nearby expected patterns)
```

---

### P3.3: Layout Hash Improvements
**Status:** Basic implementation exists
**Effort:** 2 days

**Current State:**
- Simple MD5 hash of block positions
- Used for processor routing

**Enhancements:**

**1. Fuzzy Layout Matching:**
```python
# Don't require exact match, allow similarity threshold
layout_similarity = compute_layout_similarity(doc1, doc2)
if layout_similarity > 0.85:
    use_same_processor()
```

**2. Layout Features:**
Instead of raw hash, extract features:
```python
layout_features = {
    "block_count": 386,
    "page_count": 2,
    "has_tables": true,
    "table_positions": [(0.05, 0.1), (0.05, 0.4)],
    "header_patterns": ["Box Score", "Player Stats"],
    "page_density": [0.65, 0.80]  # Blocks per page
}
```

**3. Processor Recommendation:**
```python
def recommend_processor(doc_ir: DocumentIR) -> List[Tuple[Processor, float]]:
    """Return ranked list of processors with similarity scores."""
    features = extract_layout_features(doc_ir)
    scores = []
    for processor in all_processors:
        similarity = compare_features(features, processor.layout_features)
        scores.append((processor, similarity))
    return sorted(scores, key=lambda x: x[1], reverse=True)
```

---

## Priority 4: Performance & Scale

### P4.1: Caching & Performance
**Status:** Not Started
**Effort:** 1-2 days

**Optimizations:**

**1. DocumentIR Caching:**
```python
# Cache built IRs to avoid re-processing same PDFs
cache_key = hash(pdf_bytes)
ir = redis.get(f"ir:{cache_key}")
if not ir:
    ir = builder.build(pdf_bytes)
    redis.set(f"ir:{cache_key}", ir.to_json(), ex=3600)
```

**2. Processor Caching:**
```python
# Cache loaded processors in memory
@lru_cache(maxsize=100)
def get_processor(processor_id: str) -> Processor:
    ...
```

**3. Batch Processing:**
```python
# Process multiple documents concurrently
async def batch_extract(files: List[bytes], processor_id: str):
    tasks = [extract_async(f, processor_id) for f in files]
    return await asyncio.gather(*tasks)
```

**4. Query Optimization:**
```sql
-- Add indexes to database
CREATE INDEX idx_processors_doc_type ON processors(document_type);
CREATE INDEX idx_extractions_processor ON extractions(processor_id);
CREATE INDEX idx_extractions_created ON extractions(created_at);
```

---

### P4.2: Incremental Learning
**Status:** Not Started
**Effort:** 3-4 days

**Concept:**
Allow processors to improve over time based on user corrections.

**Flow:**
1. User extracts document → processor outputs data
2. User corrects errors in UI
3. System learns from corrections:
   - Update anchor patterns if anchors failed
   - Adjust location hints if positions were wrong
   - Add new extraction ops if fields were missed
4. Re-train processor, increment version
5. Test on validation set

**Implementation:**
```python
async def learn_from_correction(
    processor_id: str,
    document_ir: DocumentIR,
    original_output: dict,
    corrected_output: dict
):
    # Compute diff
    diff = compute_diff(original_output, corrected_output)

    # Identify what went wrong
    issues = analyze_diff(diff, document_ir)

    # Update processor
    updated = apply_fixes(processor, issues)

    # Validate on examples
    if validate_processor(updated):
        await db.update_processor(processor_id, updated)
```

**Database:**
```sql
CREATE TABLE corrections (
    id TEXT PRIMARY KEY,
    processor_id TEXT,
    document_ir_json TEXT,
    original_output TEXT,
    corrected_output TEXT,
    applied BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP
);
```

---

## Priority 5: Developer Experience

### P5.1: Processor Debugging Tools
**Status:** Not Started
**Effort:** 2-3 days

**Tools to Build:**

**1. Visual Debugger:**
- Render PDF with bounding boxes overlaid
- Color-code anchors, regions, extracted fields
- Show anchor matches and mismatches

**2. Extraction Diff Tool:**
```python
# Compare expected vs actual output
def diff_extractions(expected: dict, actual: dict) -> DiffReport:
    - Show missing fields
    - Show incorrect values
    - Highlight validation failures
    - Suggest fixes
```

**3. Processor Test Suite:**
```python
# Run processor against test set
def test_processor(processor_id: str) -> TestReport:
    test_docs = get_test_documents(processor.document_type)
    results = []
    for doc in test_docs:
        result = extract(doc, processor)
        results.append(validate(result, doc.expected_output))
    return summarize_results(results)
```

**4. Synthesis Playground:**
- Web UI to test synthesis prompts
- Show LLM response in real-time
- Edit prompts and re-synthesize
- Compare processor versions

---

### P5.2: API Documentation & Examples
**Status:** Partial (basic endpoints exist)
**Effort:** 1-2 days

**Deliverables:**

**1. OpenAPI Spec:**
```yaml
/api/processors/learn:
  post:
    summary: Learn a new processor from example
    requestBody:
      content:
        multipart/form-data:
          schema:
            properties:
              name: string
              document_type: string
              example_file: binary
              desired_output: string
```

**2. SDK/Client Library:**
```python
# Python client
from quadd_extract import QuaddClient

client = QuaddClient(api_key="...")

# Learn processor
processor = await client.learn_processor(
    name="my_basketball",
    document_type="basketball",
    example_file=open("game.pdf", "rb"),
    desired_output=open("output.txt", "r").read()
)

# Extract
result = await client.extract(
    file=open("new_game.pdf", "rb"),
    processor_id=processor.id
)
```

**3. Example Scripts:**
- `examples/learn_and_extract.py`
- `examples/batch_processing.py`
- `examples/custom_validations.py`

**4. Integration Tests:**
```python
# tests/integration/test_full_workflow.py
def test_learn_extract_validate():
    # Learn from example
    processor = synthesizer.synthesize(...)

    # Extract from new doc
    result = executor.execute(...)

    # Validate results
    assert result['team1']['total_fouls'] == 9
```

---

## Priority 6: Production Readiness

### P6.1: Error Handling & Logging
**Status:** Basic logging exists
**Effort:** 1-2 days

**Enhancements:**

**1. Structured Logging:**
```python
logger.info("extraction_started", extra={
    "processor_id": processor.id,
    "document": filename,
    "anchors_found": len(anchor_positions)
})
```

**2. Error Categories:**
- User errors (bad input, missing fields)
- System errors (OCR failure, database error)
- Data errors (validation failure, anchor mismatch)

**3. Retry Logic:**
```python
@retry(tries=3, delay=1, backoff=2)
def extract_with_retry(ir, processor):
    return executor.execute(ir, processor)
```

**4. Monitoring:**
- Track extraction success rate
- Track average processing time
- Alert on degraded performance

---

### P6.2: Security & Validation
**Status:** Not Started
**Effort:** 2-3 days

**Requirements:**

**1. Input Validation:**
- PDF size limits (max 50MB)
- File type validation (PDF only)
- Malicious PDF detection

**2. Rate Limiting:**
```python
@limiter.limit("10/minute")
async def extract_endpoint():
    ...
```

**3. API Authentication:**
```python
# Add API key auth
@require_auth
async def learn_processor():
    ...
```

**4. Data Privacy:**
- Option to not store uploaded PDFs
- Automatic cleanup of old extractions
- GDPR compliance (data deletion)

---

### P6.3: Deployment & CI/CD
**Status:** Not Started
**Effort:** 2-3 days

**Deliverables:**

**1. Docker Setup:**
```dockerfile
FROM python:3.11
RUN apt-get update && apt-get install -y tesseract-ocr
COPY . /app
RUN pip install -r requirements.txt
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0"]
```

**2. CI Pipeline:**
```yaml
# .github/workflows/test.yml
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run tests
        run: pytest tests/
      - name: Run integration tests
        run: pytest tests/integration/
```

**3. Deployment Scripts:**
```bash
# deploy.sh
docker build -t quadd-extract:$VERSION .
docker push quadd-extract:$VERSION
kubectl apply -f k8s/deployment.yaml
```

---

## Estimated Timeline

| Priority | Items | Total Effort | Dependencies |
|----------|-------|--------------|--------------|
| P1 | Critical Fixes | 4-5 days | None (start immediately) |
| P2 | Data Quality | 3-5 days | None |
| P3 | Robustness | 7-9 days | P1 complete |
| P4 | Performance | 4-6 days | P1, P3 |
| P5 | Developer Experience | 5-7 days | P1 |
| P6 | Production | 5-8 days | All above |

**Total Estimated Effort:** 28-40 days (5-8 weeks with testing/iteration)

---

## Success Metrics

### Phase 2 Exit Criteria:

1. **Accuracy:**
   - 95%+ extraction accuracy on training documents
   - 85%+ accuracy on new documents (same format)
   - <5% manual corrections needed

2. **Performance:**
   - <5 seconds per document extraction
   - <30 seconds for synthesis
   - 100+ documents/hour throughput

3. **Robustness:**
   - Handle 90%+ of documents without errors
   - Graceful degradation on failures
   - Clear error messages for manual intervention

4. **Production Readiness:**
   - Full API documentation
   - Deployment automation
   - Monitoring and alerting
   - 99.9% uptime target

---

## Notes

- **P1 is the blocker:** Row extraction must work before other features
- **Multi-pass extraction (P3.1)** could dramatically improve accuracy - high value
- **Incremental learning (P4.2)** enables continuous improvement - consider prioritizing
- **Visual debugger (P5.1)** will make development much faster - front-load this

## Next Steps

1. Fix row extraction (P1.1) - start immediately
2. Add confidence scoring (P1.2) - needed for production
3. Build visual debugger (P5.1) - accelerates all other work
4. Implement multi-pass extraction (P3.1) - big accuracy win
