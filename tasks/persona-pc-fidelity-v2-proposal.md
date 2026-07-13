# 20人の独立persona-PC fidelity v2提案

Status: proposal only。未承認・未実装。現行`kcs-persona-pc-v1`を黙って変更せず、
採用時はfixture、renderer、plan、manifestをすべてv2へ上げる。

Date: 2026-07-14

## 1. 結論

評価単位は「20用途のフォルダを持つ1人」ではなく、次の20人である。

```text
formal-replay-01/
  devices/
    p01-software-engineer/       # 1人目の独立PC
      persona-manifest.json
      home/<20 active leaf scopes>
      .kcs-eval-device/          # この人だけのregistry
    p02-site-reliability-engineer/
      ...
    ...
    p20-investigative-journalist/
      ...
```

fullでは各人が単独で次を満たす。20人の合算値で代替しない。

- 20 active leaf scopesと1 isolated registry
- W0/W5の実KCS contract-contributor chunksが正確に120,000
- W5のcurrent+history contract chunksが180,000
- raw-only sourceの実chunkが0
- W0/W5 finalの全current eligible chunksが120,000以上135,000以下
- W5 finalの全current+history eligible chunksが180,000以上210,000以下

`planned chunks`は容量計画にだけ使い、合格証拠はinit/index後にKCSから読み戻した
distinct `(scope_key, chunk_id)`とする。

G0では各人のincidental-searchable sourceにもsource別上限を割り当てる。wave `w`のcheckpoint表を
`C(w), H(w)`とすると、人物合計上限は
`incidental_current_cap(w) = min(15,000, 135,000 - C(w))`、
`incidental_current_plus_history_cap(w) = min(30,000, 210,000 - C(w) - H(w))`とする。
W5 pre-purgeではそれぞれ10,200、20,400になる。W0-W5の各waveでactualを読み戻し、
contributorが正確でも動的eligible上限を超えたrootは失格とする。

## 2. 三つのlaneを分離する

| lane | 目的 | 120,000 chunk母数 | history | 容量分母 |
| --- | --- | --- | --- | --- |
| `formal-retrieval-history-v2` | 20人別の検索、履歴、latency | 含む | W0-W5を3 fresh-storage replay | 含む |
| `recursive-robustness-v1` | 深いambient tree、noise、Unicode、case/conflict、partial download | 含めない | 別manifest。必要な代表操作だけ | 含む |
| `byte-stress-v1` | 64-100 MiB級raw file、I/O、allocated blocks | 含めない | W0-only、1 replay | 含む |

正式scopeまでの親階層は深くしてよい。ただしKCSのdirect-file契約に合わせ、managed fileは
各leaf scopeの直下だけに置く。recursive ambientをformal rootへ混ぜると厳密なfile比、chunk母数、
verifierの意味が崩れるため、別root・別manifest・別receiptにする。

3 replayは同一seed・同一planをfresh storageへW0から再実行し、決定性、保存先分離、再開性を
証明する。これは統計的に独立な3標本や一般化性能の証明ではない。一般化は別content seed・別oracleの
追加suiteで扱う。

## 3. 20人のフォルダ構成

### 3.1 共通の形

各人は12個の職種固有primary scopeと8個の個人PC secondary scopeを持つ。現行v1の
共通secondary pathは廃止し、機能slotだけを揃えて物理pathを人物別にする。balancedな比較対照は
既存`scale_fixture_spec.py`が担うため、persona suiteでは20個のscope load vectorも人物別にする。

- primary合計は人物別に70-90%、secondary合計は10-30%
- 20 scopesすべてに正のfile数と正のcontributor quota
- 同じ20要素load vectorを別personaへ複製しない
- `planned_max_depth == realized_max_depth`を人物ごとに検証
- scope同士の重複、祖先・子孫関係、casefold衝突を禁止

### 3.2 人物別の代表構造

`D`は`home/`からleaf scopeまでのcomponent数である。表のpathは代表例で、採用時は各人の
12 primaryと8 secondaryをmachine-readable specへ完全列挙する。

