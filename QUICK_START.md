# Quick Start - Universal Document Learning

## One-Command Learning and Extraction

### Basic Usage

```bash
python learn_and_extract.py --source document.pdf --example "desired output format"
```

This single command will:
1. **Learn** extraction rules from your example
2. **Save** the processor for reuse
3. **Extract** data from the document
4. **Show** the formatted output

### Examples for Different Document Types

#### Basketball Box Score
```bash
python learn_and_extract.py \
  --source windom_vs_marshall.pdf \
  --example "Windom 72, Marshall 68

Leading scorers:
  J. Anderson (Windom): 14 points
  M. Johnson (Marshall): 18 points"
```

#### Honor Roll
```bash
python learn_and_extract.py \
  --source honor_roll_q1.pdf \
  --example "Mountain Lake High School - Honor Roll Q1 2024

Grade 9:
  John Anderson (3.8 GPA)
  Sarah Brown (3.9 GPA)"
```

#### Event Schedule
```bash
python learn_and_extract.py \
  --source community_events.pdf \
  --example "Community Center Events

Monday:
  9:00 AM - Yoga Class (Room A) - $10
  2:00 PM - Art Workshop (Studio) - $15"
```

#### Legal Notice
```bash
python learn_and_extract.py \
  --source court_notices.pdf \
  --example "Case No. 2024-CV-1234
Plaintiff: John Smith
Defendant: Acme Corp
Hearing: Dec 15, 2024"
```

#### Newspaper Article
```bash
python learn_and_extract.py \
  --source newspaper.pdf \
  --example "Town Council Approves New Park

The Windom Town Council voted 5-2 to approve construction of a new park on Main Street.

Council members Sarah Johnson and Mike Anderson voted in favor."
```

## Reusing Learned Processors

Once you've learned from one document, you can apply the same processor to similar documents:

### Step 1: Learn from first document
```bash
python learn_and_extract.py --source game1.pdf --example "..."
# Output shows: Processor ID: abc-123-def
```

### Step 2: List saved processors
```bash
python extract_with_processor.py --list
```

### Step 3: Extract from new documents
```bash
python extract_with_processor.py --source game2.pdf --processor abc-123-def
python extract_with_processor.py --source game3.pdf --processor abc-123-def
```

## What Happens Under the Hood

When you run `learn_and_extract.py`, the system:

### Priority #1: Template Learning
- Analyzes your desired output format
- Generates a Jinja2 template that produces that format
- No hardcoded templates!

### Priority #2: Field Mapping Learning
- Extracts column headers from source document
- Maps them to your output field names
- Example: `"Name"` column → `student_name` field

### Priority #3: Generic Extraction Rules
- Uses generic synthesis prompt (not sport-specific!)
- Generates extraction operations for any document type
- Works for basketball, honor rolls, legal notices, events, etc.

### Priority #4: Dynamic Schema
- Schema is implicit in extraction operations
- No hardcoded Pydantic models
- Works with dict-based data structures

## Tips for Best Results

### 1. Provide a Complete Example
```bash
# Good - shows full structure
--example "Header: Team Scores
Windom: 72
Marshall: 68

Top Scorers:
  Anderson: 14 pts
  Johnson: 18 pts"

# Bad - too minimal
--example "Windom won"
```

### 2. Use Consistent Formatting
Match the spacing, indentation, and structure you want in the output.

### 3. Include Multiple Rows
If your document has tables, show at least 2-3 rows in the example:
```bash
--example "Students:
  John Anderson - Grade 9 - 3.8 GPA
  Sarah Brown - Grade 10 - 3.9 GPA
  Mike Wilson - Grade 9 - 3.7 GPA"
```

### 4. Test with Different Documents
The system learns patterns, so test with 2-3 similar documents to verify it generalizes:
```bash
# Learn from first document
python learn_and_extract.py --source game1.pdf --example "..."

# Test on second document with same processor
python extract_with_processor.py --source game2.pdf --processor <id>
```

## Charter Compliance

This system follows the charter from `transformer.md`:

✅ **Makes LEARNING smarter** - Learns from examples, not code
✅ **Works for unseen document types** - No hardcoded assumptions
✅ **Doesn't require knowing document type** - Generic synthesis

## Troubleshooting

### "Source file not found"
- Check the file path is correct
- Use absolute path or ensure you're in the right directory

### "Learning failed"
- Check your PDF is readable (not encrypted)
- Ensure example output matches document content
- Try with a simpler example first

### "No processors found"
- You need to create one first with `learn_and_extract.py`
- Use `--list` to see saved processors

## Next Steps

1. **Try with your documents** - Test with real PDFs
2. **Refine examples** - Adjust desired output for better results
3. **Build a library** - Create processors for each document type you process regularly
4. **Automate** - Use saved processors in your pipeline

## Architecture

```
PDF → IR Builder → DocumentIR → Synthesizer → Processor
                                               ↓
                                          (saved to DB)
                                               ↓
PDF → IR Builder → DocumentIR → Executor → Extracted Data → Renderer → Output
                                    ↑
                               (loaded from DB)
```

The system is **document-agnostic** and learns extraction patterns from examples!
