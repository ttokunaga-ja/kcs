# Persona-PC fidelity v2 G0 contract

Status: envelope、exact topology sidecar、joint必要条件problem artifactまで実装済み。必要条件は全20人で
通過したがsource-level exact solutionではない。`g0_contract_frozen=false`、G0 root未実装、非authorizing。
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

単に共通vectorをrotateして人物別と見せることは禁止する。各activity unitは1--100の人物内かつ
scope kind内の相対尺度で、1--39=low、40--59=moderate、60--79=high、80--100=very-highとする。
physicalは同じ人物・kind内のfile creation/import/retention pressure、contributorは同じ人物・kind内の
contract-chunk demandを表し、primaryとsecondaryのunit値を直接比較しない。
現在値は観測統計や経験的校正値ではなく、roleから作成したstress-design仮説である。同一band内の細かな値は
canonicalな authored interpolationにすぎず、測定精度を主張しない。G0 freeze前にrubricに照らした独立review
receiptが必要である。
topology sidecarは`activity_unit_review_receipt_bound=false`と
`activity_unit_rubric_review_receipt_not_bound` blockerを固定し、canonical receiptがG0 rootへ束縛されるまで
自動的に解除しない。

現在の`kcs.persona.pc-topology/v2` sidecarは上記400 rowsを完全展開し、envelope SHAを束縛する。
人物内のcasefold unique/ancestor禁止はroot安全制約である。人物をまたぐglobal casefold unique/ancestor禁止は
独立root間の衝突防止ではなく、template copyを抑えるsynthetic-diversity制約として別に扱う。
400 pathはglobal casefold unique、Dmaxは全人物でexact、physical/chunk vectorは人物間の同一・rotation・
permutation cloneを拒否する。weightは各scopeへphysical 50 bp / contributor 25 bpを先に与え、残余を
activity unitでHamilton配賦する`per-scope-floor-then-hamilton-residual-v1`で正規化する。
tiny/pilot/fullの物理配賦とpilot/full chunk配賦、scope別source必要上下界は
通過したが、これはjoint family/variant/density/cohort allocationの十分条件ではない。topology artifactの
`topology_complete=true`はpaths/loadだけを指し、`g0_contract_frozen=false`と全write authority falseを維持する。

## 5. physical familyとvariant

15 familyの人物別physical-file比はv2提案書の`benchmark_stress_mix_v2` exact 20x15 matrixを正とし、
full合計203,000、
pilot合計20,300、tiny合計4,000とする。family比の分母はW0 physical filesであり、bytes、logical
members、chunksではない。これは観測された実PC統計ではなくstress-design仮説である。whole-source cohort
必要条件を満たすため、p08のmd/domain-binaryは11/1%、p17は5/13%とし、suite fullのmd/domain-binaryは
18,820/6,760 filesとする。

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

### 5.1 persona realism profile

physical format比とは別に`persona_realism_profile`を持ち、既存W0 physical rowsへ検索参加する
duplicate/revision/conflict/attachment関係をoverlayする。初期候補範囲はexact duplicate 1--3%、
near/visible revision 3--8%、conflict copy 0.2--1%、standalone attachment copy 1--4%だが、範囲だけでは
G0条件を満たさない。人物別exact integer、分母、membership、検索参加、logical-document採点規則を凍結する。
overlayを理由にphysical file総数、family/variant marginal、contract chunk targetを暗黙変更しない。
overlayはpost-hoc処理ではなくjoint solver/source recipeの入力であり、canonical allocation解の後へ追加しない。
duplicate clusterのscope配置、raw identity共有、distinct `(scope_key, chunk_id)` 寄与を解の中で証明し、
同一scopeでのcollapseを含めても人物ごとのcontract targetをexactに保つ。

最低限、physical materializations、logical documents、gate/search roleとchunks、container members/
attachments、current/history versions、duplicate/conflict clusters、allocated bytes、cloud/OS由来metadataと
ignored/excluded entriesを別台帳で整合させる。exact/near/conflictは排他的なcontent-relation軸、attachmentは
直交するcontainer-role軸とする。未確定の間は
`persona_fidelity_realism_profile_and_overlay_missing` blockerを維持する。

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
max(4, ceil(scope_contributor_chunks / 70))
  <= contributor_files
  <= min(scope_contributor_chunks, scope_physical_files)
```

下限の4は任意の安全係数ではない。互いに排他的なwhole-source history cohort P/X/Y/Nを、pilot/fullの
各scopeへ最低1 sourceずつ置くcoverage制約から導く。Uには全scope coverageを要求しない。

scope別境界だけでなく、人物・profile全体で次のcohort別source下限を満たす。

```text
L(h, profile)
  = max(20 if h in {P,X,Y,N} else 0,
        ceil(cohort_chunks(h, profile) / 70))
