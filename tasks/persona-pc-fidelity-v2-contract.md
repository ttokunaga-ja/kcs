# Persona-PC fidelity v2 G0 contract

Status: envelope、exact topology、joint必要条件problem、generic aggregate-core solver-policy sidecarまで
実装済み。必要条件は全20人で通過したが、route/realism/source-intent入力、実行可能solver、solution、proofは
含まない。`g0_contract_frozen=false`、G0 root未実装、非authorizing。
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
完成する。canonical final source planではpilot source IDsをfull source IDsのstrict subsetとして
証明しなければならないが、現時点では未証明である。

pilotからfullへ不変に継承するfieldは、source/materialization ID、scope、family、variant、gate role、
density bucket、requested quota、history cohort、fact/template/profile refs、semantic basename、target
complexity/bytes、payload seedである。fullでpilot sourceをre-quota、別cohort化、renameしてはならない。
集約割当の最終tie-breakは後述のcanonical dense semantic vectorのlexicographic最小であり、
hash-spreadを使わない。domain-separated hashはpre-solve input-closure namespaceと、解かれた
immutable origin `pilot|full-residual`、`intent_key`、semantic coordinates、cell-local ordinalからの
source/materialization identity生成にだけ使う。pilot ordinalはfullでも予約して変更せず、residual追加で
pilot IDをrenumberしない。
IDを内包するsolution/plan hashをpreimageへ含めず、hash順序自体を割当の比率・route・quotaの
権威にしない。

pilotとfullの関係claimは、(1) aggregate cell subset、(2) source-ID subset、
(3) materialization subset、(4) rendered-byte subsetに分ける。現時点は
`pilot_aggregate_cell_subset_proved=false`、`pilot_source_id_subset_proved=false`、
`pilot_materialization_subset_proved=false`、`pilot_byte_subset_proved=false`である。cell残差の
非負だけで、後ろ3つやbyte同一性を導いてはならない。

literal 10分の1が整数にならないvariant/bucketはlargest remainderで配分する。tie-breakは
canonical family、variant IDのASCII-byte順、bucket順であり、このmarginal roundingへsource/intentや
hash順序を使わない。platform、Python hash seed、filesystem orderにも依存しない。

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
overlayはpost-hoc処理ではなくpre-solve source-intent recipeとjoint solverの入力であり、canonical
allocation解の後へ追加しない。aggregate `A/C`だけではper-intent duplicate clusterのscope配置、
raw identity共有、distinct `(scope_key, chunk_id)` 寄与を証明できない。overlay membershipを
`intent_key`へ束縛したsource-intent refinementを解き、同一scopeでのcollapseを含めても人物ごとの
contract targetをexactに保つ。

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

authoritative solverはbounded exact searchとする。人物・profileごとにphysical aggregateを
`A[v,s]`、contributor refinementを`C[v,s,b,h,q]`とし、どちらも非負integerとする。
`C`はcontributor variantにだけ存在し、`q`はbucket `b`の閉区間に含まれる。次を定義する。
以下の記号はすべてphase `phi in {pilot,full}`ごとの値であり、式では`phi`を省略する。full評価へ
pilotの`N/T/M_v/F_s/t_s/D_b/H_h`を流用してはならない。

```text
F       = physical source数
N       = contributor source数
T       = contributor chunk数
M_v     = variant vのexact physical marginal
F_s     = scope sのexact physical marginal
t_s     = scope sのexact chunk target
D_b     = bucket bのexact source marginal
H_h     = cohort hのexact chunk marginal
n_s     = Σ_v,b,h,q C[v,s,b,h,q]
d_b,s   = Σ_v,h,q C[v,s,b,h,q]
r_h,s   = Σ_v,b,q C[v,s,b,h,q]
k_h,s   = Σ_v,b,q q C[v,s,b,h,q]
z_b,s,q = Σ_v,h C[v,s,b,h,q]
w_b     = bucket bに含まれるinteger quotaの個数
W       = lcm(4,16,30,20) = 240
```