| id | 1人として再現する属性 | proposed full files | primary / secondary load | formal Dmax | 代表primary scope | 代表secondary scope |
| --- | --- | ---: | ---: | ---: | --- | --- |
| p01 | software engineer | 12,000 | 85 / 15 | 4 | `work/products/product-alpha/architecture` | `desktop/current-patch` |
| p02 | SRE | 15,000 | 88 / 12 | 5 | `services/checkout/prod/oncall/operations` | `downloads/exports/log-batches` |
| p03 | security/GRC analyst | 10,000 | 80 / 20 | 4 | `compliance/frameworks/soc2/control-evidence` | `downloads/inbox/evidence-drops` |
| p04 | ML research engineer | 10,000 | 88 / 12 | 5 | `research/programs/model-alpha/experiments/results` | `desktop/current-experiment` |
| p05 | BI/data analyst | 12,000 | 82 / 18 | 4 | `analytics/governance/lineage/warehouse` | `downloads/inbox/source-extracts` |
| p06 | life-science researcher | 8,000 | 85 / 15 | 6 | `programs/study-alpha/2026/cohort-a/run-001/analysis` | `downloads/inbox/instrument-drops` |
| p07 | humanities researcher | 7,000 | 75 / 25 | 5 | `research/sources/archive-alpha/box-001/ocr-transcripts` | `desktop/current-chapter` |
| p08 | product manager | 8,000 | 75 / 25 | 5 | `portfolio/product-alpha/2026/q3/prds` | `cloud/team-shared/product-council` |
| p09 | UX researcher | 9,000 | 78 / 22 | 4 | `research/study-alpha/2026/transcripts` | `downloads/inbox/recorder-imports` |
| p10 | management consultant | 11,000 | 85 / 15 | 6 | `engagements/client-alpha/2026/phase-1/workstream-finance/deliverables` | `downloads/inbox/data-room` |
| p11 | account executive | 10,000 | 70 / 30 | 4 | `accounts/account-alpha/proposals` | `downloads/crm-exports` |
| p12 | support/success lead | 16,000 | 85 / 15 | 4 | `customers/customer-alpha/cases/case-history` | `desktop/active-queue` |
| p13 | corporate/privacy counsel | 7,000 | 82 / 18 | 5 | `matters/matter-alpha/legal-hold/collection-01/working` | `desktop/privileged-working` |
| p14 | finance controller | 13,000 | 88 / 12 | 5 | `finance/close/2026/q1/2026-03` | `desktop/current-close` |
| p15 | recruiter/people ops | 8,000 | 75 / 25 | 4 | `recruiting/requisition-alpha/interviews/round-2` | `downloads/ats-exports` |
| p16 | clinical researcher | 8,000 | 86 / 14 | 5 | `clinical/studies/study-alpha/2026/synthetic-cases` | `downloads/edc-exports` |
| p17 | construction PM | 8,000 | 90 / 10 | 6 | `portfolio/projects/project-alpha/2026/construction/drawings` | `downloads/cde-exports` |
| p18 | manufacturing quality engineer | 12,000 | 88 / 12 | 4 | `quality/nonconformance/2026/open` | `desktop/current-capa` |
| p19 | educator/instructional designer | 9,000 | 78 / 22 | 6 | `learning/courses/course-alpha/2026/term-1/lesson-plans` | `downloads/lms-exports` |
| p20 | investigative journalist | 10,000 | 85 / 15 | 5 | `newsroom/investigations/story-alpha/2026/fact-check` | `downloads/foia-exports` |

p10は7,000から11,000、p14は9,000から13,000 filesへ増やす。family比は維持したまま、
120,000 chunksをそれぞれ1,736件、1,719件の巨大contributorへ押し込む現行状態を解消するためである。
下記extension比まで適用したv2案のcontributorはp10が2,728 filesで平均44.0 chunks、
p14が2,464 filesで平均48.7 chunksになる。
全体は203,000 W0 files/replay、609,000 W0 files/3 replayとなる。W1-W5のsource/event exact件数は
joint allocator再実行後にG0で凍結する。

### 3.3 semantic filename

`source_id`は内部identityに残し、basenameは人物、scope、文書role、synthetic entity、期間、版を
表す。formal basenameはlowercase ASCII、120 bytes以下、scope内casefold uniqueとする。

| id | 例 |
| --- | --- |
| p01 | `adr-0042-auth-cache-rollback-v03.md` |
| p02 | `checkout-prod-incident-20260713-postmortem.md` |
| p03 | `soc2-cc6-1-control-evidence-index-v03.csv` |
| p04 | `model-alpha-exp-0042-analysis.ipynb` |
| p05 | `fy2026-q2-revenue-forecast-v04.xlsx` |
| p06 | `study-alpha-cohort-a-assay-results-run-001.csv` |
| p07 | `archive-alpha-box-001-item-0042-scan.pdf` |
| p08 | `product-alpha-search-prd-v12.docx` |
| p09 | `study-alpha-session-017-transcript-v03.txt` |
| p10 | `client-alpha-phase-1-market-sizing-v08.xlsx` |
| p11 | `account-alpha-mutual-action-plan-v04.docx` |
| p12 | `case-1042-escalation-timeline-v05.md` |
| p13 | `matter-alpha-legal-hold-notice-v03.docx` |
| p14 | `fy2026-q1-close-reconciliation-v03.xlsx` |
| p15 | `req-alpha-candidate-syn-017-scorecard-v02.docx` |
| p16 | `study-alpha-subject-syn-004-series-01.dcm` |
| p17 | `project-alpha-drawing-a101-rev-b.pdf` |
| p18 | `product-alpha-pfmea-rev-07.xlsx` |
| p19 | `course-alpha-week-04-lesson-plan-v02.docx` |
| p20 | `story-alpha-source-syn-017-interview-v03.txt` |

