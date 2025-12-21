# QUADD Universal Document Transformer - PROJECT CHARTER

## ⚠️ READ THIS FIRST - EVERY SESSION ⚠️

### Core Mission

Build a UNIVERSAL system where users:
1. Upload a document (PDF or paste text)
2. Provide an example of desired output
3. System LEARNS the transformation rules
4. Apply those rules to new documents of same type

**The system learns from examples. It does not contain document-specific logic.**

---

## Non-Negotiables

- ❌ NO sport-specific code (no basketball logic, no hockey logic, no wrestling logic)
- ❌ NO hardcoded column names or formats (no "OREB", "DREB", "FG" in code)
- ❌ NO document-type-specific parsers
- ✅ The system LEARNS from examples, not from programmer knowledge
- ✅ If a new document type requires code changes, WE'RE DOING IT WRONG

---

## Decision Filter

**Before ANY code change, ask:**

| Question | If Yes | If No |
|----------|--------|-------|
| Does this make the LEARNING system smarter? | ✅ Proceed | ⚠️ Reconsider |
| Does this add document/sport-specific logic? | 🛑 STOP | ✅ Proceed |
| Would this work for a document type we've never seen? | ✅ Proceed | 🛑 STOP |
| Does this require knowing what sport/document this is? | 🛑 STOP | ✅ Proceed |

---

## Success Criteria

The system is successful when:

1. User uploads a document type we've NEVER seen before
2. User provides ONE example of desired output
3. System learns the transformation rules automatically
4. System transforms future documents of that type correctly
5. **ZERO code changes required**

---

## What We're NOT Building

- ❌ Basketball extractor
- ❌ Hockey formatter  
- ❌ Wrestling parser
- ❌ Honor roll processor
- ❌ Legal notice handler
- ❌ Any sport/document-specific code

---

## What We ARE Building

- ✅ Universal PDF/text → structured data extractor
- ✅ Example-based transformation rule learner
- ✅ Learned rule applier
- ✅ Template-based formatter
- ✅ Generic table extraction engine
- ✅ Generic text pattern recognition

---

## The Learning Flow

```
LEARNING PHASE (once per document type):
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Source Doc     │ +   │  Example Output │ →   │  Learned Rules  │
│  (PDF/text)     │     │  (what user     │     │  (stored in DB) │
│                 │     │   wants)        │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘

PROCESSING PHASE (every new document):
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  New Document   │ +   │  Learned Rules  │ →   │  Formatted      │
│  (same type)    │     │  (from DB)      │     │  Output         │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

---

## How to Use This Charter

### At Session Start
Say: "Read PROJECT_CHARTER.md first. All decisions must align with it."

### During Development
Ask: "Does this align with the PROJECT_CHARTER?"

### When Going Off Track
Say: "Stop. Check PROJECT_CHARTER.md. Is this document-specific code?"

### For Claude Code
Instruct: "Before making any code changes, verify the change aligns with PROJECT_CHARTER.md Core Mission and passes the Decision Filter."

---

## Red Flags - Stop and Reassess If:

- 🚩 Adding a column name like "OREB" or "FG" to code
- 🚩 Adding sport detection logic
- 🚩 Creating a sport-specific file or function
- 🚩 Fixing a "basketball bug" or "hockey bug"
- 🚩 Hardcoding any format patterns
- 🚩 The fix only helps one document type

---

## Green Flags - Good Direction:

- ✅ Improving how the system learns from examples
- ✅ Making table extraction more generic
- ✅ Improving pattern recognition across ANY document
- ✅ Better example-to-rule synthesis
- ✅ More robust PDF text extraction
- ✅ User can teach system new formats without code changes

---

## Current Status

| Component | Status | Aligned with Charter? |
|-----------|--------|----------------------|
| Document IR Builder | ✅ Built | ✅ Yes - generic |
| Table Extraction | ⚠️ Partial | ⚠️ Needs review |
| Rule Synthesis | ⚠️ Partial | ⚠️ Needs review |
| Learning from Examples | ❓ Unknown | 🔍 Needs assessment |
| Rule Application | ⚠️ Partial | ⚠️ Needs review |

---

## Next Step

**Assess:** How much of the LEARNING system actually works?

Can a user today:
1. Upload a new document type + example output
2. Have the system learn automatically
3. Process new documents without code changes

If NO → That's what we build next.