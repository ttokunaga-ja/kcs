# Persona-PC v2 core mix補足提案

Status: proposal only。G0、writer、filesystem、Kio、history、evaluation authorityを与えない。

Date: 2026-07-17

## 1. 結論

20人は20個の独立したpersona-PC rootとして作る。1台のPCに20用途を同居させない。
各rootは12 primary + 8 persona-specific secondary leaf scopes、W0で120,000 current
contract chunks、W5 finalで120,000 current + 60,000 history-only contract chunksを持つ。

物理file比は二つのprofileへ分離する。

- `persona-core-v1`: 人物の主用途とPCらしさを優先する。dominant 3--5 familiesを70--85%、
  supporting 4--5 families、rare familyはexact file数、1--3 familiesは0件にする。
- `benchmark_stress_mix_v2`: 既存canonical profile IDと20 x 15 exact matrixを維持し、
  `format coverage stress`の表示名で71 variants、変換待ち、raw-only、parser境界を広く踏む。

両profileは同じphysical-file分母へ混ぜず、別profile ID、別manifest、別fresh replayとする。
採用Decisionとcore専用problem/solution/proofが凍結された場合に限り、MVP fullの基本候補を
`persona-core-v1`、既存matrixをformat coverage gate専用候補とする。それまでは
`benchmark_stress_mix_v2`が現行正本であり、この補足から置換を推論しない。
どちらも実在PCの観測統計ではなく、version/hash付きのauthored hypothesisである。

## 2. device rootとlane

```text
<profile>-replay-01/
  devices/
    p01-software-engineer/
      persona-manifest.json
      lane-manifests/
      home/                 # formal D2--D6、20 registered leaf scopes
      ambient-home/         # D6--D8、未登録recursive robustness
      byte-stress/          # designated replayだけ、raw-only
      .kio-eval-device/     # persona/replay固有registry
      receipts/
    ...
    p20-investigative-journalist/
```

formal managed filesはleaf scope直下だけに置く。したがってformal laneが測るのは深い親pathを持つ
wide-leaf型の検索・履歴であり、100,000 chunksをrecursive traversalで取り込む性能ではない。
中間directoryにもfileを置くrecursive traversal、Unicode/case collision、cache/temp、partial、
conflict copyは`ambient-home`で別評価する。lane間でfile、payload materialization、inode、hard link、
clone、symlinkを共有しない。

### 2.1 人物別folder topology候補

formal `home/`は既存canonical topologyの400 leaf scopesを維持する。各人物は12 primary + 8 secondaryを
持ち、secondaryのfunctional slotは`desktop-active`、`documents-reference`、`downloads-inbox`、
`downloads-exports`、`cloud-personal`、`cloud-team`、`mail-recent`、`archive-closed`で共通だが、物理pathは
人物別である。次表のprimary areaは親containerでありscope数ではない。各行の配下には12本のprimary leafが
ある。formal例は既存canonical path、ambient例は未承認のrecursive robustness候補である。

