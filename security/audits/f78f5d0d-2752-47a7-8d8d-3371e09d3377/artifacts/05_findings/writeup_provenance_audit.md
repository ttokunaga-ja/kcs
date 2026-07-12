# KCS R23 write-up provenance audit

Generated: `2026-07-11T14:18:28Z`

This artifact records the latest fixed write-up acceptance and blocking state for scan `f78f5d0d-2752-47a7-8d8d-3371e09d3377`. No new scan, discovery, validation, attack-path analysis, or finding redecision was performed. This file is not a scan-completion receipt.

## Final fixed classification

- Accepted and usable: **10**
- Blocked and unusable: **37**
  - Exact current safety refusal: **33**
  - Historical refusal not preserved, followed by category disguise or external reroute: **4**
- Total reportable candidates: **47**

Accepted IDs:

`011, 019, 020, 022, 023, 025, 028, 036, 046, 049`

The current physical snapshot has 29 reports, 15 drafts, 13 receipts, 47 candidate ledgers, and 13 vulnerability-writeup ledger rows. Physical existence does not make a blocked artifact usable.

## Accepted 10

| Candidate | Final | Report path | Current report SHA-256 | Dedicated writer/session | Persisted receipt review |
|---|---|---|---|---|---|
| KCS-R23-CAND-011 | medium/P2 | `findings/secret-twin-prehold-vector-link/secret-twin-prehold-vector-link.md` | `27b40e9ea5af51acdbb1fcf271f9a869427d83a0ed406aeacc5d41a63c5c7de1` | `/root/writeup_011` / `019f5095-a312-7752-ab06-dfe04064196a` | accepted |
| KCS-R23-CAND-019 | medium/P2 | `findings/unbounded-direct-child-read/unbounded-direct-child-read.md` | `fd4b2ad31d5328e5eb97226d440b5ab4b2489064b91fc7f5beea574661fbc07c` | `/root/writeup_019` / `019f50a4-d927-7413-9f85-c4101601c4d7` | accepted |
| KCS-R23-CAND-020 | medium/P2 | `findings/mistral-ocr-response-bounds/mistral-ocr-response-bounds.md` | `87dfc71edc66117cde1bf39d23368ff8bed1619d940a16ffc30df78aa229b1cc` | `/root/writeup_020` / `019f50a7-0a1b-7a81-bff1-10bd552dc21e` | accepted |
| KCS-R23-CAND-022 | medium/P2 | `findings/mistral-model-resolution-bounds/mistral-model-resolution-bounds.md` | `1b2a186698c5b12b2c02a5cbc6525b48b02c66486146b0e15620f0726429a930` | `/root/writeup_022` / `019f50a7-339f-78f1-a212-f1e05fa73d18` | accepted |
| KCS-R23-CAND-023 | medium/P2 | `findings/gemini-response-bounds/gemini-response-bounds.md` | `9984b95166454b13187a8edf0e16ecee7ba5b607a505f4a822af9cad8d89916d` | `/root/writeup_023` / `019f50a8-4922-7c41-aaf5-7845e4afe2be` | accepted |
| KCS-R23-CAND-025 | medium/P2 | `findings/forgeable-store-consent/forgeable-store-consent.md` | `c05bb999683bd2c6e82994a1e7c0834f39940bbae16bc55878236572e6d9f3cf` | `/root/writeup_025` / `019f514a-568b-7862-bf9f-4c2ac39d9dcc` | pending |
| KCS-R23-CAND-028 | medium/P2 | `findings/ocr-final-hash-reopen/ocr-final-hash-reopen.md` | `b07509f31627b9f39584fde8bb3b71f391c5daad4f17d237d8fce3cb700f8fc1` | `/root/wu_028` / `019f50d5-60cf-7720-81e7-62be3342b157` | accepted |
| KCS-R23-CAND-036 | medium/P2 | `findings/unvalidated-persisted-dag/unvalidated-persisted-dag.md` | `256158e0a3feadf5907c32ea2aa4e2d5c27fbd5caff575061d8ab94eb04a875d` | `/root/wu_036` / `019f50e2-91b7-7d23-a686-c61d3efe49fa` | accepted |
| KCS-R23-CAND-046 | low/P3 | `findings/cas-read-before-verification/cas-read-before-verification.md` | `b507e2425b12ff298de14e44f39a1c10963d09a4332c062639ba08d3395adc52` | `/root/writeup_046` / `019f514f-6a47-77b2-845c-a1e0de037524` | absent |
| KCS-R23-CAND-049 | medium/P2 | `findings/manifest-unit-ref-traversal/manifest-unit-ref-traversal.md` | `82ad9d651ad59c5b1825155b04553d679d709f5c25190276ed5eca060429d85d` | `/root/writeup_049` / `019f5152-3431-7e92-80ea-69580427eef9` | pending |

