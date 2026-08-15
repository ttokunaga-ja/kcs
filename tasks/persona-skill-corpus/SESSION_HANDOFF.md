# Cross-session handoff

At the end of every working interval, the parent chat collects every assigned
folder's scope-local status, inventory, and QA state, then rebuilds the one
persona-wide checkpoint. Mark unfinished folder work `blocked` or `generating`
with a concrete next action; do not infer completion from directory existence.
Reassign only folders with no active scope writer, and preserve all completed
files and evidence.

Replace `<PERSONA_ID>` and `<PERSONA_SLUG>` and copy/paste this prompt into the
future parent chat dedicated to that one persona:

```text
このリポジトリで `<PERSONA_ID>` / `<PERSONA_SLUG>` 1人分の高忠実度・完全合成
corpus production を担当してください。このチャットはこの1ペルソナだけを調整し、
別ペルソナの制作は行いません。
最初に tasks/persona-skill-corpus/README.md、COMMON_RULES.md、BATCH_PROTOCOL.md、
PERSONA_INDEX.md、PRODUCTION_LAYOUT.md、SESSION_HANDOFF.md と
tasks/persona-pc-eval-contract.md を読み、accepted Rust plan を唯一の
topology/ratio/path authority としてください。`kio-eval persona plan --profile ...
--out <absolute>` で作成・検証済みの artifact を親が渡すまで、topology を導出したり
filesystem を作成したりしてはいけません。production root は repository外の別途承認された
absolute v4 root とし、承認済みの retained filesystem boundary が accepted plan から skeleton を作成した後、
各persona直下の home 外 `_production` に status/inventory/provenance/narrative/qa metadata を置いてください。
新規rootの作成は `python3 -m eval.scaffold_persona_skill_corpus --plan <absolute-plan>
--root <absolute-v4-root>` だけを使い、既存のchecked-in skeletonをadoptしないでください。
まず `python3 -m eval.persona_skill_corpus_lease claim` で `<PERSONA_ID>` の親leaseをこのチャット固有の
session IDに対して取得してください。claimが一度だけ返すrelease_tokenは親チャット内だけに保持し、
production metadataやSubagent promptへ書かないでください。既存leaseは show で確認し、
persona-wide statusと全scope status/inventory/tempを点検してください。中断した親writerが停止済みであることを
ユーザーが確認した場合だけ、recover --expected-session ... --reason ... で回収記録を残してください。

次にこのペルソナの plan-defined leaf folder 20個について、既存inventoryと目標比率から
各フォルダで今回作る固定ファイル一覧（相対名、形式、artifact_id、日付・数値・用語アンカー）を先に決めてください。
Subagentをspawnし、1 Subagent assignmentにつき重複しないleaf folderをちょうど1つ割り当てます。
親チャットが各workerのspawn直前に、親leaseへ結合した `scope-claim --scope <exact-path>
--parent-session <parent-id> --worker-session <worker-id>` を取得し、scope tokenは親だけが保持します。
各workerは、割当 `home/<scope-path>/` と対応する
`_production/scopes/<scope-id>/assignment.json` の `files` に列挙されたdirect filenameだけを作ってください。
workerはassignment/manifest/WORKSPACE/leaseを変更せず、scope-local status/inventory/provenance/qaと
prompts/temp/renders/evidenceだけを更新します。同じleaf folderへ2 workerを割り当ててはいけません。
異なるleaf folderは並列制作して構いません。workerはpersona-wide status/narrative/manifest/aggregate JSONLや
別scopeを編集してはいけません。

各workerは必要な Documents/PDF/Spreadsheets/Presentations/ImageGen skill の SKILL.md を先に読み、
final artifact をrender/inspectして、scope-local QA evidenceへ保存します。text/code/dataは通常生成、
scan PDFはImageGen + PDF workflowを用います。完了または具体的blocked checkpointの後に親がscope-releaseし、
親チャットは全worker停止後にscope-local inventory/provenance/qaを検証・集約してpersona-wide statusを更新します。
実 PII/credential は一切使わず、cross-file narrative/numeric/date consistency と manifest/provenance を
維持してください。product-search QA は設計しないでください。各 persona の status.json を確認して
未完了の next_action から再開し、完了済み home file と evidence を上書き・削除しないでください。
最初の物理 milestone は persona ごと200件で、各形式の件数は比率×2です。1 turnで全件を作らず、
各leaf folder内の5〜20成果物batch単位で生成・visual QA・scope-local inventory/provenance/qa追記・status更新まで完結してください。
200件時点では family/variant 件数を accepted Rust plan と厳密に一致させてください。
この親チャットは1 persona、各Subagent assignmentはそのpersona内の1 leaf folderです。この二層境界を変更しないでください。
```