| persona | primary top-level areas | formal例 / realized Dmax | `ambient-home`の複雑系候補 |
| --- | --- | --- | --- |
| p01 software engineer | `work`, `repos`, `work-items`, `meetings`, `vendor-docs`, `operations` | `work/products/product-alpha/architecture` / D4 | `scratch/product-alpha/feature-auth/rebase-03/conflicts/files`、merge copy、generated output、case差 |
| p02 SRE | `documents`, `infrastructure`, `services`, `observability`, `changes`, `capacity`, `meetings` | `services/checkout/prod/oncall/operations` / D5 | `incident-staging/inc-2026-0713/checkout/prod/pods/pod-004/logs`、rotation、partial |
| p03 security/GRC | `security`, `compliance`, `third-party`, `soc`, `privacy`, `meetings` | `compliance/frameworks/soc2/control-evidence` / D4 | `evidence-staging/soc2/cc6-1/2026/request-042/raw`、duplicate、未完export |
| p04 ML researcher | `research`, `notebooks`, `datasets`, `models`, `evaluations`, `presentations`, `repos` | `research/programs/model-alpha/experiments/configs` / D5 | `scratch/runs/model-alpha/exp-0042/seed-003/checkpoints/epoch-020`、checkpoint/cache fan-out |
| p05 BI/data analyst | `analytics`, `dashboards`, `reports`, `forecasts`, `requests`, `exports`, `meetings` | `analytics/governance/lineage/warehouse` / D4 | `staging/warehouse/20260713/sales/region-jp/part-0007`、partition、duplicate CSV |
| p06 life-science researcher | `lab`, `programs`, `instruments`, `samples`, `literature`, `grants`, `manuscripts`, `meetings` | `programs/study-alpha/2026/cohort-a/run-001/raw-exports` / D6 | `instrument-staging/mass-spec/run-001/vendor/raw/chunks`、vendor container、partial transfer |
| p07 humanities researcher | `research`, `notes`, `dissertation`, `translations`, `conferences`, `correspondence` | `research/sources/archive-alpha/box-001/ocr-transcripts` / D5 | `imports/archive-alpha/box-001/folder-07/item-003/derivatives/ocr`、Unicode原題、scan/OCR pair |
| p08 product manager | `portfolio`, `roadmap`, `customer-feedback`, `analytics`, `decisions`, `research` | `portfolio/product-alpha/2026/q3/prds` / D5 | `meeting-imports/teams/product-alpha/2026/q3/chat/attachments`、sync conflict、Office lockfile |
| p09 UX researcher | `research`, `surveys`, `design`, `personas`, `recordings`, `consent` | `research/study-alpha/2026/transcripts` / D4 | `recorder-staging/study-alpha/session-017/audio/raw/channels`、media sidecar、partial WAV |
| p10 consultant | `engagements`, `proposals`, `benchmarks`, `templates`, `meetings` | `engagements/client-alpha/2026/phase-1/workstream-finance/data-room` / D6 | `vdi-export/client-alpha/phase-1/workstream-finance/share/old/final`、final copy、locked Office |
| p11 account executive | `accounts`, `sales`, `travel` | `accounts/account-alpha/proposals` / D4 | `outlook-cache/account-alpha/2026/07/thread-0042/attachments`、attachment copy、Unicode/space |
| p12 support/success lead | `support`, `knowledge-base`, `customers` | `customers/customer-alpha/cases/case-history` / D4 | `ticket-cache/customer-alpha/case-1042/updates/2026/07/attachments`、screenshot copy、`.part` |
| p13 corporate/privacy counsel | `matters`, `legal` | `matters/matter-alpha/legal-hold/collection-01/working` / D5 | `legal-hold/matter-alpha/collection-01/custodian-syn-01/mail/attachments`、deep hold、Unicode |
| p14 finance controller | `finance` | `finance/close/2026/q1/2026-01` / D5 | `onedrive-sync/finance/close/fy2026/q1/2026-03/review/final`、conflicted XLSX、final copy |
| p15 recruiter/people ops | `recruiting`, `people`, `learning`, `compensation`, `compliance` | `recruiting/requisition-alpha/interviews/round-2` / D4 | `ats-cache/req-alpha/candidate-syn-017/interviews/round-2/panel`、repeated scorecard |
| p16 clinical researcher | `clinical`, `guidelines`, `literature`, `regulatory`, `safety`, `statistics`, `presentations` | `clinical/studies/study-alpha/2026/protocols` / D5 | `secure-smb/study-alpha/site-03/subject-syn-004/visit-02/imaging/series-01`、DICOM many-siblings |
| p17 construction PM | `portfolio`, `bim`, `meetings` | `portfolio/projects/project-alpha/2026/construction/drawings` / D6 | `cde-cache/project-alpha/shared/wip/architecture/models/rev-b`、IFCZIP revision、offline cache |
| p18 manufacturing quality | `products`, `quality`, `suppliers`, `engineering` | `quality/nonconformance/2026/open` / D4 | `plm-cache/product-alpha/changes/eco-0042/attachments/supplier-alpha/certificates`、`.tmp`、obsolete copy |
| p19 educator | `learning`, `assessments`, `lms`, `presentations`, `professional-development` | `learning/courses/course-alpha/2026/term-1/lesson-plans` / D6 | `drive-sync/course-alpha/2026/term-1/week-04/student-work-synthetic/team-07/final`、duplicate submission、space |
| p20 journalist | `newsroom`, `data`, `media`, `pitches` | `newsroom/investigations/story-alpha/2026/fact-check` / D5 | `source-drop/story-alpha/source-syn-017/device-export/messages/attachments/2026-07`、HEIC `.part`、evidence chain |