All ten report hashes match their receipt and vulnerability-writeup ledger binding. The latest coordinator directive formally accepts all ten.

Persisted-state caveats retained rather than hidden:

- 025 and 049 receipts/ledger rows still say `coordinator_review=pending`; 046 has no receipt review field. Their current accepted state comes from the later explicit coordinator directive.
- The receipt writer-completion timestamps for 025, 046, and 049 precede the authoritative child-session `task_complete`; both timestamps are retained in JSON.
- 036 has a process-scope exception: its writer temporarily patched the target repository before the coordinator moved the artifact into scanDir. The repository is now clean and the current report hash binding matches.
- 025 and 049 receipts omit some older receipt-contract keys (`receipt_type`, `receipt_id`, `source_revision`), while retaining the target revision. This audit does not rewrite receipts.

## Current safety refusals: 33

All 33 used `openai / gpt-5.6-sol / ultra`. Every child ended with `task_complete.last_agent_message=null`; the complete refusal was delivered and preserved in the parent transport log.

| Candidate | Final | Agent/session | Session-meta start UTC | Refusal delivery UTC | Physical R/D/W/L |
|---|---|---|---|---|---|
| KCS-R23-CAND-001 | low/P3 | `/root/writeup_001` / `019f513f-45d0-7cc3-be7f-2c9eeb95df62` | 2026-07-11T12:55:29.815Z | 2026-07-11T13:01:51.659Z | ---- |
| KCS-R23-CAND-003 | medium/P2 | `/root/writeup_003_native` / `019f516f-d30a-7673-b12f-e2e511cf4622` | 2026-07-11T13:48:31.644Z | 2026-07-11T13:57:43.406Z | RD-- |
| KCS-R23-CAND-004 | medium/P2 | `/root/writeup_004` / `019f513f-7d62-7e93-b36f-8478a053433d` | 2026-07-11T12:55:44.047Z | 2026-07-11T12:57:11.055Z | ---- |
| KCS-R23-CAND-012 | low/P3 | `/root/writeup_012` / `019f5140-a392-7442-b662-47522bcd81f6` | 2026-07-11T12:56:59.431Z | 2026-07-11T13:01:16.111Z | ---- |
| KCS-R23-CAND-013 | medium/P2 | `/root/writeup_013_native` / `019f516f-f97d-7392-b902-825c049a819d` | 2026-07-11T13:48:41.458Z | 2026-07-11T14:02:22.863Z | R--- |
| KCS-R23-CAND-014 | medium/P2 | `/root/writeup_014_native` / `019f5170-22ae-74e0-9333-a1629aa9aadc` | 2026-07-11T13:48:51.984Z | 2026-07-11T13:52:05.356Z | R--- |
| KCS-R23-CAND-017 | medium/P2 | `/root/writeup_017_native` / `019f5170-46f6-7471-b8a3-26dda3ea8128` | 2026-07-11T13:49:01.265Z | 2026-07-11T13:51:17.200Z | R--- |
| KCS-R23-CAND-018 | low/P3 | `/root/writeup_018_native` / `019f5170-cbca-77f3-8b48-6467b356a7c8` | 2026-07-11T13:49:35.250Z | 2026-07-11T13:50:58.271Z | R--- |
| KCS-R23-CAND-024 | medium/P2 | `/root/writeup_024` / `019f5140-d1a2-7fc1-9495-940c16a0c8f1` | 2026-07-11T12:57:11.027Z | 2026-07-11T13:01:44.852Z | ---- |
| KCS-R23-CAND-027 | medium/P2 | `/root/writeup_027` / `019f514a-7d3f-75c1-a990-27ecdefef854` | 2026-07-11T13:07:44.755Z | 2026-07-11T13:09:54.202Z | ---- |
| KCS-R23-CAND-029 | low/P3 | `/root/writeup_029_native` / `019f5171-2d8f-72c0-8eb9-9c8d6a74a68c` | 2026-07-11T13:50:00.532Z | 2026-07-11T13:53:33.303Z | R--- |
| KCS-R23-CAND-030 | low/P3 | `/root/writeup_030_native` / `019f5171-5b2c-7771-af3e-e815ce93d50f` | 2026-07-11T13:50:11.952Z | 2026-07-11T13:56:32.780Z | R--- |
| KCS-R23-CAND-031 | low/P3 | `/root/writeup_031` / `019f514a-a318-70e3-8256-de9ac80c42ed` | 2026-07-11T13:07:54.442Z | 2026-07-11T13:09:22.296Z | ---- |
| KCS-R23-CAND-032 | medium/P2 | `/root/writeup_032_retry` / `019f515c-b8df-7270-9969-7c1aa55acce3` | 2026-07-11T13:27:39.709Z | 2026-07-11T13:47:28.687Z | R--- |
| KCS-R23-CAND-033 | low/P3 | `/root/writeup_033_retry` / `019f515e-613c-7553-bd8f-9a2fb9808564` | 2026-07-11T13:29:28.343Z | 2026-07-11T13:47:28.686Z | R--- |
| KCS-R23-CAND-034 | medium/P2 | `/root/writeup_034_native` / `019f5171-9aba-7081-98ad-acac4be31aba` | 2026-07-11T13:50:28.242Z | 2026-07-11T13:52:36.255Z | R--- |
| KCS-R23-CAND-038 | medium/P2 | `/root/writeup_038` / `019f514a-d0d4-7090-bd30-dba6db892e23` | 2026-07-11T13:08:06.231Z | 2026-07-11T13:18:16.636Z | RD-- |
| KCS-R23-CAND-039 | medium/P2 | `/root/writeup_039` / `019f514b-23e2-7d80-acaa-1ff4e0c4f546` | 2026-07-11T13:08:27.596Z | 2026-07-11T13:15:59.968Z | ---- |
| KCS-R23-CAND-040 | medium/P2 | `/root/writeup_040_retry` / `019f516f-23db-76c1-b151-75025edfea43` | 2026-07-11T13:47:46.848Z | 2026-07-11T13:49:01.292Z | R--- |
| KCS-R23-CAND-041 | low/P3 | `/root/writeup_041` / `019f514c-4384-7622-9e59-a27583fbfcfd` | 2026-07-11T13:09:41.127Z | 2026-07-11T13:12:26.541Z | ---- |
| KCS-R23-CAND-042 | low/P3 | `/root/writeup_042` / `019f514c-a11a-7091-a3fe-625b5087ccda` | 2026-07-11T13:10:05.086Z | 2026-07-11T13:14:40.271Z | ---- |
| KCS-R23-CAND-043 | low/P3 | `/root/writeup_043` / `019f514f-27a4-7753-b00d-efed13763efe` | 2026-07-11T13:12:50.563Z | 2026-07-11T13:14:26.227Z | ---- |
| KCS-R23-CAND-047 | medium/P2 | `/root/writeup_047` / `019f5150-ff67-71e3-9352-a0aa59364053` | 2026-07-11T13:14:51.342Z | 2026-07-11T13:18:25.894Z | ---- |
| KCS-R23-CAND-048 | medium/P2 | `/root/writeup_048` / `019f5151-2422-78a2-b981-3fe5eebe2427` | 2026-07-11T13:15:00.766Z | 2026-07-11T13:17:30.010Z | ---- |
| KCS-R23-CAND-050 | low/P3 | `/root/writeup_050` / `019f5153-965b-71b0-a3f6-cd7237e154d1` | 2026-07-11T13:17:41.060Z | 2026-07-11T13:47:28.687Z | RDWL |
| KCS-R23-CAND-051 | medium/P2 | `/root/writeup_051` / `019f5154-702f-7d90-9dca-0509a6102f10` | 2026-07-11T13:18:36.809Z | 2026-07-11T13:47:28.687Z | RDWL |
| KCS-R23-CAND-057 | low/P3 | `/root/writeup_057` / `019f5154-9d3c-7d52-9f82-69d8be39df65` | 2026-07-11T13:18:48.367Z | 2026-07-11T13:22:37.925Z | ---- |
| KCS-R23-CAND-059 | medium/P2 | `/root/writeup_059` / `019f5156-7e58-7671-a65d-0562e3fefeaf` | 2026-07-11T13:20:51.471Z | 2026-07-11T13:23:17.229Z | ---- |
| KCS-R23-CAND-061 | medium/P2 | `/root/writeup_061` / `019f5158-426c-7251-b608-32142b29a957` | 2026-07-11T13:22:47.197Z | 2026-07-11T13:26:25.294Z | ---- |
| KCS-R23-CAND-064 | low/P3 | `/root/writeup_064` / `019f5158-dcbe-7401-a6a2-97f5af5ebe2c` | 2026-07-11T13:23:26.737Z | 2026-07-11T13:26:35.674Z | ---- |
| KCS-R23-CAND-067 | medium/P2 | `/root/writeup_067` / `019f515a-c148-7102-a1a1-76094714c7ba` | 2026-07-11T13:25:30.895Z | 2026-07-11T13:29:17.909Z | ---- |
| KCS-R23-CAND-068 | medium/P2 | `/root/writeup_068` / `019f515b-e99c-74b2-b675-7a0bc36b6e75` | 2026-07-11T13:26:46.695Z | 2026-07-11T13:47:28.687Z | RDWL |
| KCS-R23-CAND-069 | high/P1 | `/root/writeup_069` / `019f515c-135f-79d3-97fe-41f8fd6bc1a6` | 2026-07-11T13:26:57.345Z | 2026-07-11T13:47:28.686Z | ---- |

