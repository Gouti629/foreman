# Foreman — Evaluation Summary

Generated 2026-08-17T23:01:41.040439+00:00 against 20 fixture submissions in `data/submissions/submissions.json`, using live Claude calls.

## Decision accuracy

**15/20 correct (75%)** — predicted decision matches each fixture's `known_label`.

### Confusion matrix (rows = known label, columns = predicted)

| known \ predicted | accept | refer | decline |
|---|---|---|---|
| **accept** | 5 | 0 | 0 |
| **refer** | 1 | 5 | 1 |
| **decline** | 0 | 3 | 5 |

## Routing efficiency

- Pricing check **skipped** in 3/20 cases (coverage or consistency hard-fail found first).
  - Of those, 3 ended in **decline** — the skip didn't cost anything, the case was decisive without pricing input.
- Pricing check **ran** in 17/20 cases.

### Per-submission detail

| ID | Business | Known | Predicted | Correct | Pricing | Phase 2 reason |
|---|---|---|---|---|---|---|
| SUB-001 | Sunrise Diner Express | accept | accept | ✅ | ran | Ran pricing_checker — neither coverage_checker nor consistency_checker returned a hard-fail signal, so premium adequacy is still relevant. |
| SUB-002 | Lightwell Software Inc. | accept | accept | ✅ | ran | Ran pricing_checker — neither coverage_checker nor consistency_checker returned a hard-fail signal, so premium adequacy is still relevant. |
| SUB-003 | Thread & Co. Boutique | accept | accept | ✅ | ran | Ran pricing_checker — neither coverage_checker nor consistency_checker returned a hard-fail signal, so premium adequacy is still relevant. |
| SUB-004 | Electric Lounge | decline | refer | ❌ | ran | Ran pricing_checker — neither coverage_checker nor consistency_checker returned a hard-fail signal, so premium adequacy is still relevant. |
| SUB-005 | Bright Beginnings Learning Center | decline | refer | ❌ | ran | Ran pricing_checker — neither coverage_checker nor consistency_checker returned a hard-fail signal, so premium adequacy is still relevant. |
| SUB-006 | Summit Roofing Solutions | decline | decline | ✅ | ran | Ran pricing_checker — neither coverage_checker nor consistency_checker returned a hard-fail signal, so premium adequacy is still relevant. |
| SUB-007 | Lonestar Freight Lines | decline | decline | ✅ | skipped | Skipped pricing_checker — coverage_checker returned a critical finding (confidence 0.90): "Broker notes confirm the business operates 15 tra… |
| SUB-008 | Peak Commercial Builders | refer | accept | ❌ | ran | Ran pricing_checker — neither coverage_checker nor consistency_checker returned a hard-fail signal, so premium adequacy is still relevant. |
| SUB-009 | Lakeside Property Partners | refer | refer | ✅ | ran | Ran pricing_checker — neither coverage_checker nor consistency_checker returned a hard-fail signal, so premium adequacy is still relevant. |
| SUB-010 | Precision Molded Components | refer | refer | ✅ | ran | Ran pricing_checker — neither coverage_checker nor consistency_checker returned a hard-fail signal, so premium adequacy is still relevant. |
| SUB-011 | Corner Grill & Go | decline | decline | ✅ | skipped | Skipped pricing_checker — consistency_checker returned a critical finding (confidence 0.98): "Broker notes assert the business is an 'Excell… |
| SUB-012 | Vintage Thread Boutique | decline | decline | ✅ | skipped | Skipped pricing_checker — consistency_checker returned a critical finding (confidence 0.97): "The business is stated as 2 years old (opened … |
| SUB-013 | Ironclad Roofing Co. | refer | refer | ✅ | ran | Ran pricing_checker — neither coverage_checker nor consistency_checker returned a hard-fail signal, so premium adequacy is still relevant. |
| SUB-014 | Precision Auto Care | decline | refer | ❌ | ran | Ran pricing_checker — neither coverage_checker nor consistency_checker returned a hard-fail signal, so premium adequacy is still relevant. |
| SUB-015 | Midwest Plastics Group | accept | accept | ✅ | ran | Ran pricing_checker — neither coverage_checker nor consistency_checker returned a hard-fail signal, so premium adequacy is still relevant. |
| SUB-016 | Sunshine Auto Repair | refer | decline | ❌ | ran | Ran pricing_checker — neither coverage_checker nor consistency_checker returned a hard-fail signal, so premium adequacy is still relevant. |
| SUB-017 | The Velvet Room | decline | decline | ✅ | ran | Ran pricing_checker — neither coverage_checker nor consistency_checker returned a hard-fail signal, so premium adequacy is still relevant. |
| SUB-018 | Peachtree Logistics | refer | refer | ✅ | ran | Ran pricing_checker — neither coverage_checker nor consistency_checker returned a hard-fail signal, so premium adequacy is still relevant. |
| SUB-019 | Carolina Build Group | accept | accept | ✅ | ran | Ran pricing_checker — neither coverage_checker nor consistency_checker returned a hard-fail signal, so premium adequacy is still relevant. |
| SUB-020 | Coastline Apparel Co. | refer | refer | ✅ | ran | Ran pricing_checker — neither coverage_checker nor consistency_checker returned a hard-fail signal, so premium adequacy is still relevant. |
