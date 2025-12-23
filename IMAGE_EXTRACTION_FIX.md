# Image Extraction Fix - Generic Improvement

## Problem Identified

Users uploading **clear PNG screenshots** (e.g., tournament brackets from usabracketing.com) were getting errors:

```
"I can see this is a wrestling tournament bracket/results document,
but the text appears to be heavily corrupted or poorly scanned..."
```

**Root Cause:** The images were NOT corrupted. The issue was with the pytesseract OCR layer.

---

## Charter Compliance ✅

This is a **GENERIC image extraction improvement** that aligns with the PROJECT CHARTER:

| Charter Rule | Status | How This Fix Aligns |
|-------------|--------|---------------------|
| ✅ Makes LEARNING system smarter | ✅ YES | Better at handling ANY complex image |
| ❌ Document-specific logic | ✅ NO | Works for brackets, forms, charts, ANY complex layout |
| ✅ Works for unseen doc types | ✅ YES | Improves ALL image-based documents |
| ❌ Requires knowing what doc is | ✅ NO | Generic vision improvement |

**Green Flags:**
- ✅ More robust image extraction (not just PDFs)
- ✅ Improving pattern recognition across ANY document
- ✅ User can teach system new formats without code changes

---

## Technical Root Cause

### How Image Processing Works:

1. **User uploads image** (PNG, JPG, etc.)
2. **System converts to base64** for Claude's vision API
3. **System runs pytesseract OCR** to extract text
4. **Both sent to Claude** (images + OCR text)

### The Problem with pytesseract:

Pytesseract is designed for **simple text documents** (letters, invoices, plain text).

For **complex layouts**, pytesseract fails:
- ❌ Tournament brackets (tables, lines, non-linear text)
- ❌ Forms (boxes, checkboxes, structured layouts)
- ❌ Charts and graphs (visual elements)
- ❌ Multi-column layouts
- ❌ Rotated or angled text

### What Claude Received:

```
IMAGES: [Clear, perfect tournament bracket]
OCR TEXT: "jb3k jT urnb45 n@me c0rr  u pt3d t3xt..."
```

**Old Instructions:**
> "Use the OCR TEXT for accurate names, numbers, and values."

**Claude's Response:** "The text appears corrupted" ❌

---

## The Solution

Changed instructions to **prioritize IMAGES over OCR** for complex layouts.

### New Prompt Structure:

**1. Header Instructions (lines 697-701):**
```
For each document, you receive:
1. **IMAGES (PRIMARY SOURCE)** - Complete, accurate visual content
2. **OCR TEXT (SUPPLEMENTARY)** - May be incomplete or corrupted for complex layouts

**IMPORTANT:** For documents with complex layouts (brackets, tables, forms),
prioritize extracting from IMAGES. OCR text from pytesseract often fails on
complex layouts - if it looks corrupted but the image is clear, extract
everything from the image and ignore the OCR text.
```

**2. Example Section (line 707):**
```
## Example Images (primary source - read from these):
```

**3. Example OCR (line 723):**
```
## Example OCR Text (supplementary - may be incomplete):
```

**4. Task Section (line 742):**
```
## New Document Images (primary source - extract from these):
```

**5. New OCR Section (line 755):**
```
## New Document OCR Text (supplementary - may be incomplete):
```

**6. Detailed Instructions (lines 762-772):**
```
**PRIMARY SOURCE: Use the IMAGES** - The images show the complete, accurate content.
**SECONDARY SOURCE: OCR Text** - Use only as supplementary help if needed.

**CRITICAL FOR COMPLEX DOCUMENTS:** If the document has complex layouts
(tables, brackets, forms, charts), the OCR text may be incomplete or corrupted.
In these cases:
- **RELY ON THE IMAGES** - Extract all content directly from what you see
- Ignore garbled or corrupted OCR text
- The images contain the true, complete information

**For simple text documents:** OCR text is reliable and can be used.

**How to decide:** If the OCR text looks corrupted, fragmented, or incomplete
BUT the images are clear and readable, extract everything from the images and
ignore the OCR text.
```

---

## Files Modified

**src/simple_transformer.py** - `_build_vision_ocr_content()` method