ここでいうhard constraintはfamily/variant/scope/bucket/cohort/quotaのaggregate coreである。
realism overlay、variant feasibility、pre-solve source-intent recipe、fact/oracleをまだ含まないため、これだけを
complete source-level feasibilityと呼ばない。aggregate coreは少なくとも次のexact式をすべて満たす。

```text
Σ_s A[v,s] = M_v                                      for every v
Σ_v A[v,s] = F_s                                      for every s
A[v,s] = Σ_b,h,q-in-b C[v,s,b,h,q]                   for every contributor v,s
Σ_v,s,h,q-in-b C[v,s,b,h,q] = D_b                    for every b
Σ_v,b,h,q-in-b q*C[v,s,b,h,q] = t_s                  for every s
Σ_v,s,b,q-in-b q*C[v,s,b,h,q] = H_h                  for every h
Σ_v,b,q-in-b C[v,s,b,h,q] >= 1                       for every s,h in {P,X,Y,N}
Σ_v,s,b,h,q C[v,s,b,h,q] = N
Σ_v M_v = Σ_s F_s = F
Σ_b D_b = N
Σ_s t_s = Σ_h H_h = T
```

`U`にはscope coverageを要求しない。non-contributor variantには`C` cellを持たせない。これらと
§6冒頭のscope source上下界、nonnegative integer、bucket membershipを合わせてaggregate-core hard
constraintsとする。充足後のexact integer objective layersは次の5つである。

```text
L_scope          = Σ_s       |T*n_s - N*t_s|
L_density        = Σ_b,s     |N*d_b,s - D_b*n_s|
L_cohort_sources = Σ_h,s     |T*r_h,s - H_h*n_s|
L_cohort_chunks  = Σ_h,s     |T*k_h,s - H_h*t_s|
L_quota          = Σ_b,s,q (W/w_b)*|w_b*z_b,s,q - d_b,s|
```

`L_cohort_sources`と`L_quota`は観測されたユーザー統計ではなく、同一hard
marginal上の偏りを抑えるbenchmark canonicality regularizerである。観測現実の推定精度を
主張しない。routeは将来の独立review済み`R[persona,variant,scope] in 0..4`だけを使う。
phase別variant marginalを`M_phi,v`、両phase共通のroute active setを
`V+={v | M_full,v > 0}`とし、

```text
route_achieved_phi = Σ_v∈V+,s A_phi[v,s] * R[persona,v,s]
route_ideal_phi    = Σ_v∈V+ M_phi,v * max_s R[persona,v,s]
L_route_phi        = route_ideal_phi - route_achieved_phi
```

とする。physical `A`を1回だけ評価し、`C`との二重加算をしない。現行v1 route hintは
10,820 active persona-variant-scope cellsのうち749しか非0でなく、`md`/`txt_log`が全0、
secondary偏重も持つためv2の権威に再利用しない。review済みの完全な
persona x variant x scope行列とreceiptができるまで
`route_affinity_matrix_review_receipt_bound=false`を維持する。

solverはpilot候補を単独で決めず、その候補からexact fullへ非負残差で延長できることを
hard constraintとする。`A_full=A_pilot+deltaA`、`C_full=C_pilot+deltaC`とし、次のstrict
lexicographic tupleを最小化する。

```text
(pilot L_scope, L_density, L_cohort_sources, L_cohort_chunks, L_quota,
 pilot L_route, Flat(A_pilot), Flat(C_pilot),
 full-aggregate L_scope, L_density, L_cohort_sources, L_cohort_chunks, L_quota,
 full-aggregate L_route, Flat(deltaA), Flat(deltaC))
```

