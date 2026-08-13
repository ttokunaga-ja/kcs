# Common production rules

1. Treat `eval/persona_fixture_spec.py` as authoritative. Do not rename,
   omit, add, or reweight personas, primary paths, shared secondary paths,
   format families, or percentages. Materialize files only below the assigned
   `<pXX-role>/home/` root.
2. All content is synthetic: never use real PII, PHI, credentials, secrets,
   customer data, or copied private documents. Use invented but internally
   consistent people, organizations, account numbers, and identifiers.
3. Maintain a believable per-persona narrative. Names, project/study/account
   IDs, dates, milestones, amounts, terminology, conclusions, and revisions
   must agree across related files. Record the persona lexicon and timeline in
   its production metadata.
4. Use ordinary generation for text, code, and data. Where quality benefits,
   use the named **Documents**, **PDF**, **Spreadsheets**, **Presentations**, or
   **ImageGen** skill for DOCX, XLSX, PPTX, `pdf_text`, `pdf_scan`, or image
   artifacts. A scan PDF requires ImageGen plus the PDF workflow.
5. Before using any named skill, the worker must read its relevant `SKILL.md`.
   Render and inspect every final document page, PDF page, spreadsheet sheet,
   slide, and image as that skill requires. Store QA evidence outside `home/`.
6. Keep temporary sources, render outputs, and scratch work separate from final
   corpus paths. Promote only reviewed final files into `home/`; record source,
   generator/skill, seed, and checksum or equivalent provenance in the manifest.
7. Do not design product-search QA or assert searchability from raw artifacts.
   This workflow produces corpus files and artifact QA only; evaluator/index
   validation remains governed by the fixture and its existing tooling.
8. The normal parallel unit is one worker per persona folder. Because each
   worker/session owns one complete persona folder `<persona>/`, including its `home/`
   and `_production/` trees. Distinct persona folders do not conflict and may
   run concurrently. The worker must hold that persona's atomic `lease.json`; never run
   multiple writers inside one persona. Do not alter another worker's folder or
   shared planning files. A Markdown claim alone is not ownership.
9. At each checkpoint update per-persona status, inventory, failures, decisions,
   and the exact next action. A later session must be able to resume without
   rediscovering what was generated or inspected.
10. The lease prevents accidental double assignment among cooperating sessions.
    It is not a security boundary against processes with direct write access as
    the same OS user. Forced recovery is a trusted parent/user operation and
    must never be delegated to an artifact-producing subagent.