**Changes:**
1. **Line 697-701**: Updated header to prioritize images
2. **Line 707**: Changed "for structure/layout" → "primary source - read from these"
3. **Line 723**: Changed "accurate text extraction" → "supplementary - may be incomplete"
4. **Line 742**: Changed "for structure/layout" → "primary source - extract from these"
5. **Line 755**: Changed "accurate text extraction" → "supplementary - may be incomplete"
6. **Lines 762-772**: Added comprehensive instructions on when/how to prioritize images

---

## Generic Document Types This Helps

✅ **Tournament Brackets** - Complex tables, brackets, lines
✅ **Forms** - Boxes, checkboxes, structured fields
✅ **Charts/Graphs** - Visual data representations
✅ **Scorecards** - Complex tables with statistics
✅ **Multi-column layouts** - Newspapers, reports
✅ **Architectural drawings** - Visual with annotations
✅ **Music sheets** - Notes, symbols, non-text content
✅ **Medical forms** - Checkboxes, structured data
✅ **Any complex visual document**

**Still works well for:**
✅ **Simple text documents** - Letters, invoices (OCR helps)
✅ **PDFs with good text** - Reports, contracts (OCR helps)

---

## Testing Scenarios

### Scenario 1: Tournament Bracket (Complex Layout)
- **Input**: Clear PNG screenshot of wrestling bracket
- **Old behavior**: "Text appears corrupted" ❌
- **New behavior**: Extracts directly from image ✅

### Scenario 2: Business Form (Structured Layout)
- **Input**: PDF form with boxes and fields
- **Old behavior**: Fragmented OCR text confuses extraction ❌
- **New behavior**: Reads structure from image ✅

### Scenario 3: Simple Text Document
- **Input**: Plain text invoice PDF
- **Old behavior**: Used OCR successfully ✅
- **New behavior**: Still uses OCR (when it's good) ✅

### Scenario 4: Honor Roll (Table Layout)
- **Input**: Multi-column honor roll table
- **Old behavior**: OCR scrambles columns ❌
- **New behavior**: Reads table structure from image ✅

---

## Impact

### For Users:
- ✅ Clear images now work correctly
- ✅ No more "corrupted text" errors for good images
- ✅ Works for ANY complex layout, not just tournaments

### For the System:
- ✅ Better at handling complex visual documents
- ✅ Leverages Claude's vision capabilities fully
- ✅ OCR still available as supplementary help
- ✅ No document-type-specific logic added

### Charter Alignment:
- ✅ Generic improvement (not sport-specific)
- ✅ Works for ANY document type
- ✅ No code changes needed for new document types
- ✅ User teaches format via examples, not programmer

---

## Why pytesseract Still Included?

Even though pytesseract fails on complex layouts, we keep it because:

1. **Helpful for simple documents** - Plain text PDFs, invoices
2. **Supplementary data** - Can help with names/numbers when layout is simple
3. **Claude decides** - New instructions let Claude ignore it when bad
4. **No harm** - If it's garbage, Claude now knows to ignore it

---

## Key Insight

**Claude's vision API is BETTER than pytesseract OCR for complex layouts.**

The old prompt treated OCR as the "accurate" source and images as supplementary. This was backwards for complex documents.

**New approach:**
- Images = Primary source (always accurate)
- OCR = Supplementary (use when helpful, ignore when corrupted)

---

## Future Enhancements (Charter-Compliant)

Potential improvements that remain generic:

1. **Adaptive OCR skipping** - Detect complex layouts and skip pytesseract entirely
2. **Quality scoring** - Measure OCR text quality, auto-decide priority
3. **User feedback loop** - Learn which document types need image priority
4. **Multiple OCR engines** - Try different engines, use best result

All remain **generic** and **charter-compliant**.

---

## Summary

**Problem:** Clear images failed with "corrupted text" errors due to poor pytesseract OCR

**Root Cause:** Instructions prioritized OCR over images for complex layouts

**Solution:** Updated prompt to prioritize images as primary source, OCR as supplementary

**Result:** Clear images now work correctly for ANY complex layout

**Charter Status:** ✅ Fully compliant - generic image extraction improvement