Unicode、空白、case collision、`final (1)`、conflicted copy、`.part`、Office lockfileは
recursive robustness laneへ置き、formal basename portabilityと混ぜない。

### 3.4 recursive ambientの代表例

次は`<robustness-root>/devices/<persona>/ambient-home/`以下に置く未登録treeである。
formal scope、120,000 chunks、Recall/latencyの母数へ入れないが、bytes、directory、inode、traversalは
robustness用capacity receiptへすべて計上する。

| id | 代表ambient path | 主に試す現象 |
| --- | --- | --- |
| p01 | `scratch/product-alpha/feature-auth/rebase-03/conflicts/files/` | merge copy、生成物、case違い |
| p02 | `incident-staging/inc-2026-0713/checkout/prod/pods/pod-004/logs/` | D7 log rotation、partial file |
| p03 | `evidence-staging/soc2/cc6-1/2026/request-042/raw/` | evidence duplicate、export途中 |
| p04 | `scratch/runs/model-alpha/exp-0042/seed-003/checkpoints/epoch-020/` | checkpoint/cache大量配置 |
| p05 | `staging/warehouse/20260713/sales/region-jp/part-0007/` | partition、duplicate CSV |
| p06 | `instrument-staging/mass-spec/run-001/vendor/raw/chunks/` | vendor container、partial transfer |
| p07 | `imports/archive-alpha/box-001/folder-07/item-003/derivatives/ocr/` | D8、Unicode原題、scan/OCR pair |
| p08 | `meeting-imports/teams/product-alpha/2026/q3/chat/attachments/` | sync conflict、Office lockfile |
| p09 | `recorder-staging/study-alpha/session-017/audio/raw/channels/` | media sidecar、partial WAV |
| p10 | `vdi-export/client-alpha/phase-1/workstream-finance/share/old/final/` | `final/final-2/copy`、locked Office |
| p11 | `outlook-cache/account-alpha/2026/07/thread-0042/attachments/` | attachment copy、Unicode/space |
| p12 | `ticket-cache/customer-alpha/case-1042/updates/2026/07/attachments/` | screenshot copy、`.part` |
| p13 | `legal-hold/matter-alpha/collection-01/custodian-syn-01/mail/attachments/` | deep hold、Unicode filename |
| p14 | `onedrive-sync/finance/close/fy2026/q1/2026-03/review/final/` | conflicted XLSX、final copy |
| p15 | `ats-cache/req-alpha/candidate-syn-017/interviews/round-2/panel/` | repeated scorecard |
| p16 | `secure-smb/study-alpha/site-03/subject-syn-004/visit-02/imaging/series-01/` | DICOM series、many siblings |
| p17 | `cde-cache/project-alpha/shared/wip/architecture/models/rev-b/` | IFCZIP revision、offline cache |
| p18 | `plm-cache/product-alpha/changes/eco-0042/attachments/supplier-alpha/certificates/` | `.tmp`、obsolete copy |
| p19 | `drive-sync/course-alpha/2026/term-1/week-04/student-work-synthetic/team-07/final/` | duplicate submission、space |
| p20 | `source-drop/story-alpha/source-syn-017/device-export/messages/attachments/2026-07/` | HEIC `.part`、evidence chain |

case-insensitive filesystemで同居できないcollision pairは、POSIX native realizationまたは
manifest-only expected failureとして記録し、作れなかったfixtureを作成済みと見なさない。

初期robustness profileは各人256 ambient file candidates、128 directories、最大深度D6-D8とする。
file candidate比はbenign nested document 40%、exact/near/conflict copy 15%、cache/temp 15%、
partial download 10%、hidden/lockfile 10%、empty file 5%、Unicode/case-collision candidate 5%とする。
各entryは`registered_scope=false`、`formal_gate_eligible=false`、formal leafとの交差なし、`.kcs`なしを
持つ。candidate数とnative realized数を別々に記録し、宣言外entryをverifierが拒否する。

## 4. 物理file family比

分母は人物ごとのW0 physical filesであり、extension比、byte比、logical member比、chunk比ではない。
以下は実利用統計ではなく、検索・変換・raw-only境界を広く踏むためのstress-design仮説である。
p10/p14のfile数を増やしても百分率は維持する。

