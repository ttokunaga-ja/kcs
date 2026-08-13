# Cross-session handoff

At the end of every working interval, the coordinator collects each assigned
persona's `<pXX-role>/_production/status.json`, inventory, and QA state. Mark
unfinished work `blocked` or `generating` with a concrete next action; do not
infer completion from directory existence. Reassign only personas with no
active writer, and preserve all completed files and evidence.

Copy/paste this prompt into a future parent Codex session:

```text
このリポジトリで20 persona の高忠実度・完全合成 corpus production を再開してください。
最初に tasks/persona-skill-corpus/README.md、COMMON_RULES.md、BATCH_PROTOCOL.md、
PERSONA_INDEX.md、PRODUCTION_LAYOUT.md、SESSION_HANDOFF.md と
eval/persona_fixture_spec.py を読み、
fixture を唯一の topology/ratio/path authority としてください。production root は
repository-root/persona-corpus とし、python3 eval/scaffold_persona_skill_corpus.py
--root <production-root>（既存のowned rootは --resume）で全20人分 skeleton を作成し、
各persona直下の home 外 `_production` に status/inventory/provenance/narrative/qa metadata を置いてください。
次に subagent を spawn し、各 worker へ重複しない persona を割り当て、各workerは
eval/persona_skill_corpus_lease.py claim で固有session IDのleaseを取得してから作業してください。
claimが一度だけ返すrelease_tokenはactive parent session内だけに保持し、production metadataへ書かないでください。
既存leaseは show で確認し、status/inventory/tempを点検してください。中断したwriterが停止済みであることを
ユーザーが確認した場合だけ、recover --expected-session ... --reason ... で回収記録を残して再割当してください。
通常終了はclaimのrelease_tokenでreleaseします。同一 persona の同時 writer を禁止します。worker は必要な Documents/PDF/Spreadsheets/
Presentations/ImageGen skill の SKILL.md を先に読み、final artifact を render/inspect して QA evidence
を `<persona>/_production` に保存します。text/code/data は通常生成、scan PDF は ImageGen + PDF workflow を用います。
実 PII/credential は一切使わず、cross-file narrative/numeric/date consistency と manifest/provenance を
維持してください。product-search QA は設計しないでください。各 persona の status.json を確認して
未完了の next_action から再開し、完了済み home file と evidence を上書き・削除しないでください。
最初の物理 milestone は persona ごと200件で、各形式の件数は比率×2です。1 turnで全件を作らず、
5〜20成果物のbatch単位で生成・visual QA・inventory/provenance/qa追記・status更新まで完結してください。
200件時点では family比率だけでなく manifest.json の format_variant_counts_200 も厳密に満たしてください。
並列化はpersona単位に限定し、1 subagent/session = 1 complete persona folder `<persona>/`（home と _production）
だけを所有させてください。別persona同士は独立しているため衝突なく並列実行できますが、同じpersonaを複数agentへ分割しないでください。
```
