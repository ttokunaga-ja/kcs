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
8. Ownership has two levels. One parent chat session owns one complete persona
   and holds its persona lease. Within that chat, each artifact-producing
   subagent owns exactly one fixture-defined leaf folder for the duration of an
   assignment, for which the parent must hold a bound scope lease. Different leaf folders
   in the same persona may run concurrently; the same folder may not have two
   active writers. A Markdown claim alone is not ownership.
9. Before dispatch, the parent records the exact relative filenames, format
   families, artifact IDs, and narrative anchors assigned to each leaf folder.
   A scope worker may write only those final files below its assigned `home/`
   folder. Within its matching `_production/scopes/<scope-id>/`, it may update
   only scope-local status, inventory, provenance, QA, prompts, temp, renders,
   and evidence. It must not edit persona-wide controls or aggregates, another
   scope, or the parent-owned scope `WORKSPACE.md`, `manifest.json`,
   `assignment.json`, lease, lock, or recovery log.
10. At each checkpoint the scope worker updates its scope-local status,
    inventory, failures, decisions, and exact next action. After workers stop,
    the parent chat validates and deterministically aggregates those records
    into the persona-wide checkpoint. A later parent chat must be able to
    resume without rediscovering what was generated or inspected.
11. Persona and scope leases prevent accidental duplicate assignment among
    cooperating sessions. They are not security boundaries against processes
    with direct write access as the same OS user. Forced recovery is a trusted
    parent/user operation and must never be delegated to an artifact-producing
    subagent.
