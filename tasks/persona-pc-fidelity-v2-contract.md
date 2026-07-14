# Persona-PC fidelity v2 G0 contract

Status: envelope contract実装済み。`g0_contract_frozen=false`、G0 root未実装、非authorizing。
現行`kcs-persona-pc-v1`、そのartifact、golden hash、writer、history planを変更しない。

Date: 2026-07-14

## 1. 目的とversion境界

v2は20人の独立したsynthetic PCを、人物ごとに20 active leaf scopes、120,000 current
contract-contributor chunks、W5 finalで180,000 current+history contract chunksとして計画する。
人物間のfile/chunk poolingは禁止する。

v2はv1をin-place migrationしない。すべてのv2 artifactは次のidentityを持つ。

```text
fixture_id             = kcs-persona-pc-v2
fixture_schema_version = 2
```

validatorはbodyをmaterializeする前にbounded framed headerを読み、次のexact tupleでdispatchする。

```text
(artifact_schema, artifact_schema_version, artifact_kind,
 fixture_id, fixture_schema_version)
```

genericなartifact `schema_version`と`fixture_schema_version`を混同しない。plan、allocation、certificate、
event、query、receiptはそれぞれ別`artifact_schema`と`artifact_kind`を持つ。v1 validatorがv2を、v2
validatorがv1を、または別artifact kindのbodyを受理してはならない。既存v1 rootはv1 verifierで読み、
v2はv2 contractからfresh rootへ再生成する。

G0はpure planningだけを扱う。renderer、filesystem writer、KCS subprocess、W1-W5 mutation、Recall、
performanceは呼び出さない。

## 2. lane境界

1つの小さなsuite descriptorが、次の3つの独立したversioned lane spec hashを束縛する。

| lane | replay | formal chunk母数 | history | authority |
| --- | ---: | --- | --- | --- |
| `formal-retrieval-history-v2` | 3 fresh-storage deterministic replays | 含む | W0-W5 | G0はplanned only |
| `recursive-robustness-v1` | 1 separate-manifest replay | 含めない | 代表操作のみ | formal評価を代替しない |
| `byte-stress-v1` | 1 W0-only | 含めない | なし | capacity/I/O専用 |

robustness entryとbyte-stress entryをformal family ratio、scope count、chunk count、Recall queryへ
混ぜない。各laneは別root、別manifest、別receiptを持つ。

## 3. profileとpilot projection

| profile | files/person | suite files | contributor target/person | density contract |
| --- | ---: | ---: | ---: | --- |
| `tiny-smoke` | 200 | 4,000 | contributor sourceごと3 chunks | 適用しない |
| `pilot` | fullのexact 10%（700-1,600） | 20,300 | 12,000 | 適用する |
| `full` | 7,000-16,000 | 203,000 | 120,000 | 適用する |

pilotは独立再allocationを「sample」と呼ばない。solverはpilotを先にexact解として作り、pilotの
family/variant/scope/bucket cell、12,000 chunks、P/X/Y/N/U cohortを同時に解く。そのpilot source rowを
不変の予約inventoryとしてfull solverへ埋め込み、fullは追加sourceだけで120,000 chunksとfull marginalsを
完成する。pilot source IDsはfull source IDsのstrict subsetである。

pilotからfullへ不変に継承するfieldは、source/materialization ID、scope、family、variant、gate role、
density bucket、requested quota、history cohort、fact/template/profile refs、semantic basename、target
complexity/bytes、payload seedである。fullでpilot sourceをre-quota、別cohort化、renameしてはならない。
canonical hash-spreadは、pilot-first joint solverが同じobjective値を持つ候補から一意解を選ぶ最後の
tie-breakであり、無条件のpost-hoc source選択ではない。

literal 10分の1が整数にならないvariant/bucketはlargest remainderで配分する。tie-breakは
canonical family、variant、bucket、source順であり、platform、Python hash seed、filesystem orderを
使わない。

tinyはrouting/topology smokeである。pilot/full用density bucketをtinyへ適用すると最小quotaだけで
tiny targetを超えるため、tinyをformal density証拠やpilot capacity証拠に使わない。

## 4. topology contract

canonical v2 fixtureは20 persona rowsをpersona ID順に持ち、各rowは20 scope rowsをordinal順に完全展開する。
runtime templateだけ、代表pathだけ、primary/secondary合計だけのartifactにはv2 root hashを発行しない。

```text
persona_id / role / formal_dmax / primary_share_bp
scope.ordinal / scope_key / kind / functional_slot / relative_path
scope.physical_file_weight_bp / scope.contributor_chunk_weight_bp
```

必要条件:

- exactly 20 personas、各12 primary + 8 secondary、合計400 scopes
- physical file weightsとcontributor chunk weightsは別vectorで、各人物10,000 bp
- primary subtotalは人物別の宣言値、secondaryは残差
- 全weight正。tinyで全scopeに1 file以上を置けるphysical lower boundを持つ
- 20人物のphysical vectorとcontributor vectorをそれぞれ複製しない
- secondaryはfunctional slotだけ共有し、160 physical pathsは人物別
- componentは`^[a-z0-9][a-z0-9-]*$`、80 bytes以下、relative pathは240 bytes以下
- `.`, `..`、separator/control、Windows禁止文字、末尾dot/space、CON/PRN/AUX/NUL/COM1-9/LPT1-9禁止
- portable lowercase ASCII、casefold unique、scope間ancestor/descendantなし
- derived maximum path depthが`formal_dmax`とexact一致し、少なくとも1 pathが到達
- tiny/pilot/fullの全scopeでphysical filesとcontributor quotaが正
- W1-W5のrename/move/archive/restore/replacement/purge pathにも同じ規則を適用し、全checkpointで
  casefold collision、ancestor conflict、既存destinationを拒否

単に共通vectorをrotateして人物別と見せることは禁止する。各weightはその人物のactivity/folder roleを
説明できるreviewed stress-design仮説でなければならない。

## 5. physical familyとvariant

15 familyの人物別physical-file比はv2提案書のexact 20x15 matrixを正とし、full合計203,000、
pilot合計20,300、tiny合計4,000とする。family比の分母はW0 physical filesであり、bytes、logical
members、chunksではない。

family内variantは人物別profileを使う。各variant dictionary entryは次を一意に決め、source rowによる
overrideを許可しない。

```text
variant_id / extension / media_type / gate_role / expected_offline_disposition
validator_id / validator_schema_version / renderer_id / renderer_schema_version
complexity_unit / feasibility_rule_id
```

extensionだけを付け替えたbytesは禁止する。ZIP/IFCZIP、USTAR、GZIP、NPZ、PCAP、DICOMには
独立validatorを割り当てる。SQLiteはruntime/version/compile optionsを完全に束縛できるまでformal
variantへ入れない。

現envelopeはfamily/variant ratio、extension、gate role、planned disposition、validator/renderer identityを
機械化したが、variant別`complexity_unit`とfeasibility parameterはsource recipe/renderer設計まで未確定である。
その間は`variant_catalog_complete=false`とし、G0 root hashを発行しない。

offline dispositionはfamilyではなくvariant別に固定する。例:

- `.png/.jpg`、scan PDF: recognized non-text、offline raw-only、`awaiting_ocr`
- DOCX/XLSX/PPTX: recognized non-text、offline raw-only、`await_conversion`
- text-layer PDF: local `contract_contributor` / `local_pdf_text`
- `.tif/.bmp`、WAV/AIFF/MID、domain binary: octet-stream raw-only、`unsupported_binary`
- `.md/.markdown/.txt`とrecognized code: local `contract_contributor` / `local_text`
- `.log/.jsonl`、structured、CSV/TSV、HTML/EML、IPYNB: `incidental_sniff` hypothesis

`raw_only actual chunks == 0`はG2/G7のobserved gateであり、G0のplanned dispositionで代替しない。

## 6. joint allocation

densityの分母はfamily/variant integer allocation後のcontract-contributor sourcesだけとする。

| class | personas | 1-4 | 5-20 | 21-50 | 51-70 |
| --- | --- | ---: | ---: | ---: | ---: |
| low | p01,p02 | 30 | 50 | 20 | 0 |
| medium | p03,p04,p07,p12,p18,p20 | 10 | 30 | 45 | 15 |
| high | p05,p06,p09,p10,p13,p14,p16,p19 | 3 | 12 | 45 | 40 |
| dense-office | p08,p11,p15,p17 | 1 | 4 | 20 | 75 |

solverは集約cell上で、次を同時に満たす。

1. family -> variant Hamilton marginals
2. physical files -> 20 scope column marginals
3. contributor files -> scope bounds
4. density bucket -> scope controlled rounding
5. bounded exact min-cost flow/search
6. bucket内のsource quotaを1-70でscope targetへexact化
7. P/X/Y/N/U whole-source history cohortsと必要scope coverage

各scopeの必要境界は次である。

```text
ceil(scope_contributor_chunks / 70)
  <= contributor_files
  <= min(scope_contributor_chunks, scope_physical_files)
```

authoritative solverはbounded exact searchで、objectiveは順に、hard constraint充足、比例idealからの
integer L1 deviation最小、route affinity最大、canonical flattened cell vectorのlexicographic最小とする。
solver schema/version、node/edge/state上限、tie-break順をhashへ含める。2x2 repairはwarm startにだけ使え、
authoritative exact解と一致しなければ捨てる。certificateはfamily、variant、scope、bucket、quota
histogram、warm-start repair steps、exact objective、各marginal hashを持つ。同じmarginalだけを満たす
別解を受理せず、canonical rebuildとexact一致させる。