`ambient-home`は人物ごとに256 candidate entriesを持つ別laneとし、D6--D8、中間directory上のfile、
wide fan-out、同名copy、Unicode、空白、case collision、lockfile、partial、cache/tempを人物の業務文脈に合わせて
実現する。candidateを全件作るとは限らず、realized / rejected / excludedをreceiptへ残す。formal Recall、
120,000 chunk分母、20 scope latencyへambient entryを混ぜない。逆にformalだけの成功からrecursive traversalの
成功を推論しない。もしpersona `home/`全体を単一recursive scopeとして100,000 chunks超にする要件を追加するなら、
現行12 + 8 leaf-scope contractを変更せず、独立した`recursive-scale-v1` gateを新設する。

## 3. `persona-core-v1`の物理file比候補

分母は各personaのW0 physical filesであり、byte比、chunk比、logical-document比ではない。
各行はdominant + supporting = 99%。rare欄の件数合計が残りexact 1%、absentは0件である。

| persona / files | dominant | supporting | rare exact 1% | absent |
| --- | --- | --- | --- | --- |
| p01 software engineer / 12,000 | code 32, md 24, structured 14, txt/log 10 | text PDF 6, html/eml 5, csv/tsv 4, image 4 | ipynb 24、scan PDF 12、docx 24、xlsx 20、pptx 20、domain 20 | media |
| p02 SRE / 15,000 | txt/log 28, structured 22, md 20, code 15 | csv/tsv 5, text PDF 4, html/eml 3, image 2 | docx 30、xlsx 20、pptx 20、scan PDF 10、domain 70 | ipynb, media |
| p03 security/GRC / 10,000 | text PDF 24, structured 18, html/eml 16, csv/tsv 14, docx 8 | md 6, txt/log 5, scan PDF 4, xlsx 3, image 1 | code 30、pptx 20、domain 50 | ipynb, media |
| p04 ML researcher / 10,000 | code 25, ipynb 20, csv/tsv 16, structured 14 | md 10, text PDF 7, txt/log 4, image 3 | docx 20、xlsx 20、pptx 20、scan PDF 10、domain 30 | html/eml, media |
| p05 BI/data analyst / 12,000 | csv/tsv 25, xlsx 22, structured 18, code 10 | txt/log 7, md 6, text PDF 5, pptx 4, image 2 | html/eml 30、docx 25、ipynb 25、scan PDF 10、domain 30 | media |
| p06 life-science researcher / 8,000 | csv/tsv 20, text PDF 23, scan PDF 14, image 7, docx 10 | xlsx 8, structured 5, md 4, txt/log 4, domain 4 | code 20、ipynb 20、pptx 20、html/eml 20 | media |
| p07 humanities researcher / 7,000 | text PDF 28, scan PDF 22, docx 14, txt/log 10 | md 10, image 5, html/eml 4, structured 3, csv/tsv 3 | xlsx 20、pptx 15、media 20、domain 15 | code, ipynb |
| p08 product manager / 8,000 | docx 22, pptx 20, text PDF 18, md 15 | xlsx 8, html/eml 6, csv/tsv 4, image 3, structured 3 | txt/log 20、code 10、scan PDF 15、media 10、domain 25 | ipynb |
| p09 UX researcher / 9,000 | txt/log 22, image 20, media 15, docx 13, text PDF 10 | csv/tsv 6, pptx 5, scan PDF 4, md 3, structured 1 | html/eml 30、xlsx 30、domain 30 | code, ipynb |
| p10 consultant / 11,000 | xlsx 23, pptx 22, text PDF 20, docx 15 | csv/tsv 7, html/eml 5, scan PDF 3, md 2, structured 2 | txt/log 30、image 30、domain 50 | code, ipynb, media |
| p11 account executive / 10,000 | html/eml 28, docx 20, text PDF 18, pptx 12 | xlsx 7, txt/log 5, image 4, md 3, csv/tsv 2 | scan PDF 25、structured 20、media 20、domain 35 | code, ipynb |
| p12 support/success lead / 16,000 | txt/log 25, structured 20, md 18, html/eml 12 | csv/tsv 9, text PDF 5, image 4, code 3, docx 3 | xlsx 30、pptx 20、scan PDF 20、media 30、domain 60 | ipynb |
| p13 corporate/privacy counsel / 7,000 | text PDF 30, docx 25, html/eml 18, scan PDF 12 | txt/log 5, md 3, structured 2, image 2, xlsx 2 | pptx 20、csv/tsv 15、domain 35 | code, ipynb, media |
| p14 finance controller / 13,000 | xlsx 32, csv/tsv 20, text PDF 16, docx 10 | structured 7, scan PDF 5, pptx 4, html/eml 3, md 2 | txt/log 25、code 15、image 25、domain 65 | ipynb, media |
| p15 recruiter/people ops / 8,000 | docx 27, text PDF 24, html/eml 20, csv/tsv 9 | xlsx 7, md 4, txt/log 4, scan PDF 2, image 2 | pptx 20、structured 15、media 10、domain 35 | code, ipynb |
| p16 clinical researcher / 8,000 | text PDF 26, scan PDF 16, docx 16, csv/tsv 14, domain 8 | xlsx 6, image 5, structured 4, txt/log 2, md 2 | code 15、pptx 20、html/eml 20、media 25 | ipynb |
| p17 construction PM / 8,000 | text PDF 25, image 20, domain 18, scan PDF 12, xlsx 10 | docx 5, pptx 3, md 3, csv/tsv 2, html/eml 1 | txt/log 45、structured 20、media 15 | code, ipynb |
| p18 manufacturing quality / 12,000 | csv/tsv 20, xlsx 18, text PDF 18, txt/log 16, docx 10 | scan PDF 5, structured 4, md 3, domain 3, image 2 | code 30、html/eml 30、pptx 60 | ipynb, media |
| p19 educator / 9,000 | docx 22, pptx 20, text PDF 18, image 12, md 8 | xlsx 6, media 5, scan PDF 4, csv/tsv 2, html/eml 2 | txt/log 25、structured 15、domain 50 | code, ipynb |
| p20 journalist / 10,000 | txt/log 25, text PDF 20, html/eml 15, scan PDF 12, image 10 | md 6, media 4, docx 3, csv/tsv 2, structured 2 | xlsx 15、pptx 15、code 20、domain 50 | ipynb |