| persona | md | txt/log | code | structured | csv/tsv | html/eml | ipynb | text PDF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| p01 | 22 | 8 | 28 | 12 | 3 | 5 | 1 | 7 |
| p02 | 20 | 22 | 15 | 20 | 5 | 3 | 0 | 4 |
| p03 | 10 | 12 | 8 | 15 | 10 | 8 | 0 | 15 |
| p04 | 12 | 7 | 18 | 10 | 12 | 2 | 12 | 12 |
| p05 | 8 | 5 | 6 | 14 | 20 | 5 | 5 | 5 |
| p06 | 6 | 6 | 3 | 5 | 15 | 2 | 3 | 18 |
| p07 | 12 | 10 | 0 | 4 | 3 | 5 | 0 | 25 |
| p08 | 10 | 4 | 1 | 5 | 8 | 8 | 0 | 13 |
| p09 | 8 | 15 | 0 | 4 | 8 | 3 | 0 | 10 |
| p10 | 4 | 4 | 0 | 2 | 8 | 6 | 0 | 18 |
| p11 | 3 | 4 | 0 | 2 | 5 | 25 | 0 | 16 |
| p12 | 15 | 20 | 4 | 15 | 12 | 12 | 0 | 5 |
| p13 | 3 | 4 | 0 | 1 | 2 | 14 | 0 | 28 |
| p14 | 3 | 3 | 1 | 4 | 15 | 5 | 0 | 13 |
| p15 | 4 | 5 | 0 | 2 | 7 | 15 | 0 | 20 |
| p16 | 5 | 6 | 1 | 4 | 10 | 4 | 1 | 24 |
| p17 | 3 | 4 | 0 | 2 | 5 | 4 | 0 | 20 |
| p18 | 6 | 12 | 2 | 6 | 15 | 3 | 0 | 18 |
| p19 | 8 | 5 | 0 | 2 | 5 | 5 | 0 | 20 |
| p20 | 8 | 18 | 1 | 3 | 8 | 10 | 0 | 16 |

| persona | scan PDF | docx | xlsx | pptx | image | media | domain binary |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| p01 | 1 | 3 | 2 | 2 | 3 | 0 | 3 |
| p02 | 0 | 2 | 1 | 1 | 2 | 0 | 5 |
| p03 | 5 | 5 | 4 | 2 | 3 | 0 | 3 |
| p04 | 1 | 2 | 3 | 3 | 5 | 0 | 1 |
| p05 | 1 | 3 | 15 | 4 | 3 | 0 | 6 |
| p06 | 8 | 8 | 8 | 5 | 9 | 0 | 4 |
| p07 | 20 | 10 | 1 | 2 | 6 | 1 | 1 |
| p08 | 3 | 15 | 8 | 15 | 7 | 1 | 2 |
| p09 | 4 | 12 | 4 | 8 | 15 | 7 | 2 |
| p10 | 5 | 12 | 18 | 18 | 3 | 0 | 2 |
| p11 | 4 | 14 | 7 | 10 | 5 | 3 | 2 |
| p12 | 1 | 3 | 2 | 1 | 7 | 1 | 2 |
| p13 | 15 | 22 | 3 | 2 | 3 | 0 | 3 |
| p14 | 8 | 8 | 27 | 7 | 3 | 0 | 3 |
| p15 | 8 | 20 | 8 | 3 | 5 | 1 | 2 |
| p16 | 12 | 10 | 8 | 5 | 6 | 1 | 3 |
| p17 | 12 | 8 | 10 | 4 | 12 | 1 | 15 |
| p18 | 6 | 8 | 10 | 3 | 5 | 0 | 6 |
| p19 | 8 | 15 | 7 | 12 | 8 | 3 | 2 |
| p20 | 10 | 8 | 2 | 2 | 8 | 4 | 2 |

v2の203,000 filesへ適用したsuite集計は次である。

| family | files | 比 | family | files | 比 |
| --- | ---: | ---: | --- | ---: | ---: |
| md | 18,580 | 9.15% | txt/log | 19,210 | 9.46% |
| code | 10,440 | 5.14% | structured | 15,310 | 7.54% |
| csv/tsv | 18,680 | 9.20% | html/eml | 14,430 | 7.11% |
| ipynb | 2,240 | 1.10% | text PDF | 28,580 | 14.08% |
| scan PDF | 11,680 | 5.75% | docx | 17,270 | 8.51% |
| xlsx | 15,430 | 7.60% | pptx | 10,620 | 5.23% |
| image | 11,380 | 5.61% | media | 2,150 | 1.06% |
| domain binary | 7,000 | 3.45% | total | 203,000 | 100.00% |

表示比の合計は小数第2位丸めにより99.99%になるが、正本は上のexact file countsであり、
203,000を分母にした丸め前合計は100%である。

## 5. family内extension/variant比

`ipynb`、text/scan PDF、DOCX、XLSX、PPTXは各family内で対応拡張子100%とする。
text PDFとscan PDFは同じ`.pdf`を内部構造で区別する。

人物別extension profileは少なくとも次を持つ。

- Markdown: `.md/.markdown`を人物別に60/40から90/10
- txt/log: `.txt/.log/.jsonl`を物語中心75/10/15、業務中心70/15/15、
  operations中心25/55/20などへ分ける
- code: KCSがlocal textとして認識する`.py/.rs/.ts/.go/.js/.java/.c/.cpp`から
  職種別に3種類以内を選ぶ
- structured: `.json/.yaml/.xml/.sql`をengineering、data/finance、documentの3 profileで変える
- delimited: `.csv/.tsv`を人物別60/40から85/15
- mail/web: `.html/.eml`を人物別20/80から80/20
- image: valid `.png/.jpg/.tif/.bmp`を人物別に配分
- media: valid `.wav/.aiff/.mid`を該当personaだけに配分

