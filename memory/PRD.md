# EASA Part-66 AI Study Assistant — PRD

## Original problem statement (summary)
A strictly source-grounded EASA Part-66 study and examination platform. The initial scope is Module 3 Electrical Fundamentals (B1.1/B2) only. Authoritative sources (the EASA guideline and the module course material) are provisioned on the backend; students never upload anything. Examination rules, knowledge levels, distribution, time and pass mark are extracted from the guideline. Questions use exactly 3 options with 1 correct answer and an EASA Level 1/2/3 (not easy/medium/hard). Everything is validated before a student sees it. The AI Tutor is source-locked and cites its sources, and is never hallucinated or browsed. The platform includes a mistake bank, adaptive practice, a 20-day plan, admin validation and activation, and an architecture ready for future modules.

## User choices
- LLM: Claude Sonnet 4.5 (claude-sonnet-4-5-20250929) via the Emergent LLM key
- Admin: JWT email/password login. Students: no login, one shared local profile
- Sources: EAR_BasicCourse_NewSyllabus.pdf (guideline, 92 p), M3 B1B2 I3R00 text PDF (455 p), example MCQ bank (style reference only, non-authoritative)

## Architecture
- backend/sources/ holds the provisioned PDFs plus manifest.json, which is auto-registered and ingested on first run
- guideline_parser.py: deterministic extraction of level definitions, format/time/pass rules, the count section (2.3), the level table (p.15-16), the syllabus (p.30-32) and the distribution (p.80-81). Columns are mapped to category groups and checked against the totals.
- ingestion.py: per-page chunks (page, page label, submodule, section, heading, source_type), an in-memory BM25 index, and document versioning/activation
- qgen.py: generation from a source-page window, then deterministic checks (3 options, banned phrases, length ratio, permitted level, fuzzy verbatim-quote traceability, cited page belongs to the submodule), then an independent LLM auditor (blind answer, source, single-correct, distractors, level, numerical, syllabus, exam-standard). Results are validated, rejected or review_required (source issue → flag).
- routes_student.py: bank, attempts, adaptive practice, mock exam built by distribution, performance by level, mistakes and insights, study plan, source chunk and page image
- routes_tutor.py: SSE source-locked tutor with 6 modes, refusal on low retrieval coverage, citations [p.N], SOURCE FLAG capture
- routes_admin.py: auth, KB status, document register/re-process/activate, configure module, first-run report, confirm config, activate module with prerequisites, generation jobs, audit, flags
- Frontend: React dark avionics UI. Dashboard, Tutor, Bank, Practice, Mock Exam, Mistakes, Plan, Admin (7 tabs)

## Implemented (2026-10-03)
- Module 3 B1/B2/B2L config extracted: 52 Q, 65 min, 3/1, 75%, 20 submodule rows, levels L1/L2. All checks VALID. Confirmed and activated.
- About 100 validated questions (bank fill job for 2 full exam sets)
- All student and admin features above. Testing iteration 1: backend 16/16, frontend all flows passing.

## Backlog
- P1: Admin editing of an ambiguous extracted configuration (currently REVIEW REQUIRED blocks confirmation; re-extraction only)
- P1: shadcn confirm dialog instead of window.confirm in the mock exam
- P2: Per-student accounts; Module 4+ content provisioning; diagram-aware questions (figure images)
