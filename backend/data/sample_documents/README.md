# Sample Documents (Indian Refinery Context)

Three realistic documents for testing the `/api/ingest` pipeline. They are plain
text so they can be saved as PDF with any tool (print-to-PDF, LibreOffice,
Word). The ingestion parser reads PDFs, so convert them before uploading.

## Files

| File | Document type | Plant / company | Key entities to detect |
|------|---------------|-----------------|------------------------|
| `01_maintenance_work_order_P-101A.txt` | Maintenance work order | BPCL Mathura Refinery, CDU-1 | Equipment **P-101A** (pump), personnel (Rakesh Sharma, Suresh Patel…), OISD-154, API 610, incident IR-2024-0156, dates |
| `02_safety_procedure_hot_work_OISD.txt` | Safety procedure / SOP | IOCL Gujarat Refinery | OISD-117/118/105, Petroleum Rules 2002, Factories Act 1948, PESO, NFPA 51B, personnel, E-305 & V-203 |
| `03_inspection_report_V-203.txt` | Inspection / NDT report | Reliance Jamnagar Refinery | Equipment **V-203** (vessel), NDT results, ASME/API codes, OISD-164, SMPV-U, PESO, personnel, dates |

## How to convert to PDF (pick any one)

**Option A — LibreOffice (CLI), if installed:**
```bash
soffice --headless --convert-to pdf --outdir . 01_maintenance_work_order_P-101A.txt
```

**Option B — Word / any editor:** open the `.txt`, File → Print → "Save as PDF".

**Option C — browser:** open the `.txt` in a browser, Ctrl+P → "Save as PDF".

> These 3 documents intentionally share overlapping entities (V-203 appears in
> both the SOP and the inspection report; OISD standards appear in all three).
> That overlap is what the knowledge graph should link together — ingest all
> three and then verify the graph shows cross-document relationships.