初期exact比は次とする。各セルはその人物の該当family内百分率で、`-`はfamily自体が0%である。

| id | md / markdown | txt / log / jsonl | code variants | json / yaml / xml / sql | csv / tsv | html / eml | png / jpg / tif / bmp | wav / aiff / mid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p01 | 85/15 | 45/35/20 | py/rs/ts 25/40/35 | 45/35/5/15 | 75/25 | 80/20 | 60/25/10/5 | - |
| p02 | 90/10 | 25/55/20 | py/go/ts 60/30/10 | 30/50/5/15 | 70/30 | 50/50 | 70/15/10/5 | - |
| p03 | 80/20 | 40/35/25 | py/go/ts 70/20/10 | 45/20/25/10 | 60/40 | 40/60 | 45/15/35/5 | - |
| p04 | 80/20 | 50/20/30 | py/cpp/go 85/10/5 | 55/20/5/20 | 80/20 | 80/20 | 60/20/15/5 | - |
| p05 | 75/25 | 55/20/25 | py/js/ts 65/5/30 | 30/10/10/50 | 80/20 | 65/35 | 70/20/5/5 | - |
| p06 | 70/30 | 55/20/25 | py/cpp/ts 85/10/5 | 35/15/35/15 | 65/35 | 70/30 | 35/20/40/5 | - |
| p07 | 60/40 | 75/10/15 | - | 30/10/50/10 | 60/40 | 35/65 | 25/20/50/5 | 60/40/0 |
| p08 | 70/30 | 60/15/25 | py/js/ts 60/10/30 | 50/20/5/25 | 75/25 | 45/55 | 55/35/5/5 | 70/30/0 |
| p09 | 65/35 | 70/15/15 | - | 45/20/25/10 | 65/35 | 35/65 | 35/50/10/5 | 70/30/0 |
| p10 | 70/30 | 70/10/20 | - | 35/10/15/40 | 75/25 | 35/65 | 50/35/10/5 | - |
| p11 | 70/30 | 70/15/15 | - | 55/10/15/20 | 80/20 | 20/80 | 45/45/5/5 | 70/30/0 |
| p12 | 90/10 | 35/45/20 | py/js/ts 70/10/20 | 50/30/5/15 | 75/25 | 35/65 | 60/30/5/5 | 80/20/0 |
| p13 | 65/35 | 75/10/15 | - | 30/10/45/15 | 60/40 | 25/75 | 30/20/45/5 | - |
| p14 | 70/30 | 65/15/20 | py/js/ts 70/10/20 | 25/10/20/45 | 85/15 | 40/60 | 55/25/15/5 | - |
| p15 | 70/30 | 70/15/15 | - | 45/10/30/15 | 70/30 | 30/70 | 40/45/10/5 | 70/30/0 |
| p16 | 70/30 | 70/10/20 | py/cpp/ts 80/10/10 | 30/10/50/10 | 70/30 | 35/65 | 25/15/55/5 | 80/20/0 |
| p17 | 65/35 | 60/20/20 | - | 25/15/45/15 | 60/40 | 35/65 | 35/45/15/5 | 80/20/0 |
| p18 | 75/25 | 45/35/20 | py/cpp/rs 70/20/10 | 30/15/35/20 | 65/35 | 45/55 | 35/30/30/5 | - |
| p19 | 70/30 | 70/10/20 | - | 40/15/35/10 | 70/30 | 40/60 | 45/35/15/5 | 55/20/25 |
| p20 | 70/30 | 65/20/15 | py/js/ts 80/10/10 | 50/15/25/10 | 70/30 | 25/75 | 35/50/10/5 | 75/25/0 |

採用時はこの20人×family比を`extension_profile_id`としてspecへ格納し、largest remainderで
exact整数へ割り当てる。単に拡張子だけを付け替えたbytesは禁止する。

### 5.1 role別domain binary

すべてraw-only、expected contributor chunksは0である。SQLiteはruntime/version/compile optionsを
完全に束縛できるまでformal coreから外し、warehouse/ERP/QMS exportはcanonical ZIP/GZIP/USTARで
再現する。

| id | domain binary family内比 |
| --- | --- |
| p01 | canonical source-export ZIP 70 / USTAR 30 |
| p02 | PCAP 70 / canonical JSONL.GZ 30 |
| p03 | PCAP 40 / evidence ZIP 60 |
| p04 | valid NPZ 70 / model-metadata ZIP 30 |
| p05 | warehouse ZIP 60 / CSV.GZ 40 |
| p06 | instrument-export ZIP 70 / assay CSV.GZ 30 |
| p07 | TIFF-containing USTAR 60 / archive ZIP 40 |
| p08 | product-export ZIP 70 / team-export USTAR 30 |
| p09 | recording-project ZIP 70 / session USTAR 30 |
| p10 | data-room ZIP 80 / exported-snapshot USTAR 20 |
| p11 | CRM ZIP 60 / Maildir USTAR 40 |
| p12 | ticket ZIP 70 / CRM JSONL.GZ 30 |
| p13 | DMS ZIP 70 / legal-hold USTAR 30 |
| p14 | ERP CSV.GZ 60 / close-package ZIP 40 |
| p15 | ATS ZIP 60 / HRIS JSONL.GZ 40 |
| p16 | synthetic DICOM Part-10 70 / EDC ZIP 30 |
| p17 | IFCZIP 70 / CDE ZIP 30 |
| p18 | QMS ZIP 60 / PLM USTAR 40 |
| p19 | course-package ZIP 70 / LMS USTAR 30 |
| p20 | FOIA ZIP 70 / synthetic source-drop USTAR 30 |