full側の5式とrouteは残差だけでなくpilot+残差のfull aggregate上で評価する。
人物ごとの`Flat(A)`はcanonical family順、family内variant IDのASCII-byte順、scope ordinal順、
`Flat(C)`はそれにdensity bucketのenvelope順、cohort `P/X/Y/N/U`順、quota昇順を追加した
dense zero-inclusive vectorとする。personaはflat cell軸ではなくsuite solve/serializationの外側で
`p01..p20`順、pilot/full-residualの順は上記strict pair tuple自体で決める。suite-wide `A`表現は
1 tensorあたりfull-zeroを含む566 bound persona x declared-variant rows、11,320 cellsを保持する。
route matrixは`full variant marginal > 0`をactiveとする別の541 rows、10,820 scoresであり、除外する25 rowsは
hard-zero `A`なので`R`を要求しない。`C`は1 tensorあたり116 contributor rows、812,000 cellsである。
joint pilot+residual decision coordinatesは最低22,640 `A` cellsと1,624,000 `C` cellsであり、
absolute-value/search auxiliary stateは別に数える。
envelope内の表示順とASCII順が異なる場合も`persona_id+variant_id`でjoinし、位置やfiltered row番号で
zipしない。

5つのL、route、flat vectorは別々のlexicographic componentsとして保持し、weighted sumやbig-Mで
合成しない。float/decimal近似を禁止し、boolをintegerとして受理しない。すべての積・和・絶対値は
checked signed 128-bit、`max_integer_bits=127`で計算し、overflowは
`invalid_problem_or_policy`としてfail closedにする。現行`F<=16,000`、`N<=F`、`T<=120,000`では
`L_scope<=2TN`、`L_density<=2N^2`、`L_cohort_sources<=2TN`、
`L_cohort_chunks<=2T^2`、`L_quota<=2WN`、`L_route<=4F`で、最大は
`2T^2=28,800,000,000 < 2^35`である。上限変更時はpolicy versionを上げる。

solver schema/version、node/edge/state上限、上記式、軸、tie-break順をpolicy hashへ含める。
2x2 repairはwarm startにだけ使え、authoritative exact解と一致しなければ捨てる。warm-start
steps、objective値、marginal hashは実行receiptにはなるが、それだけでglobal optimality
certificateと呼ばない。最適性を証明するにはvalidatorによるbounded canonical exact replayか、
完全なlower-bound/dual proofと照合が必要である。8 MiB上限で完全proofを保持できない場合は
`execution receipt`と呼び、`optimality certificate`と呼ばない。

このgeneric aggregate-core数式、dense axes、checked arithmetic、暫定deterministic探索上限は、次の
non-authorizing machine-readable policy sidecarへ固定済みである。

```text
artifact_schema = kcs.persona.pc-joint-solver-policy/v2
artifact_kind   = persona-pc-v2-joint-solver-policy
canonical bytes = 82,950
sha256          = 29046b5b5d60d25db51a670e597617bec07b7c4513bded39196bb1053ee52f41
```

ただしroute matrix/review receipt、realism/source-intent refinement、source recipe/variant feasibility、
fact/oracle/query specが未束縛なので、`exact_objective_evaluable=false`、`exact_solver_executable=false`、
`policy_definition_complete_for_bound_problem=false`、`solver_policy_bound=false`である。探索上限も
`resource_limits_empirically_calibrated=false`であり、cap到達は`resource_exhausted-unknown`とする。
canonical solutionは`persona_realism_profile`/overlay、pre-solve source-intent recipe、reviewed route
matrix、fact/oracleを入力として束縛する前に作ってはならない。

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
canonical solver solutionを含まない。したがってaggregate cell、source ID、materialization、
rendered bytesのどのpilot subset claimの証明でもなく、
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
canonical solutionに含め、bounded exact replayまたは完全proofで検証する。warm start/objective/marginal
hashだけのexecution receiptを最適性証明として扱わない。G7 observed gateでは
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
別inventoryにする。W0 overlayはpre-solve source-intent recipeとjoint solverへ先に入力し、aggregate
coreに加えてsource-intent refinementでclusterのscope配置とdistinct chunk寄与を含む120,000 contract
chunksを解く。allocation後のpost-hoc追加は禁止する。

## 8. source recipeとoracle

pre-solve source-intent artifactは共通catalogとimmutable intentを分離する。overlayとfact membershipは
すべて`intent_key`を参照し、この段階ではfinal source/materialization IDを持たない。