現在のpersona-global probeはfull/pilotの全20人を可解とするが、400 exact load vectorが未凍結なので
scope-level completion evidenceではない。特にp07 pilotはbucket上限まで294 chunksしか余裕がない。

## 7. history checkpointsとincidental上限

full checkpointは人物・replayごとに次とする。

| checkpoint | current C | history-only H |
| --- | ---: | ---: |
| W0 | 120,000 | 0 |
| W1 | 120,000 | 24,000 |
| W2 | 120,000 | 24,000 |
| W3 | 120,000 | 48,000 |
| W4 | 120,000 | 60,000 |
| W5 pre-purge | 124,800 | 64,800 |
| W5 final | 120,000 | 60,000 |

pilotは同じsource cohort/event modelのexact 10% projectionとする。

| checkpoint | current C | history-only H |
| --- | ---: | ---: |
| W0 | 12,000 | 0 |
| W1 | 12,000 | 2,400 |
| W2 | 12,000 | 2,400 |
| W3 | 12,000 | 4,800 |
| W4 | 12,000 | 6,000 |
| W5 pre-purge | 12,480 | 6,480 |
| W5 final | 12,000 | 6,000 |

profile `p`のeligible上限とbase incidental上限は下表のexact integerを使う。wave別上限は次である。

```text
incidental_current_cap(p,w)
  = min(base_incidental_current[p], current_eligible_cap[p] - C(w))
incidental_current_plus_history_cap(p,w)
  = min(base_incidental_total[p], total_eligible_cap[p] - C(w) - H(w))
```

pilot W5 pre-purgeでは1,020 / 2,040となる。

artifactにはfractionやfloatを保存しない。profile別のexact integer cap tableを正とする。

| profile | current eligible cap | current+history eligible cap | base incidental current | base incidental total |
| --- | ---: | ---: | ---: | ---: |
| full | 135,000 | 210,000 | 15,000 | 30,000 |
| pilot | 13,500 | 21,000 | 1,500 | 3,000 |

各source version/materializationのplanned incidental upperをwave別current/history inventoryへ投影し、
`sum(planned current upper) <= cap_current(w)`、`sum(planned current+history upper) <= cap_total(w)`を
solver certificateで証明する。G7 observed gateでは
`Icur=actual_current-C(w)`、`Itotal=actual_current_plus_history-C(w)-H(w)`とし、
`0 <= Icur <= cap_current(w)`かつ`Icur <= Itotal <= cap_total(w)`を実読する。

### 7.1 history cohort model

pilot/fullのwhole-source contributor cohort比は`P/X/Y/N/U = 4/10/6/4/76`である。quota chunk合計を
この比へexactに合わせ、P/X/Y/Nはpilot/fullとも各人物の20 scopesすべてを正のsourceで覆う。
10% projectionはcheckpoint/cohort chunk targetへ適用し、source/event row countがfullの厳密10%である
ことは要求しない。

- P: W1 small edit。W5でP'を別pathへ作成・index後、旧P pathを1件ずつpath-purgeして同quota P'で置換
- X: W1 small edit、W3 major edit、W4 deleteし、同scope/variant/quotaのX'で置換
- Y: W1 small edit、W3 major edit、そのままcurrent
- N: W3 edit、W5 correction
- U: arithmetic control。安全なsame-scope rename/duplicateの母体にできる

W5順序は全regular events、全ordinary scope indexes、P' current確認、persona/source順の旧P
unlink/path-purge + forced purged commit、全post-purge noop indexesである。rename/move/archive/restore等の
structural event inventory、dependency、before/after state、replacement recipeもroot-independent intentへ
exact列挙する。rendererが未完成のG0ではevent bytes/hashを作らず、intent hashだけを凍結候補にする。

formal W0 raw hashesはunique controlとし、exact/near/conflict duplicateは明示eventまたはrobustness
laneで導入する。logical content identityとmaterialization identityを分離し、duplicate pathがRecall
expected source数を水増ししない。

## 8. source recipeとoracle

v2 planは共通catalogとsource固有rowを分離する。

```text
catalogs:
  fidelity_profiles / source_profiles / projects / entities / facts
  filename_templates / content_templates / permission_profiles / mtime_buckets
  validators / renderer_profiles
sources:
  persona_id / scope_key / source_id / materialization_id / source_profile_id
  project_or_case_id / entity_ids / fact_ids / period / status / version
  requested_contributor_chunks / expected_incidental_chunks_upper
  target_complexity / target_bytes / duplicate_or_conflict_group / payload_seed
```