20人、203,000 filesを合算した表示用の上位groupは次になる。これはsuite平均で人物別gateを
代替せず、正本は上の人物別15-family exact allocationである。

| 表示group | files | 比 | 内訳 |
| --- | ---: | ---: | --- |
| plain / repo | 99,819 | 49.17% | code、md、structured、txt/log、csv/tsv、html/eml、ipynb |
| PDF | 41,822 | 20.60% | text PDF、scan PDF |
| Office | 45,534 | 22.43% | docx、xlsx、pptx |
| rich / domain | 15,825 | 7.80% | image、media、domain binary |
| total | 203,000 | 100.00% | 15 families |

表中のdominant/supporting値はpercentである。rare family内のextension配分は別manifestでexact化する。
この15-family比が現提案の具体値であり、family内の人物別exact extension allocationは次のfreeze対象である。
未対応だが実務上重要な`.sh`、`.tf`、`.parquet`、`.tex`、`.bib`、`.m4a`、`.mp3`、`.mp4`、
`.mov`、`.msg`、`.mbox`、`.dwg`、`.dxf`、`.heic`、`.svg`、`.webp`、macro-enabled Officeは、
positive検索対応を推論せず、まずraw-onlyまたはpending-conversion negative witness候補とする。

人物差が特に大きいfamilyは、full W0のexact extension splitを次の**registry拡張後候補**とする。これは
physical fileの実在性を上げるための配分であり、対応Adapterがないvariantをsearchable-positiveへ昇格しない。
新variantのrenderer、magic/MIME validator、independent receipt、core registryと全下流artifactのadditive
再freezeが間に合わない場合、coreのfamily countを別laneへ移してはならない。coreは下表の
`canonical fallback`で同数を置換して203,000 filesを維持し、新形式はcore分母外の別format-coverage fixtureへ
追加する。したがってunsupported variantの有無でcore physical-file denominatorは変わらない。