variantごとに検査項目を分ける。

| variant | 決定論・validity gate |
| --- | --- |
| ZIP / IFCZIP | `ZIP_STORED`、固定entry順・epoch・permission・extra field、CRC、bounded member path、展開後byte上限。IFCZIPは1個の妥当なISO-10303-21 SPFを持つ |
| USTAR | header、checksum、uid/gid、mtime、padding、member順、bounded member path |
| GZIP | mtime 0、OS 255、DEFLATE stored block、CRC32、ISIZE、展開後byte上限 |
| NPZ | ZIP gateに加え、内部`.npy`のmagic、header、shape、dtype、payload長 |
| PCAP | magic、endianness、version 2.4、snaplen、record timestamp/length bounds、packet checksum |
| DICOM | Part-10 preamble/meta、transfer syntax、explicit-VR length、digest由来UID、synthetic identifier、pixel bounds |

plain IFCはprintable textとしてsniffされ得るためraw-onlyには使わない。すべて独立validatorで
再読込し、拡張子、media type、magic、gate roleの不一致をfail closedにする。

## 6. chunk quotaとphysical sizeを分離する

現行fullの実quota分布は`1-4: 0% / 5-20: 31.39% / 21-50: 48.79% /
51-72: 19.82%`で、仮説の55/30/12/3とは一致しない。p08、p10、p11、p14、p15、p17は
全contributorが51 chunks以上になる。v2はpersona、family、scope、quota bucketを同時に解く。

| density class | personas | 1-4 | 5-20 | 21-50 | 51-70 |
| --- | --- | ---: | ---: | ---: | ---: |
| low | p01, p02 | 30% | 50% | 20% | 0% |
| medium | p03, p04, p07, p12, p18, p20 | 10% | 30% | 45% | 15% |
| high | p05, p06, p09, p10, p13, p14, p16, p19 | 3% | 12% | 45% | 40% |
| dense-office | p08, p11, p15, p17 | 1% | 4% | 20% | 75% |

分母はfamily/extension allocation後のcontract-contributor sourcesだけであり、全physical filesではない。
bucket件数をlargest remainderで固定した後、joint solverが各sourceへ1-70を割り当て、人物合計を
正確に120,000へ合わせる。p95とv2 hard maxはともに70以下とする。外側の既存安全上限72は
非回帰guardとしてだけ残す。解がない比率はfile数、family比、
またはbucket比をG0で明示的に変更し、quotaだけを隠れて歪めない。

上のexact extension比とproposed full file数を使ったpersona-global interval probeでは20人すべてで
120,000がbucket最小・最大の間に入る。最も余裕が小さいp07でも最大122,718である。ただしscope別の
正quota、route、family marginalsを同時に満たす証明ではないため、G0のjoint solver成功までは未凍結とする。

PDF pages、Office member数、attachment数、raw bytesはchunk quotaとは別fieldにする。

| 対象 | formal retrieval/history | byte-stress |
| --- | --- | --- |
| text PDF | 1-72 pages、actual chunksを別attest | 201+ pages可 |
| scan PDF | 1-50 pages | 51-500 pages |
| EML | 0-5 attachments | 6-50 attachments |
| XLSX | 1-20 sheets、bounded rows/cells | 21-100 sheets |
| PPTX | 1-40 slides | 41-200 slides |
| image/media/domain | ordinary rawを4 KiB-512 KiB、tailは最大16 files/person・1-4 MiB | 128 KiB-100 MiB |

formal W0 source treeの提案上限は512 MiB/personかつ10 GiB/replayである。W5 finalは
1.25 GiB/personかつ25 GiB/replay、pre-purge peakは1.35 GiB/personかつ27 GiB/replayを
上限候補にする。各person上限と20人合計上限を同時に満たさなければならない。
3 rootsを保持するformal suite、plan/ledger/tempを含む提案hard capは88 GiBとする。ただし、これは
completed root 25+25 GiB、進行中rootのpre-purge 27 GiB、plan/ledger/temp/supervisor 11 GiBの
合計上限である。pilot実測前の承認ではない。raw、CAS、SQLite/FTS/WAL、history、staging、inodeをpilotで測り、
root-bound capacity receiptが上限内と証明するまでfull writeはblockedのままにする。