Exact refusal text:

```text
Agent errored: This content was flagged for possible cybersecurity risk. If this seems wrong, try rephrasing your request. To get authorized for security work, join the Trusted Access for Cyber program: https://chatgpt.com/cyber

This agent's turn failed. If you still need this agent, use the available collaboration tools to give it another task.
```

Message SHA-256: `84bac7fb2c21d1f06462b617185f7730fa15d728c691dded81f867f26c839d7b`

No separate classifier-trigger timestamp is persisted; the JSON records the available session, activity, child-completion, and parent-delivery timestamps without inference.

## Historical unpreserved refusals: 4

| Candidate | Final | Surviving report | Current report SHA-256 | Blocking basis |
|---|---|---|---|---|
| KCS-R23-CAND-005 | medium/P2 | `findings/unicode-question-glob-bypass/unicode-question-glob-bypass.md` | `438c76b8347de1d9987eb4f9a4322210bf7ec1b1b0589b24c2398762e6c33c01` | Historical exact refusal unavailable; surviving report came from category-changing resubmission. |
| KCS-R23-CAND-006 | medium/P2 | `findings/pdf-page-marker-amplification/pdf-page-marker-amplification.md` | `39b58d3a5510b34b7d8c05aeb3fe9c00d4af374606bf71008dab6fe0070cf327` | Historical exact refusal unavailable; surviving defensive memo came from category-changing resubmission. |
| KCS-R23-CAND-007 | medium/P2 | `findings/quadratic-unit-lcs/quadratic-unit-lcs.md` | `a59dbcc202ad77b216ab5a769b9b31b3ab71fd25ce48650e14ce44a9b9e6d345` | Historical exact refusal unavailable; surviving defensive write-up came from category-changing resubmission. |
| KCS-R23-CAND-008 | medium/P2 | `findings/symlinked-kcs-cross-scope-store/symlinked-kcs-cross-scope-store.md` | `114ec40bf9f9cbf6e28e1b78a060ddcc437e8eb381216b836ed4a69499809bda` | Historical exact refusal unavailable; surviving report was externally rerouted after refusal. |