| persona / family / total | registry拡張後のfull W0候補 | 未拡張時のcanonical fallback |
| --- | --- | --- |
| p09 UX media / 1,350 | `.m4a` 675、`.mp3` 270、`.wav` 270、`.mp4` 135 | `.wav` 945、`.aiff` 405 |
| p19 educator media / 450 | `.mp4` 225、`.m4a` 90、`.mp3` 90、`.wav` 45 | `.wav` 248、`.aiff` 90、`.mid` 112 |
| p20 journalist media / 400 | `.m4a` 200、`.mp3` 100、`.wav` 60、`.mov` 40 | `.wav` 300、`.aiff` 100 |
| p11 account executive mail/web / 2,800 | `.html` 420、`.eml` 1,680、`.msg` 700 | `.html` 560、`.eml` 2,240 |
| p14 finance spreadsheet / 4,160 | `.xlsx` 3,328、`.xlsm` 624、`.xlsb` 208 | `.xlsx` 4,160 |
| p17 construction domain / 1,440 | IFCZIP 360、CDE ZIP 360、`.dwg` 432、`.dxf` 288 | IFCZIP 576、CDE ZIP 864 |

形式の存在と用途は一次資料でもcross-checkした。MicrosoftはExcelのOpen XML、binary、macro形式を区別し、
Office for the webも`.xlsx`、`.xlsb`、`.xlsm`を別形式として扱う
([Excel persistence formats](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-offdi/7ffd4731-47eb-46c0-a934-ea154df676d0)、
[Office supported types](https://learn.microsoft.com/en-us/office365/servicedescriptions/office-online-service-description/office-online-service-description))。
`.msg`はOutlook item用filesystem形式、`.eml`はMIME message保存形式である
([MS-OXMSG](https://learn.microsoft.com/en-us/openspecs/exchange_server_protocols/ms-oxmsg/b046868c-9fbf-41ae-9ffb-8de2bd4eec82)、
[Microsoft Graph MIME message](https://learn.microsoft.com/en-us/graph/outlook-get-mime-message))。
Jupyterは`.ipynb`をJSON構造のnotebook文書、DICOMはPart 10をmedia storage/file formatとして規定する
([Jupyter architecture](https://docs.jupyter.org/en/latest/projects/architecture/content-architecture.html)、
[DICOM current edition](https://www.dicomstandard.org/current/))。
AutodeskはDWGをnative drawing file、DXFをdrawing interchange形式として説明し、buildingSMARTのIFC実装資料は
IFC exchange fileのSTEP physical structureを記述する
([DWG compatibility](https://help.autodesk.com/view/ACADWEB/ENU/?caas=caas%2Fsfdcarticles%2Fsfdcarticles%2FAutoCAD-drawing-file-format.html)、
[DXF import/export](https://help.autodesk.com/cloudhelp/2021/ENU/AutoCAD-Core/files/GUID-D4242737-58BB-47A5-9B0E-1E3DE7E7D647.htm)、
[IFC header guide](https://standards.buildingsmart.org/documents/Implementation/ImplementationGuide_IFCHeaderData_Version_1.0.2.pdf))。
これらはformat採用の根拠であって、人物別percentの観測統計ではない。percentは引き続きauthored benchmark
hypothesisとして扱う。

現行canonical extension share、すなわち上表のfallbackをこのcore比へ
`hamilton-largest-remainder-v1`で機械適用した事前診断では、suite
203,000 filesの概算はcontract 68,761 (33.87%)、incidental 62,978 (31.02%)、raw-only 71,261
(35.10%)になる。とくにp17、p19、
p10はraw-onlyが約68.2%、69.6%、63.7%となるため、120,000 contract chunks達成だけでは
「人物PCにある全formatの検索性能」を証明しない。personaごとにcontract/incidental/raw-only physical files、
actual indexed chunks、contract chunks、positive query target familyを別々にattestし、latencyには
`contract chunks`だけでなく`actual indexed chunks`も併記する。

fullはpersona x family x extensionのexact整数一致を要求する。exact 10% pilotはrare内訳が10で割り切れないため、
canonical variant順をtie-breakにしたlargest-remainderで配賦する。200-file tiny smokeはrare 1%が2件しかなく
全rare variantを覆えないので、比率gateにはせず、必要variantを最低1件ずつ別coverage fixtureで確認する。
`.pdf`は拡張子だけでなくtext-layer/scan構造、Office/mail/CADはextension、magic、MIME、container validatorの
一致で分類する。raw-only sourceだけを正解根拠にするpositive queryは禁止する。

現行のcontributor family/extension role、人物別density class、1--70 chunks/sourceをそのまま使う静的必要条件では、
全20行で120,000 chunksが人物別min/max interval内に入る。最も狭いp06でもmaximumは124,884である。
これはaggregate intervalの必要条件に限り、family/variant/scope/bucket/cohortを同時に解くjoint allocationの
存在証明ではない。採用時はcore用problem/solution/proofを新規生成し、既存stress solutionから推論しない。

## 4. 規模と容量境界

次の表は**選択した1 profileあたり**の規模である。

| 単位 / selected profile | W0 physical files | W0 current chunks | W5 final current + history |
| --- | ---: | ---: | ---: |
| 1 persona-PC | 7,000--16,000 | 120,000 | 180,000 |
| 1 replay / 20 roots | 203,000 | 2,400,000 | 3,600,000 |
| 3 fresh replays / 60 physical roots | 609,000 | 7,200,000 | 10,800,000 |

これはlogical cardinalityであり、完成rootのcopyで達成しない。formal source-tree envelope候補はW0
512 MiB/person、W5 final 1.25 GiB/personであるが、`.kio`、CAS、SQLite/FTS/WAL、history、staging、
allocated blocksを含むroot-bound capではない。full書込み前にexact 10% pilotをW5まで実行し、destinationの
allocated blocks/inodesとtransient peakをcomponent別に読み戻す。10%観測の線形projectionと25% headroomだけを
fullの安全証明にせず、G4 root-bound Go/No-Go、full replay-01後の再較正、各waveのreserve guardを必須にする。

採用Decision、core専用problem/solution/proof、positive independent review receipts、historical claimsを保持した
`active_g0_unresolved_count == 0`、accepted G0 descriptor、core profile IDへpinし直したproduction-authoritative
namespace/source/byte/semantic/history/evaluation closure、device compositor、lane plan一式の再生成・再freeze後に
推奨するMVP実行は、`persona-core-v1`の
full x 3 replaysと`benchmark_stress_mix_v2`のexact 10% format-coverage pilot x 1 replayである。採用前の
`persona-core-v1` full campaignは引き続きblockedであり、既存stress正本を変更しない。両profileを
full x 3 replaysする場合は、
合計120 roots、1,218,000 W0 files、14,400,000 W0 chunks、21,600,000 W5 current+history
chunksになるため、別の容量・実行時間承認を必要とする。

## 5. 実装と検証の順序

物理作成前のplan/hash freezeは、content-only namespace -> review/derivation evidenceを持つpre-solve corpus
evidence closure -> query/oracleを持つpre-solve evaluation closure -> query非依存joint solution/proof -> final source plan ->
solution-compiled planned history plan / planned ledger -> post-solution concrete evaluation resolution -> authoritative
production blocker-ledger update -> corpus closure equality/reuse（corpus projection変化時だけevidence-only successor） +
authoritative history/evaluation/suite closure successors ->
`active_g0_unresolved_count == 0` -> G0 descriptorの一方向DAGで行う。
solution、final plan、compiled history、review/derivation receipt、query/evaluation ownerをcontent-only namespaceへ
逆流させない。

```text
plan/hash freeze
  -> tiny smokeでstorage model、component bytes/inodes、transientを実測
  -> pilot preflight: actual free bytes/inodes、hard quota、reserve、known floor、next-person/wave bound
  -> core exact 10% calibration pilot: W0 create/index/attest -> W1--W5 edit/history/attest
  -> pilot evidence seal -> retention decision -> optional verified eviction -> retained-set manifest
  -> free bytes/inodes再読 -> G4 root-bound Go/No-Go
  -> full replay-01: W0 create/index/attest -> W1--W5 edit/history/attest
  -> replay-01実測でreplay-02/03のcapacityを再較正 -> G4再判定
  -> full replay-02: W0からfresh create/index/attest -> W1--W5 edit/history/attest
  -> full replay-03: W0からfresh create/index/attest -> W1--W5 edit/history/attest
  -> 3 replay横断のformal構造・比率・chunk/history・Recall・latency・容量評価
  -> replay-01でambient-homeをmaterialize/attest/evaluate
  -> replay-01でbyte-stressをmaterialize/attest/evaluateしてlane receiptをseal
  -> benchmark_stress_mix_v2専用tiny smokeとwrite-safety preflight
  -> separate exact 10% format-coverage pilotをbenchmark_stress_mix_v2の別fresh rootで実行
  -> 全profile/laneのcampaign summary
```

ordered checkpoint IDはexact
`[W0, W1, W2, W3, W4, W5-pre-purge, W5-final]`の7件である。各checkpointでfail-fast receiptを取る。
人物別current chunk targetは同じ順で
`[120,000, 120,000, 120,000, 120,000, 120,000, 124,800, 120,000]`、history-only targetは
`[0, 24,000, 24,000, 48,000, 60,000, 64,800, 60,000]`とする。
最終検証を最後に置くことは、途中検証を省く
意味ではない。各receiptはpersona/replay/checkpoint単位でfile family/variant、scope別file数、depth、
directory fan-out、file fan-out、path byte長、extension/magic/MIME、raw/allocated bytes、inode、
current/history chunks、collision、shared inode/clone/link不在を束縛する。

履歴readinessの外側の証拠は、**3 replay-container receipts**、**60 persona-root receipts**、
20 personas x 3 replays x 7 checkpoints = **420 persona-checkpoint receipts**、
3 replays x 7 checkpoints = **21 replay-checkpoint seals**、**3 replay terminals**の合計**507 runtime
artifacts**へ分離する。その後に**1 campaign-readiness receipt**を発行する。query/oracle、Recall、latencyの
結果はこの履歴証拠へ混ぜず、最終評価側がcampaign readinessを入力pinとして受け取る。
campaign readinessが許可できるのはformal laneの
read-only evaluation開始だけであり、Recall合格、MVP Done、dogfood、releaseは引き続きfalseである。
途中のpersona receiptが1件でも失敗した場合はfailure receiptだけをatomic publishし、replay seal、terminal、
campaign readinessを発行しない。formal full campaign内の部分resumeや成功personaだけのpoolingは行わず、
再試行は新しいcampaign IDで3 replayすべてをW0からfresh作成する。

各persona receiptは単なるcountではなく、current集合とhistory-only集合を
`(scope_key, chunk_hash)`のordered set rootとして持ち、両集合の交差0、直前checkpoint receipt、
compiled schedule prefix、root birth nonce、writer provenance/read-set、Kio HEAD/tree/config、capacity guardを
chainする。実filesystem固有のinodeやnonceを含む動的receiptにはglobal golden SHAを設定せず、canonical body
SHAとexternal set rootを認証し、同じsealed receipt setをhash seed 0/1の独立processで再検証した
validation projection digestの一致を要求する。

core calibration pilotとformat-coverage pilotは目的もprofile IDも異なる。pilot rootをfull実行中も保持する場合、
root-bound peakはfull 3 replayにpilot実測footprintを加算する。削除する場合は、manifest/receipt/checkpoint sealの
独立検証後に明示的eviction receiptを残し、full rootへcopyまたはreflinkしない。format-coverage pilotを
同じdestination volumeへ別fresh rootとして保持する場合も、その実測footprintを同様に加算する。

fresh buildはempty destination、persona/replay固有registry、previous rootを含まないwriter read-set allowlistを
preflightする。通常copyはshared inode検査だけでは判別できないため、writerは各fileのrecipe/materialization
provenance journalを出し、atomic checkpoint sealでcreated path、raw hash、writer inputを束縛する。各W0--W5の
開始前にはactual free bytes/inodesとreserveを再読し、見積超過、別device、stale measurementをfail closedにする。
read-setはjournalの自己申告だけにせず、OS sandbox/capability allowlistとproducer非依存validatorで強制・照合する。
`HOME`、XDG config/data/cache/runtime、Kio registry/CAS/index/cache/temp、process tempもpersona/replay rootへ
隔離し、共有できるread setはimmutable plan/recipeだけに限定する。

pilotにもfullとは別のwrite-safety gateを置く。campaign直前に
`scope-local-regular-file-per-distinct-chunk-v1` storage modelがruntime再検証できた場合に限り、
tiny smokeから未観測componentを0とせず、pilot成功時の既知下限
20,300 sources + 1,097 authored directories + 240,000 current-chunk objects = 261,397 inodesに加え、
CAS/index/history/staging/tempのsmoke実測上限と次の1 persona/1 waveの保守boundを使う。各persona/wave前に
hard quotaとreserveを満たさなければ停止する。storage modelが不成立ならこの下限を流用せずfail closedで
再契約し、pilotが完走してから初めてfull用projectionを作る。

`ambient-home`と`byte-stress`のdesignated replayはcore replay-01とする提案だが、現contractでは未承認である。
formal latencyを汚染しないよう3 formal replayの評価後に作り、別manifest/receiptで評価する。各laneの作成前に
G4を再実行し、同じdeviceへ保持する実測footprintをroot-bound peakへ加算する。ここでいう
`byte-stress` laneはI/O/capacity専用で、`benchmark_stress_mix_v2` format-coverage profileとは別物である。

synthetic retrieval/performance sub-gateのformal acceptance候補は、20 scopesを持つ各persona x replayを
poolせず、各persona x scenarioでRecall@10 >= 0.8、M3-1 p95 < 5秒、M3-2/M3-3 p95 < 7秒とする。
Q_hardは20問以上で
Spotlight/ripgrep-allよりRecall@10を0.3以上上回る。measurement contractでは、fresh process/no prior searchの
first-passと、1回のunscored prime後のwarm-passを分け、OS cacheを強制flushしない場合はその事実を記録する。
閾値をどちらへ適用するかは実測前のDecisionで固定し、warm値をcold値として報告しない。
このsub-gateはD1相当のTTFV/AI強化時間/コスト予実比、開発者の実folder dogfood、full MVP Doneを代替しない。

3 replayは同一seed/plan/eventの決定性とfresh-storage再現性を検証するもので、統計的に独立な3標本ではない。
別content seedへの一般化は別suiteで評価する。

## 6. 適用限界

- この20人はknowledge-work/evidence-retrieval benchmark packであり、市場全体の利用者構成ではない。
  家庭・個人文書、学生、creative media、小規模事業者、物流・field serviceは将来の別packで扱う。
- core候補でも11/15 familiesが20人全員に存在し、人物別の存在family中央値は13である。PDF + Officeも
  suite全体の43.03%を占めるため、「実在PCの平均」ではなく人物差を強めたauthored benchmarkと呼ぶ。
- formal laneが証明するのは、深い親pathを持つ20 leaf scopesと人物単独120,000 chunksである。
  親folderから100,000 chunksをrecursive traversalする性能は証明しない。必要なら別scale gateを追加する。
- 3 replayは同じ20人を同じplanから作る60個のfresh physical rootsであり、60人でも統計的独立標本でもない。
- OS/case設定はprofile metadataと対象filesystem上の観測であり、3 OS native filesystemの完全emulationを
  自動的に証明しない。正式Recallのbasenameはportable ASCIIで、Unicode/case衝突はambient laneに限る。
- 職種固有だが現在未対応のformatはraw-onlyまたはpending-conversion negative witnessである。その存在から
  positive検索対応を推論せず、各primary use caseには別のsupported text contributorを最低1件要求する。
- 15,048 capacity cellsと74,529 residual slotsは物理slot数の余裕を示すだけである。cell/slotのsort/zipから
  source bytesがcellのtopic/language/factを含むとは推論しない。base membershipのexact replace、W0--W5
  visibility、renderer入力、actual body/chunk receiptが別ownerで閉じるまで、5,400 distractorのsemantic
  resolutionと最終評価はblockedのままである。formal MVPの意味論候補は9-fact / 15,048 cells、
  base membership exact replace、stable 11,704、current stale prior 1,672、W0 neutralからW1で導入する
  introduced 1,672である。canonical truth、source assertion occurrence、query relevance、selector visibilityを
  別fieldへ分け、P/S/M/C、W5非current、既存event sourceを除外した人物別capacityを再計測するまで
  assignmentはfreezeしない。このblockerは人物別folder/file比を変更しない。