file name、extension、gate role、media typeはsource profileとtemplateから一意に導出し、source rowへ
重複保存しない。basenameはlowercase ASCII、120 bytes以下、scope内casefold uniqueで、persona/source
ID、path、digest、fixture nonceを露出しない。

fact graphとanswer membershipをrendererより先に凍結する。corpus template/seed、event seed、query
template/seedを別domainに置く。query artifactはcorpus rendererから参照不能とし、query text/templateを
source recipeへ入れない。

各人物はexact 90 positive queries（30 x M3-1/M3-2/M3-3）と15 purged-negative（5 x 3）を持つ。
suite全体で1,800 positive query textをbyte-uniqueにする。scenario内の30問は次の3 strataを各10問とする。

- M3-1: `current-fact` / `cross-format-fact` / `locale-language-fact`
- M3-2: `old-wording` / `rename-move` / `locale-language-history`
- M3-3: `deleted` / `restored` / `locale-language-lifecycle`

多言語personaの`locale-language-*`には非primary languageを最低1問含める。negativeはRecall母数外で
`false-positive@10 == 0`を要求する。各positiveには同topic/languageのdistractor sourcesを3件以上
持たせる。G0 freeze時は`query_spec_hashed=true`、実query text生成前は
`query_instances_rendered=false`とし、両者を1つの`query_rendered` claimへ畳まない。

## 9. hash graphとresource boundary

canonical JSONはsorted keys、compact UTF-8 NFC、integer-only、duplicate keyなしとする。root/runtime
path、replay number、timestamp-nowをplan hashへ入れない。logical epochとexact offsetを使う。

hash graphはacyclicとし、domain-separated entry hash -> referenced catalog closure -> persona plan hash ->
suite hashの一方向だけを許す。self-hash fieldをcanonical bytesへ含めない。missing、duplicate、unused、
cyclic、foreign-persona referenceはfail closedとする。

bounded artifact上限は次とする。すべて最大nesting depth 64、string 4,096 bytes、bodyを読む前の
framed byte capを持つ。

- suite/fixture envelope: 2 MiB
- W0 persona plan: 16 MiB、最大16,000 W0 sources、20 scopes
- joint allocation certificate: 8 MiB/person
- history intent/event recipe: 16 MiB/person、event-created sources最大4,096/person
- oracle/query spec: 4 MiB/person、positive 90、negative 15
- suite descriptor/compact summaries: 4 MiB

suite buildは1 personaずつ行い、20 full plansを同時保持しない。p12の16,000 W0 sourcesと
event-created replacement recipesは別inventory/別上限であり、W0 capを暗黙超過させない。

capacity candidate:

- formal W0: 512 MiB/personかつ10 GiB/replay
- W5 final: 1.25 GiB/personかつ25 GiB/replay
- W5 pre-purge: 1.35 GiB/personかつ27 GiB/replay
- 3 retained roots + workspace: 88 GiB
- byte-stress: 740 MiB payload/person、768 MiB/person、15 GiB total
- first pilot: 32 GiB cap、96 GiB reserve、250,000 inode cap、worker 1

これらはplanning cap候補であり、allocated blocks、CAS/index/history/staging、inode、RSSのpilot readback
までfull writeをauthorizeしない。
`1.35 GiB/person`はcanonical integerでは`floor(27 GiB / 20)`とし、20人合計には8 bytesの余白が残る。

## 10. G0 negative authority

G0 artifact/receiptは次を固定する。

```text
g0_contract_frozen               = false  # 全400 paths/load/solver/oracle完了まで
renderer_available               = false
filesystem_writer_available      = false
kcs_execution_available          = false
history_executor_available       = false
query_spec_hashed                = false  # oracle/query spec完成時にのみtrue
query_instances_rendered         = false
actual_chunks_attested           = false
formal_capacity_gate_satisfied   = false
authorizes_physical_write        = false
authorizes_history_mutation      = false
```

solver成功だけで現行`WRITABLE_PROFILES`、`HISTORY_ASSIGNMENT_EXECUTABLE`、prepare/history receiptの
formal flagを変更してはならない。

`g0_contract_frozen=true`へ変更できるのは、次がすべてcanonical rebuildで証明された後だけである。

1. 400 exact scope rowsと2種類のreviewed load vector
2. full/pilot family/variant/scope/bucket/source quota exact allocation
3. P/X/Y/N/U history cohort、操作順、scope coverage、checkpoint exact projection
4. source recipe catalog、fact graph、oracle membership、独立query spec
5. W0-W5全source/destinationのpath/basename collision、variant feasibility、resource cap validation
6. v1 identity/goldenの非回帰
7. 20人を1人ずつbuildしたcanonical bytes/hashと16 MiB cap