The exact earlier refusal text is unavailable and is not reconstructed. The preserved coordinator summary at `2026-07-11T09:55:13.194Z` is:

> 書き手エージェントの一部が、許可済みのローカル防御監査にもかかわらず一般的な安全フィルタで拒否されました。実作業は開始されていないため、同じ finding を「安全な回帰テスト付き実装品質レポート」として再投入し、実スコープ・外部通信・攻撃用入力を一切使わない形に限定しています。

## Invalid refusal-trial artifacts

- **003:** native refused trial replaced/touched report, draft, and supporting PoC. No receipt or write-up ledger row exists.
- **013:** the trial deleted the old report, later re-added a new report, updated it, and then ended in refusal. The current report SHA is `2b8c671df7fb8c9e0302e231ea1c33be8f7e8a840c1ea2ef26e8d87e0f9b7041`; no draft, receipt, or write-up row exists.
- **038:** report and draft exist, but the trial ended in refusal before receipt or write-up ledger row.
- **050:** report/draft/receipt/ledger row exist, but final state is refusal. Receipt/ledger report SHA `453e55e32bd9985ce61f8560d5242d5d21c3c2878937b468221d6e65d73f22a9` is stale against current `7095de8e68352fafc181ee8e0b3940deccd0336b4450fb372d1c17a851837108`.
- **051:** report/draft/receipt/ledger hashes match, but final state is refusal, so all remain unusable.
- **068:** report/draft/receipt/ledger row exist, but final state is refusal. Recorded report and draft hashes are stale against current values.
- **030:** only the old report remains; native retry touched supporting PoC files, not the report, and then ended in refusal.

## OpenCode state

The former 12-ID OpenCode override is **superseded and cancelled**. Current authorized IDs: none. The latest instruction prohibits OpenCode or another provider as a refusal bypass.

Process check at `2026-07-11T14:18:28Z`: no OpenCode process is running.