byte-stressは1 replay、W0-only、20人×64 raw-only filesとする。1人あたりsmall 32×128 KiB、
medium 16×2 MiB、large 12×32 MiB、tail 4×80 MiBでpayload 740 MiB、receipt余裕込み
768 MiB/person、20人で15 GiBを上限候補にする。

容量判定は`st_blocks`相当のallocated bytesを使い、hard link、clone、sparse、filesystem compressionで
見かけだけの容量を作ることを禁止する。

## 7. personaらしさをbytesへ束縛するsource recipe

planはpersona fidelity、fact/entity、template、variant、size、permission profileを共有辞書へ正規化し、
source rowには短い参照IDとsource固有値だけを持たせる。すべての共有辞書は推移的にcanonical plan hashへ
含め、参照先のないID、未参照entry、重複IDを拒否する。v2 persona planは16 MiB/personをhard cap候補とし、
G0で20人すべての実serialization sizeを測ってresource oracleとテストを更新する。

共有persona fidelity profileはOS/case semantics、device class、locale、timezone、languages、work cadence、
retention、sync snapshot source、sensitivity、permission、mtime-age、duplicate/conflict仮説を持つ。
各source rowは少なくとも次をcanonical plan hashへ含める。

```text
fidelity_profile_id / fidelity_profile_sha256
persona_id / scope_key / source_id / materialization_id
project_or_case_id / synthetic_entity_ids / fact_ids
filename_template_id / content_template_id / document_role
language / topic / period / status / version
family / variant / media_type / validator_id
quota_bucket / requested_contributor_chunks
expected_incidental_chunks_upper / expected_disposition
complexity_unit / target_complexity / target_bytes
sensitivity_tier / permission_profile_id / mtime_age_bucket
duplicate_or_conflict_group
renderer_id / renderer_schema_version / deterministic_payload_seed
```

人物ごとに3-5個のproject/case fact graphとgold oracleを先に凍結し、メール、PDF、表、メモが同じsynthetic factを
異なる言い回しで参照する。本文にpersona ID、source ID、digest、fixture nonceを露出させず、
同じ語彙を持つdecoyと旧revisionを生成する。日本語・英語などはpersona profileに従う。

synthetic entityは`.invalid` email、RFC 5737 documentation IP、`*-syn-NNN`識別子だけを使う。
hostのHOME、USER、hostname、環境credential、実PII/PHI、network/live syncを入力にしない。

## 8. 作成、編集、複数再現、検証の順序

| Gate | 実装・実行 | 合格条件 | 現在地 |
| --- | --- | --- | --- |
| G0 v2契約凍結 | 400 exact scope paths/load、family/extension/variant整数比、ambient spec、共有辞書、source recipe、size、fact/oracle、W0-W5 exact eventを1つのmachine-readable specへhash固定 | generator変更前に全20人でcanonical rebuild。joint solverがfull contributor=120,000とpilot=12,000、scope routing、wave別incidental上限、plan 16 MiB上限をexactに解く | 未実装 |
| G1 v2 tiny W0 | 20人×200 files/rootを1人・1sourceずつstreaming作成 | 4,000 files/root、2 roots合計8,000 writes、400 scopes/root、比率/path/hash/readback、inode非共有 | v1相当は済。v2回帰が必要 |
| G2 pilot W0 | fullの10% stratified sample、計20,300 files、各人12,000 planned、init→offline index | 各人actual contributor 12,000、raw-only 0、planned/actualを別台帳化 | streaming writerと完全attestorが未実装 |
| G3 pilot W1-W5 | immutable eventをmutation前に検証し、edit/rename/move/duplicate/derive/archive/delete/restore/purge | exactly-once journal、再開収束、waveごとのactual attestation、purge後index noop | allocator/manifestのみ済 |
| G4 full Go/No-Go | pilotのbytes/inodes/RSS/history amplificationを読み戻す | 3 roots+staging+reserveがroot-bound capacity内。不足ならwrite前に停止 | evidence待ち |
| G5 full replay×3 | 同一plan/eventから3 fresh rootsをそれぞれW0からW5まで実行 | `.kcs`/完成rootコピーなし、hard link/cloneなし、60 registries、1,200 scopes | 未実装 |
| G6 reproducibility/resume | root依存値を除くcanonical stateとquery rankを比較、failure injection後resume | event exactly-once、同一seedのstate/count/history/query projection一致 | 未実装 |
| G7 actual attestation | DB/CAS/HEAD/historyを全persona・全replay・全waveで実読 | 各waveのC/Hがcheckpoint表とexact一致。current eligibleは`C(w)..135,000`、current+history eligibleは`C(w)+H(w)..210,000`かつ動的incidental cap内、raw-only=0 | 未実装 |
| G8 evaluation | 各人・各scenario最低30問、合計1,800 unique queries | per-person Recall@10 >=0.8、M3-1 p95<5s、M3-2/M3-3 p95<7s。同一seed再現性に限定して報告 | 未実施 |