```text
catalogs:
  fidelity_profiles / source_profiles / projects / entities / facts
  filename_templates / content_templates / permission_profiles / mtime_buckets
  validators / renderer_profiles
intents:
  persona_id / intent_key / source_profile_id / eligible_scope_keys
  project_or_case_id / entity_ids / fact_ids / period / status / version
  contributor_eligibility / allowed_bucket_ids / expected_incidental_chunks_upper
  target_complexity / target_bytes / duplicate_or_conflict_group / payload_seed
overlay_memberships:
  relation_kind / cluster_key / intent_keys / search_participation
```

aggregate solutionに続くsource-intent refinementは、各`intent_key`へscope、family/variant、
bucket/cohort/quota、cell-local ordinalをexactに割り当て、overlay/duplicate-cluster constraintも検証する。
final source/materialization IDはinput-closure namespaceと解かれたsemantic coordinates/cell-local ordinalの
domain-separated hashから導出する。preimageは`persona_id`、immutable origin
`pilot|full-residual`、`intent_key`も含む。pilot cell-local ordinalはfullでも不変に予約し、residual
sourceは別originで追加してpilot IDをrenumber/collideさせない。IDを含むpayload自身のhashや、IDを内包する
solution/plan hashをpreimageへ戻してcycleを作らない。downstream final source planがupstream solution
hashと導出済みIDを束縛する。

file name、extension、gate role、media typeはsource profileとtemplateから一意に導出し、intent/final source
rowへ重複保存しない。basenameはlowercase ASCII、120 bytes以下、scope内casefold uniqueで、persona/source
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

hash graphはacyclicとし、`envelope -> topology -> joint necessary problem -> solver-policy
sidecar -> pre-solve persona input closure (realism/source-intent recipe/reviewed route/fact-oracle) ->
aggregate plus source-intent-refinement solution -> execution receipt or independently verifiable proof ->
final source plan -> suite`の一方向だけを許す。
policy SHAを先行problemへ逆流させず、self-hash fieldをcanonical bytesへ含めない。missing、duplicate、unused、
cyclic、foreign-persona referenceはfail closedとする。

bounded artifact上限は次を目標とする。すべて最大nesting depth 64、string 4,096 bytesとし、最終loaderは
bodyを読む前のframed byte capを持つ。現solver-policy sidecarの512 KiBはmaterialize済みvalueに対する
in-memory canonical capであり、framed loader安全性は未実装なのでloader blockerを解除しない。

- suite/fixture envelope: 2 MiB
- joint necessary problem: 4 MiB/suite（現在744,081 bytes）
- joint solver policy: 512 KiB/suite
- W0 persona plan: 16 MiB、最大16,000 W0 sources、20 scopes
- joint allocation execution receipt or independently verifiable proof: 8 MiB/person
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
solver_policy_bound              = false
route_affinity_matrix_review_receipt_bound = false
source_intent_refinement_policy_bound = false
joint_allocation_proved          = false
pilot_aggregate_cell_subset_proved = false
pilot_source_id_subset_proved    = false
pilot_materialization_subset_proved = false
pilot_byte_subset_proved         = false
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
2. generic aggregate-coreのobjective・軸・暫定上限を持つnon-authorizing solver-policy sidecar
3. 人物別`persona_realism_profile`/overlayと8軸台帳、pre-solve source-intent recipe/variant feasibility、
   reviewed route matrix、fact graph/oracle membership/独立query specのinput closure
4. full/pilot family/variant/scope/bucket/source quota/cohort aggregateとper-intent overlay assignmentの
   exact refinement、bounded canonical exact replayまたは完全proofによる最適性の検証、cycle-free final ID導出
5. P/X/Y/N/U history操作順、scope coverage、checkpoint exact projection
6. W0-W5全source/destinationのpath/basename collision、resource cap validation
7. v1 identity/goldenの非回帰
8. 20人を1人ずつbuildしたcanonical bytes/hashと16 MiB cap