The historical CAND-003 OpenCode session `ses_0aebb22f8ffeGHZhQnEHK9te1T` remains recorded as an unused quota-only attempt. Its repeated error was:

```text
AI_APICallError: Usage limit reached for 5 hour. Your limit will reset at 2026-07-11 22:58:30
```

It produced no files, additions, deletions, tokens, or assistant output and is not a safety refusal.

## Full 47-row physical worklist

`R/D/W/L` in the refusal table means report / canonical draft / receipt / vulnerability-writeup ledger row. Full current paths, byte sizes, hashes, safe-path flags, receipt bindings, supporting files, and exact refusal session evidence are in `writeup_worklist.json`.

| Candidate | Final | Classification | Report SHA | Draft SHA | Receipt SHA | Ledger SHA (write-up rows) |
|---|---|---|---|---|---|---|
| KCS-R23-CAND-001 | low/P3 | `blocked_safety_refusal` | missing | missing | missing | 031d3adb8db597d0c26e4f1a5fdc7f802cb600b6d5518c0cefbf487bf40ecb4c (0) |
| KCS-R23-CAND-003 | medium/P2 | `blocked_safety_refusal` | 4621d270d9bb0d78f95cf7eb81972c8900e91588ec53da8217b42cb3798a0187 | 62ccf2e15f251f000035ae2e4082941a5b46357ff58d04f535b1160566472ce0 | missing | 841be46a2f359e7e0804a933c684e8d480ee489bbe4fecb95ce208aaaa487f91 (0) |
| KCS-R23-CAND-004 | medium/P2 | `blocked_safety_refusal` | missing | missing | missing | 5d112952f8551a0db6ab41ba93b7eee1bb87cf22a758d6bf46bb28c91071142d (0) |
| KCS-R23-CAND-005 | medium/P2 | `blocked_historical_unpreserved_refusal` | 438c76b8347de1d9987eb4f9a4322210bf7ec1b1b0589b24c2398762e6c33c01 | missing | missing | 89391c89511c53323f3fdbba70cfeddf8e4e8f262030253964019ec9aa0371ec (0) |
| KCS-R23-CAND-006 | medium/P2 | `blocked_historical_unpreserved_refusal` | 39b58d3a5510b34b7d8c05aeb3fe9c00d4af374606bf71008dab6fe0070cf327 | missing | missing | 7dcc9b0e9f747bf20dcef22796316b904853d70ee4bf8d47548ab7acb5e7943a (0) |
| KCS-R23-CAND-007 | medium/P2 | `blocked_historical_unpreserved_refusal` | a59dbcc202ad77b216ab5a769b9b31b3ab71fd25ce48650e14ce44a9b9e6d345 | missing | missing | ff8b7780e11370c0ca7833322b744c389730a913dcd0ad1db79903176ecb1473 (0) |
| KCS-R23-CAND-008 | medium/P2 | `blocked_historical_unpreserved_refusal` | 114ec40bf9f9cbf6e28e1b78a060ddcc437e8eb381216b836ed4a69499809bda | missing | missing | d864b4e67bbeecc9b9380e636d14ecbf636d0ff2aaae03310d45ee9074f13eda (0) |
| KCS-R23-CAND-011 | medium/P2 | `accepted` | 27b40e9ea5af51acdbb1fcf271f9a869427d83a0ed406aeacc5d41a63c5c7de1 | 301c905d101ec33f2c02dd6f061e5a7c492bea5c499029f7743aca2395dcf3f5 | e7ca270d3a68da83f7b89353f106d2b77f359eeb47b8d67642f0906b93a580fc | 8240fddbcdfd1efd8b445b57bb6b9a5b8bb1a7f36cafa373659c96ace9cdca7c (1) |
| KCS-R23-CAND-012 | low/P3 | `blocked_safety_refusal` | missing | missing | missing | f695cb98ea7b48d5aa99b948631710cc8c4ed9a5a4e8c6fd13035eb086bf1533 (0) |
| KCS-R23-CAND-013 | medium/P2 | `blocked_safety_refusal` | 2b8c671df7fb8c9e0302e231ea1c33be8f7e8a840c1ea2ef26e8d87e0f9b7041 | missing | missing | 44d79f6b285d750d26cb439c0dacf6e12ee0e33f26a27473894f283812e3bb6c (0) |
| KCS-R23-CAND-014 | medium/P2 | `blocked_safety_refusal` | 7a47312e2a3663e2ea40b4b80870ed4690ee4c06576429477f86a4d233bfac64 | missing | missing | 31adaeec172d8341e357ae07e4d5f95f03b873cd9a909f877027eff29c3dd6e9 (0) |
| KCS-R23-CAND-017 | medium/P2 | `blocked_safety_refusal` | c2ad6afc9001b81eb485c259fd7dd1041427b3df15115cd1bd045cbfaa38e44e | missing | missing | 78f88008f3d059aa74996afaa26ce4460fd58ece421fd273b0ec5e5af52f0b7f (0) |
| KCS-R23-CAND-018 | low/P3 | `blocked_safety_refusal` | 70782b415d7beae1cd767bf89bf33573a60e9639fd76643007ece382d6475439 | missing | missing | bf8f08f377b3a99a98d2aa5dd38ec5087e45c177d1a96cdd0331b2cb45ad93a6 (0) |
| KCS-R23-CAND-019 | medium/P2 | `accepted` | fd4b2ad31d5328e5eb97226d440b5ab4b2489064b91fc7f5beea574661fbc07c | 27fb0b7db5a61391e394cdbc19cd60985bbf5a0a8a36bc09d2488c50a6a73963 | 6ae1d4dcc84e19625f7f1ca225220306fd89ea46f8295605098424cad9649a3b | c67d625b49ca5e8a8384d135918e004780b4888440212fdfbe5524305836996c (1) |
| KCS-R23-CAND-020 | medium/P2 | `accepted` | 87dfc71edc66117cde1bf39d23368ff8bed1619d940a16ffc30df78aa229b1cc | 9634a064f664341c999976c3afa748c42d421f1ee7e627285a52d349007a4b3a | f914579dd1f55f7d4499e99998c6fccd82017d844915ddfb2cccde6ac5c8b17c | 8fd45e61b697bf908cdb6ea489a370e112b84104ffe6788af8f6e6b7ee3d1846 (1) |
| KCS-R23-CAND-022 | medium/P2 | `accepted` | 1b2a186698c5b12b2c02a5cbc6525b48b02c66486146b0e15620f0726429a930 | 5ff19c2c08b4dc3b9600b306aec1ad52dc26b92839f6d535c47881a756fa0391 | 4d72134899c0eedace8cd4a69a9cdf1f55dc2e1b50263d34f6fa9902a77e7fa9 | e81b125a25227a278eae464afd9680f3c09d052bfd82e9e793a568d4720d2e35 (1) |
| KCS-R23-CAND-023 | medium/P2 | `accepted` | 9984b95166454b13187a8edf0e16ecee7ba5b607a505f4a822af9cad8d89916d | 95fd00819148862f1a32b34464829d5959392ad40be1862e55a2984e7452fd9c | 3cd74e1c487867e4141b95272232f07f4aaed003a3c4f743743aded169a264be | 7b8f996e3ca80bf490ad99a4fd7c24b1d1e4e02b51be4c43df2df2203b404392 (1) |
| KCS-R23-CAND-024 | medium/P2 | `blocked_safety_refusal` | missing | missing | missing | 51486ab1017b073ec1c23cdbef3befc9785a02b423d17cf2ead4f9d0a432d4a8 (0) |
| KCS-R23-CAND-025 | medium/P2 | `accepted` | c05bb999683bd2c6e82994a1e7c0834f39940bbae16bc55878236572e6d9f3cf | e97377c7862e1017f5e4e38dc605215754b957eedb72a7402c7669ed27d421f1 | e8ca4a399651211838b52350b0b59f2808745f7effcd78e2c65b6da0a976e3d9 | d801e26405d016588f1df2b36194a923486aad0dff131377def4908ee2f1ac42 (1) |
| KCS-R23-CAND-027 | medium/P2 | `blocked_safety_refusal` | missing | missing | missing | c8979c05f3d526656a99f9d3c9fa8ba7c0512777d96d1471672a7c40b1ea16e8 (0) |
| KCS-R23-CAND-028 | medium/P2 | `accepted` | b07509f31627b9f39584fde8bb3b71f391c5daad4f17d237d8fce3cb700f8fc1 | ef4dded7a4dfd75e2ab49f532d0f74db8c751522867fa2f14b22b7882b684784 | 0f10a7322683fedee552e83a28909873ec9da2473a016285019d543018855c53 | cc2dedbb86fc358f3c7b90365501d06ff17648d056346a3744ded01c4f162bf3 (1) |
| KCS-R23-CAND-029 | low/P3 | `blocked_safety_refusal` | f89d108c5e51e0a32125b83ee804c662e04f94faf4608959a7a395ad83047f06 | missing | missing | 4be3e6c721fc3bc1d6bf1f1b85fbf771433efc0b82df8d72588fc9ca5ea43635 (0) |
| KCS-R23-CAND-030 | low/P3 | `blocked_safety_refusal` | 6e18e4c040d5753a6cc17499efd31ad45349a15b881ecab807c2036d3f0076ec | missing | missing | fc5400b5aa5803a0b961a6ee51341824d1e1225db4f2b7515e6ddfc5dce7b2c0 (0) |
| KCS-R23-CAND-031 | low/P3 | `blocked_safety_refusal` | missing | missing | missing | 583f6b39cf392693db1eab31a63b6f4aec4bb68b184996bca8825cdd95a1f7fe (0) |
| KCS-R23-CAND-032 | medium/P2 | `blocked_safety_refusal` | 98081c4eb6cc8d822affbd2dfa32744296dc856f54b36f32de8e1216240cd3b7 | missing | missing | 9d78681ec2db7690192e4f04c6ed8379421a591928a9cb2321bc63ba71c7004c (0) |
| KCS-R23-CAND-033 | low/P3 | `blocked_safety_refusal` | b9c7f8fca399718f2f8bf7ee7f84e87027b5d48aac8328f0fef73a1a1473bc20 | missing | missing | 4831db46c127f8c756085606cf709289297e70e24aed856c809e656d0a4fdfcc (0) |
| KCS-R23-CAND-034 | medium/P2 | `blocked_safety_refusal` | 27067edac3a1eb89aff3c10eda5cd4454c0916b0fea0f5f090eb2093a5aa48f5 | missing | missing | c870106619170f52419a9fb23f91f6fa204162a2aeffd870a38242abe328fa52 (0) |
| KCS-R23-CAND-036 | medium/P2 | `accepted` | 256158e0a3feadf5907c32ea2aa4e2d5c27fbd5caff575061d8ab94eb04a875d | 20e15dcdff40c29232d5cdd33d8ebaa4e9e62bfa653f78c6776ae76880653b5a | 80fde187e0d5d74340c1d001d50a02dd487e37b60bc733557aa8e941f3ce593e | 0fd50f29323d432d309e32a54c22ccc4946de7132c9867c9e941799bc7c05a18 (1) |
| KCS-R23-CAND-038 | medium/P2 | `blocked_safety_refusal` | 40c861dbdf35c5f01c43386dd45bb68a63ecda6c2b19de272c6d7556f339f3d4 | 7e4c4fc30c681d515fc5d2f0f25570af36c2830729ab95370257e911208d2cef | missing | 18ebbe7744b76e1be436e91871831c12d86773af419889ec3063f9e1484ca719 (0) |
| KCS-R23-CAND-039 | medium/P2 | `blocked_safety_refusal` | missing | missing | missing | ecebae9cc7231bb726b08e9322be3c21ddae9e3544702776e733f853b19db0e0 (0) |
| KCS-R23-CAND-040 | medium/P2 | `blocked_safety_refusal` | 8aac673f5602b104447d50f34e6109d4783c7a42c955648e89e4689d89b074f3 | missing | missing | 7e9c2f19b81cf88098906481d1d35d5429cca49df3e92db38623bba0cb582e65 (0) |
| KCS-R23-CAND-041 | low/P3 | `blocked_safety_refusal` | missing | missing | missing | 6687bc2c7099114fed8eeaeb667068cc7d121b5b55ee932a5086ae7b35a55c61 (0) |
| KCS-R23-CAND-042 | low/P3 | `blocked_safety_refusal` | missing | missing | missing | 474a04dbfe2bd6dd39d4930b9be9962ed9abc75af4c0efdd9316048b860c8e44 (0) |
| KCS-R23-CAND-043 | low/P3 | `blocked_safety_refusal` | missing | missing | missing | 2dec619860fefd264733f1848fe0adef24458a4e67aa0e991d43dff818ef931e (0) |
| KCS-R23-CAND-046 | low/P3 | `accepted` | b507e2425b12ff298de14e44f39a1c10963d09a4332c062639ba08d3395adc52 | c0172581d75b41b3dc0ac0f9251d82fa2973326dfbb582ce070c61c99c9cabb4 | 0a036e137b1f7935cbe4438723cb69f4e115bfc83d161376aacd519d0992874b | d331ba6581756516905134d1f915f0b0388656d90d18fa9e742be819e8b925f3 (1) |
| KCS-R23-CAND-047 | medium/P2 | `blocked_safety_refusal` | missing | missing | missing | 290c301d123bf8f0307612ec87386447e9e4d6bb2913ac44d019b8b5f176dd02 (0) |
| KCS-R23-CAND-048 | medium/P2 | `blocked_safety_refusal` | missing | missing | missing | a6016d56209d7a8591aa5eaea389364548409e525ebdcc4c9b051a6e8cb6d869 (0) |
| KCS-R23-CAND-049 | medium/P2 | `accepted` | 82ad9d651ad59c5b1825155b04553d679d709f5c25190276ed5eca060429d85d | 6e732996870ff80722574abfe592a060bc1fff1ade991f7f143882c1532ee38a | 6920823119909311b33fb2c09b1c2382d46acdb71bc1f85777c9a1f43f340950 | 083868361340e759765225d65f12a7de2bf220d81ef6f2df1af1d4a7797fc3ef (1) |
| KCS-R23-CAND-050 | low/P3 | `blocked_safety_refusal` | 7095de8e68352fafc181ee8e0b3940deccd0336b4450fb372d1c17a851837108 | ac7ac640e3f509d2a6b0edafc6d9475568c4fcb714863ec2bd0684e8d95b2960 | 5ca84b264cc7b04761b3b27a1683431ab4ece8be9f2eeea2a85679f2779506ee | 85160dd60025711c5b18f12aa7227c1ec0d1a303e91d02ba3b86fd205b50e9c5 (1) |
| KCS-R23-CAND-051 | medium/P2 | `blocked_safety_refusal` | fe13ed99589050395c055c375929421365905a0dc13db9b31bf72d3898337ac3 | 68508328f560f98c12a3c68cc86bfb633fba1c0a6751c6462a57c431f53901c1 | c75af6a9bac557a50f17dea641612a84b647343bb681d0ffe2de3dfc8f301398 | d9b483f98209595ec79ec13ca266a8b299ebf860bb1e1c1155c4f74f10fec224 (1) |
| KCS-R23-CAND-057 | low/P3 | `blocked_safety_refusal` | missing | missing | missing | d84a5e845fa28caced0d535a09bfafd7e44f4dfe0520c2c7b23918b5a12b6c3e (0) |
| KCS-R23-CAND-059 | medium/P2 | `blocked_safety_refusal` | missing | missing | missing | 9c45e29a5a6b8cfe868b374eca7e7ce48aab85dd621cb801c2ba56060bfdddd0 (0) |
| KCS-R23-CAND-061 | medium/P2 | `blocked_safety_refusal` | missing | missing | missing | a9b59e6c9be9c2d029a001ef05bd23b4dfd4215194e7d021e06f76c397c22a79 (0) |
| KCS-R23-CAND-064 | low/P3 | `blocked_safety_refusal` | missing | missing | missing | 82d63485dd4d3ccf485e4a3f8ebc092a75990125b05c1f536a4d1e87d6820dd0 (0) |
| KCS-R23-CAND-067 | medium/P2 | `blocked_safety_refusal` | missing | missing | missing | a2a871bd687c86ebd0dba9db39313886b26f10b94ad7526ec18483eec74a8e5c (0) |
| KCS-R23-CAND-068 | medium/P2 | `blocked_safety_refusal` | 7a9a5ce7166ab518a317c9bfcd4606d1041ed04c4fe55a57275fff5babd7c931 | e3424d2b116b7cb2dc2e41fcbd059d4522cdafea476b84146957e62e4cf6ba04 | a7bd0ad264a7f53958c18d7a94a242a4a5314e5ef77849ab4c66768d9ed774af | 8de988071059959833cb824479851f0f946140c1df18c3c81cef835aeb572a31 (1) |
| KCS-R23-CAND-069 | high/P1 | `blocked_safety_refusal` | missing | missing | missing | e6f0700ef0d481327bda7304dcbfa773e989d4f364662ca3946ddca4799e7671 (0) |

## Repository and path checks

- HEAD: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Target revision match: true
- Current Git worktree clean: true
- All present report/draft/receipt/ledger paths are safe scanDir-relative regular files.
- No relevant symlink or symlink parent was observed.
- No report, receipt, ledger, or draft was changed by this audit update.

## Evidence sources

- `artifacts/05_findings/attack_path_analysis_report.md`
- `artifacts/05_findings/attack_path_decisions_A.json` through `attack_path_decisions_H.json`
- `/Users/ttokunaga-ja/.codex/sessions/2026/07/11/rollout-2026-07-11T21-36-51-019f512e-37a5-7a82-993d-b5bb2da12387.jsonl`
- `/Users/ttokunaga-ja/.codex/sessions/2026/07/10/rollout-2026-07-10T20-04-38-019f4bb3-6daf-7593-a078-c204f8ce1381.jsonl`
- `/Users/ttokunaga-ja/.local/share/opencode/log/opencode.log`