W0でindexして履歴境界を作ってから編集する。編集後に初めてindexするとW0が履歴に存在しないため、
順序を入れ替えない。3 replayは完成rootを複製せず、同じimmutable plan/eventを入力にW0から別々に作る。
pilot file数は各人のproposed full filesの10分の1、すなわち700-1,600 files/personで、suite合計20,300とする。
これによりfamily/extension比とcontributor密度をfullからstratified sampleできる。

full contract checkpointは各人・各replayで次とする。

| checkpoint | current C | history-only H |
| --- | ---: | ---: |
| W0 | 120,000 | 0 |
| W1 | 120,000 | 24,000 |
| W2 | 120,000 | 24,000 |
| W3 | 120,000 | 48,000 |
| W4 | 120,000 | 60,000 |
| W5 pre-purge | 124,800 | 64,800 |
| W5 final | 120,000 | 60,000 |

small editは90%以上のsemantic sectionsを保持し、指定factだけを変える。major editは別bucketにする。
rename/moveはbytes不変、delete/restoreはsource/version/rawを保持、purge後は旧queryが0件になることを
diff receiptとquery oracleで証明する。大量purge throughputは通常履歴とは別reportも出す。

queryにpersona/source ID、path、digest、section slug、生成nonceを含めない。各positive queryは同語彙の
distractorを3件以上持ち、current、old wording、rename/move、deleted、restored、多言語を
別stratumとしてper-person判定する。最低30問/persona/scenario、合計1,800はpositive queryだけで数える。
purged-negativeはRecall母数へ混ぜず、別に最低5問/persona/scenarioを置き、`false-positive@10 == 0`を
要求する。corpus template/seedとquery template/seedを分離し、
gold oracleをsource rendering前に凍結する。queryとanswer文書のrare token、特徴的n-gram、renderer内部語彙の
重複率をgateし、template exact lookupを拒否する。pooled平均だけで合格させず、同一seedの3 replay結果から
20人一般への統計的一般化を主張しない。

## 9. 容量判断

2026-07-14時点の内蔵APFS空きは約143.83 GiBである。現行v1の35/40/20/5 binary byte仮説を
20,090 filesへそのまま適用すると、binaryだけで最低約80.4 GiB/replay、約241.3 GiB/3 replayとなる。
v2のimage+media+domainは20,530 filesなので、同じ旧envelopeなら最低約82.2 GiB/replay、
約246.6 GiB/3 replayとなる。どちらもOffice、PDF、CAS、index、history、staging前に不足するため、
旧size envelopeのfullはNo-Goである。

内蔵volumeで最初に許可する候補は20人全員・1 replayのpilotだけとする。

```text
byte_cap                  = 32 GiB
reserve_bytes             = 96 GiB
inode_cap                 = 250,000
explicit_free_inodes      = 1,000,000
reserve_inodes            = 750,000
concurrent_persona_worker = 1
```

formal fullの88 GiB候補とbyte-stress 15 GiB候補はpilot receipt後に再裁定する。現在のvolumeで理論上
103 GiBに収まっても、40 GiB程度しかreserveが残らないため、自動的にGoにしない。正式実行環境は
初期運用案として512 GiB以上の空きを持つ専用volumeを推奨し、最終必要量はpilotのallocated blocks、
CAS/index/history amplification、W5 transient peak、25% headroomから決める。

planner/renderer/writerは全person/bytesを同時保持せず、1 persona・1 sourceずつ処理する。
既存のplanning上限はworker RSS 384 MiB、composer 128 MiB、process tree 512 MiB、worker同時1である。
KCS index用RSS上限はpilotで別に実測・凍結する。

## 10. 現在の進捗とv2実装境界

現行v1で実装済み:

- 20人、400 scopes、15 familyのmachine-readable matrix
- deterministic format×scope allocatorと1-72 planned quota
- tiny W0 4,000 filesのwriter、3 ledgers、manifest、2 fresh root検証
- W1-W5 contributor/structural allocatorとroot-independent event manifest
- bounded persona planning、capacity/runner/storage/prepare receiptのfail-closed境界
- final HEADのM3-1/M3-2/M3-3 CI green

v2で残るもの:

- 人物別secondary pathsとscope load、深度、semantic filename、fact graph
- persona-specific extension/domain variantとvalid renderer
- chunk/complexity/bytesを分離したjoint source recipe
- 1 persona・1 source streaming W0 writerとpilot/full write gate
- W0 init/index complete attestor、W1-W5 journal/executor
- 3 fresh-storage replay、actual chunk/history attestation、1,800 query evaluation

この提案が採用されるまでは、現行`SCHEMA_VERSION=1`、`FIXTURE_ID=kcs-persona-pc-v1`、
canonical plan SHAを変更しない。採用後の最初の実装単位はG0のschema v2とsource recipeであり、
rendererやfull writerだけを先行させない。

Q_hardでのSpotlight/ripgrep-all比較、D1のTTFV/AI強化時間/コスト、実フォルダdogfoodは、
このsynthetic persona suiteで代替しない。