contributor_sources(profile) >= sum_h L(h, profile)
```

| profile | P | X | Y | N | U | total lower |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| pilot chunks | 480 | 1,200 | 720 | 480 | 9,120 | - |
| pilot source lower | 20 | 20 | 20 | 20 | 131 | 211 |
| full chunks | 4,800 | 12,000 | 7,200 | 4,800 | 91,200 | - |
| full source lower | 69 | 172 | 103 | 69 | 1,303 | 1,716 |

authoritative solverはbounded exact searchで、objectiveは順に、hard constraint充足、比例idealからの
integer L1 deviation最小、route affinity最大、canonical flattened cell vectorのlexicographic最小とする。
solver schema/version、node/edge/state上限、tie-break順をhashへ含める。2x2 repairはwarm startにだけ使え、
authoritative exact解と一致しなければ捨てる。certificateはfamily、variant、scope、bucket、quota
histogram、warm-start repair steps、exact objective、各marginal hashを持つ。同じmarginalだけを満たす
別解を受理せず、canonical rebuildとexact一致させる。
この段落はobjective層の設計順だけを要求する。integer L1のexact式、route-affinity matrix、flatten axes、
探索上限は未束縛であり、これらをmachine-readable policyへ固定するまで`solver_policy_bound=false`である。

旧p17 pilotは203 contributor sourcesでglobal cohort下限211を満たさず、旧p08は211で余裕0だったため、
§5のphysical mixを明示変更した。現在は全20人のpilot/full/full-minus-pilot marginalsと必要条件が通過する。
pilot global下限余裕はp11の+7が最小、p08/p17は+8である。scope-boundではp17のlower headroomが28、
minimum scope spanが3、p07のupper headroomが388である。これらはmargin regressionとして固定する。

現在の必要条件artifactは次である。

```text
artifact_schema = kcs.persona.pc-joint-problem/v2
artifact_kind   = persona-pc-v2-joint-allocation-problem
canonical bytes = 744,081
sha256          = 384c95f550355b63443d7f5ca94dad2ed008ab7b24d6b8148a9504f613c29227
bound envelope  = 6b5c7145881f2ab1e8c84fe033f667757dccf478b704e0731d543bfddfcddbac
bound topology  = fc079fc8e0aaee0ae03a22fee349e0af8f2dfe18e1fed6d8bb05304643e4a958
```

これはfamily/variant、gate role、20 scopes、density bucket、cohort chunk、coordinatewise
full-minus-pilot residualを束縛するが、source rows、variant-to-scope route、source quota/cohort assignment、
canonical solver solutionを含まない。したがってstrict pilot source subsetの証明ではなく、
`joint_allocation_proved=false`、`joint_allocation_geometry_proved=false`、
`joint_allocation_proved_for_g0=false`、`solver_policy_bound=false`、`source_recipe_bound=false`を維持する。
family/variant/density bucket/history cohortを同時にroutingするjoint solverは未実装であり、必要条件通過を
completion evidenceとして扱わない。

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

現在のW0 raw-hash unique controlは必要条件artifactの暫定仮説であり、G0正本ではない。
`persona_realism_profile`は既存W0 physical rowsへduplicate/revision/conflict/attachment関係とsearch
participationを明示的にoverlayする。exact duplicateはmaterialization identityを分けつつraw identityを
共有できる。logical documentとduplicate clusterを別台帳で数え、duplicate pathがRecall expected source数を
水増ししない。overlayはphysical/family marginalsを変更せず、history eventで追加されるmaterializationは
別inventoryにする。W0 overlayはjoint solver/source recipeへ先に入力し、clusterのscope配置とdistinct
chunk寄与を含めて120,000 contract chunksを解く。allocation後のpost-hoc追加は禁止する。

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
- joint necessary problem: 4 MiB/suite（現在744,081 bytes）
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
activity_unit_review_receipt_bound = false
joint_allocation_proved          = false
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

1. 400 exact scope rows、2種類のauthored load vector、rubricに対する独立review receipt
2. full/pilot family/variant/scope/bucket/source quota exact allocation
3. P/X/Y/N/U history cohort、操作順、scope coverage、checkpoint exact projection
4. source recipe catalog、fact graph、oracle membership、独立query spec
5. 人物別`persona_realism_profile`、overlay membership、8軸台帳の整合
6. W0-W5全source/destinationのpath/basename collision、variant feasibility、resource cap validation
7. v1 identity/goldenの非回帰
8. 20人を1人ずつbuildしたcanonical bytes/hashと16 MiB cap
