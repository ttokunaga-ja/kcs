# Persona-PC source-semantic resolution v2 提案

Status: **proposal-only / non-authorizing**。本書は契約候補の設計記録であり、G0、artifact
発行、最終 ID、namespace、folder/file 作成、render、write、history、Kio、evaluation 実行を
一切許可しない。

Date: 2026-07-17

## 1. 結論

現行の 20 persona / 203,000 W0 source slot には、2,100 target、200 companion、5,400 distractorを
収容する**物理slot cardinality**がある。ただし、既存成果物を変更しないadditive/versioned ownerを
追加すれば直ちにexact source-semantic closureになる、とはまだ証明できない。

現在の静的 feasibility baseline は、人物ごとの
distinct source candidate が最大 53、suite 全体で 1,060 に留まり、次をいずれも満たさない。

- `all_condition_exact_resolution_count == 0`
- `revision_exact_join_proved_count == 0`
- `checkpoint_selector_effective_membership_compiled_count == 0`
- target / primary / companion / distractor の four-domain disjointness が未成立

また、I5 の 100 target は contributor source として解決できない。各 persona の I5 は、
stable cross-scope move 4 件と W1-edited cross-scope move 1 件の exact 5 件である。現行の
source-matched lifecycle は、その 5 件を `incidental_searchable` かつ 32,768 bytes 以下の
source slot へ割り当て、別に `reserved_unused_semantic_anchor` を exact 5 件予約している。
frozen gate role は semantic overlay では contributor へ変更できないため、既存 I5 source の
上書きや再分類では closure を証明できない。

提案する解決は、元の I5 source 100 件を lifecycle support として保持し、予約済み contributor
anchor 100 件を一対一の query-bearing mirror として追加する方法である。これに加え、query と
oracle を一切参照しない **9-fact / 15,048-cell** の alternative capacity pool を corpus 側に先に構築し、
evaluation 側だけがその pool から distinct distractor 5,400 件を選ぶ。formal MVP ではこの9-fact案を
採用候補とし、stable 7-factへ縮小して1,440件のdynamic distractor factをevaluation側で別factへ
置換する案は不採用とする。後者はfrozen oracleのexact `distractor_fact_id`を弱め、hard-negative分布と
同一benchmark IDでの比較可能性を変えるためである。

独立設計監査で、capacity cell ID順とresidual source-slot digest順のsort/zipは、`K`とsource slotの
bijectionしか証明しないことが判明した。既存residual sourceはv2でtopic、language、present factsを
すでに持ち、axisの9 factsにはW0で`absent`、W1以降で`current`になるrevision factも含まれる。
したがってmappingだけをsemantic membershipと呼ぶのは禁止する。base factsのreplace policy、
canonical truth、source assertion occurrence、query relevance、selector visibility、renderer input、
payload equivalence、actual rendered bytesを別ownerで閉じるまでは、pre-solve candidate-domainのassignment countを
0に保つ。post-namespaceのsolution assignment単独もsemantic proofではなく、namespace v4へ入れない。
final source/history/evaluation planとauthoritative closureが閉じるまではresolution完了やG0へ使用しない。

現行の pin 済み成果物はすべて byte-for-byte unchanged とする。新しい corpus-side owner を
採用する場合は `corpus-semantic-namespace/v4` と complete projection inventory の additive
successor が必須であり、現行 namespace v3 や complete inventory v2 を再発行・再解釈しない。

## 2. 権限と境界

本提案時点の authority 値は次で固定する。

| field | value |
| --- | --- |
| `proposal_only` | `true` |
| `authorizes_g0_freeze` | `false` |
| `authorizes_artifact_issuance` | `false` |
| `authorizes_final_identifier_assignment` | `false` |
| `authorizes_namespace_issuance` | `false` |
| `authorizes_physical_write` | `false` |
| `authorizes_render_or_materialization` | `false` |
| `authorizes_history_mutation` | `false` |
| `authorizes_kio_execution` | `false` |
| `authorizes_query_rendering` | `false` |
| `authorizes_evaluation_execution` | `false` |

境界は次の一方向依存に限定する。

```text
frozen corpus owners
  -> query-independent capacity lattice
  -> query-independent truth/occurrence policy
  -> query-independent candidate domain (assignment count zero)
  -> corpus semantic namespace v4
corpus namespace + review/derivation evidence + corpus-scoped blocker projection
  -> pre-solve corpus evidence closure
pre-solve corpus closure + query/oracle owners + evaluation-scoped blocker projection
  -> pre-solve evaluation input closure
corpus namespace -> joint problem/solution/proof
  -> final source plan/transformation directives
  -> solution-compiled history plan/planned ledger
solution/history plan + evaluation input closure
  -> evaluation-only selector visibility + source-semantic resolution v2
planned ledger + corpus/evaluation/history/suite closures + full production blocker ledger
  -> G0 suite descriptor
```

query / oracle / answer / distractor selection は、evaluation-side resolution だけが参照できる。
それらは corpus-side source-slot eligibility/selection/assignment、source-ID preimage、corpus bytes、
capacity membership、I5 mirror assignment、effective reconciliation、namespace projection の
いずれにも影響してはならない。この禁止は evaluation-side が発行済み `A` から `D` を mapping
することまでは禁止せず、その mapping が corpus 側へ逆流することを禁止する。
この禁止は「生成器が直接 import しない」だけでなく、seed、sort key、digest、cache、環境変数、
中間 manifest を介した間接依存も含む。

## 3. 数量モデル

### 3.1 集合と exact cardinality

次の集合を区別する。

| symbol | meaning | exact count |
| --- | --- | ---: |
| `T` | abstract query-history target intent | 2,100 |
| `P` | non-I5 contributor primary source | 2,000 |
| `S` | original I5 incidental lifecycle-support source | 100 |
| `M` | reserved contributor mirror for I5 | 100 |
| `C` | companion source | 200 |
| `K` | query-independent alternative capacity cell | 15,048 |
| `A` | existing residual source intent capacity-assigned one-to-one to `K`; semantic application is separate | 15,048 |
| `D` | evaluation が `A` から選ぶ distinct distractor | 5,400 |

`K` と `A` の間にはcapacity上のbijectionがあり、cellとsource keyを混同しない。この時点では
`A`の既存bytes/topic/language/factsがcell semanticsを含むとは主張しない。以下の`D`とclosure cardinalityは、
effective-semantic plan、renderer、checkpoint reconciliationまで完成した将来状態の必要値である。
`D` は `A` の部分集合で、
`|A - D| == 9,648` を保つ。実際の resolution が参照する
distinct existing source は `P + S + M + C + D == 7,800` 件である。I5 support を除く
query-bearing semantic closure は `P + M + C + D == 7,700` 件、mirror 追加前の最低 closure
は `P + C + D == 7,600` 件である。corpus 側で所有する role/candidate population は
`P + S + M + C + A == 17,448` 件となる。

各 persona は target 105 件を持つ。内訳は contributor gate role の target 100 件と I5 support
5 件であり、100 contributor target のうち positive 85 件、negative 15 件、I5 5 件は positive
である。したがって 1 persona あたり positive 90、negative 15、suite 全体で positive 1,800、
negative 300 となる。各 positive に exact 3 distinct distractor を割り当て、negative には
distractor を割り当てないので、`1,800 * 3 == 5,400` である。

### 3.2 query-independent alternative pool

各 persona の pool は次の corpus-side 式だけで決める。

```text
4 topics * eligible_language_count * 9 facts * 11 replicas
```

同一 `(persona_id, topic_id, language, fact_id)` の最大 multiplicity は exact 11 である。
この 11 は query 数や oracle の answer 分布から導出せず、capacity-axis catalog の固定軸とする。
fact graph は 1 persona あたり 4 graphs、1 graph あたり exact 9 facts である。別の evaluation-side
read-only adequacy proof が、同一 tuple に対する oracle demand の最大値も exact 11 であることを
照合するが、その値や行順を corpus-side cell/source assignment の入力にしてはならない。

`available` は`full-residual` originだけから再計算する。expanded content-contextがcurrent、
`semantic_anchor_capacity=false`、`content_relation_role=independent`、`container_role_ids=[]`で、gate roleが
`contract_contributor`または`incidental_searchable`のslotから、同originのcontent-relation anchor/derivative、
attachment host/standalone-memberの全overlay reservation endpointを除く。suite算術は182,700 residualから
66,015 raw-onlyを除いた116,685 searchable、さらに42,156 reserved searchableを除いた74,529である。
この差分値を信頼せず、20 residual overlay originsを独立に開いてeligible/rejected digestを再構成する。

| persona | eligible languages | available | required cells | headroom |
| --- | --- | ---: | ---: | ---: |
| p01 | ja, en | 6,966 | 792 | 6,174 |
| p02 | en | 9,027 | 396 | 8,631 |
| p03 | ja, en | 5,310 | 792 | 4,518 |
| p04 | en | 5,652 | 396 | 5,256 |
| p05 | ja, en | 4,968 | 792 | 4,176 |
| p06 | en | 2,952 | 396 | 2,556 |
| p07 | en, fr, de, ja | 2,169 | 1,584 | 585 |
| p08 | ja, en | 2,124 | 792 | 1,332 |
| p09 | en, ja | 2,034 | 792 | 1,242 |
| p10 | en | 1,404 | 396 | 1,008 |
| p11 | en, es | 3,186 | 792 | 2,394 |
| p12 | ja, en | 8,712 | 792 | 7,920 |
| p13 | ja, en | 1,773 | 792 | 981 |
| p14 | ja, en | 1,890 | 792 | 1,098 |
| p15 | ja, en | 2,718 | 792 | 1,926 |
| p16 | ja, en | 2,700 | 792 | 1,908 |
| p17 | ja, en | 1,404 | 792 | 612 |
| p18 | ja, en | 4,374 | 792 | 3,582 |
| p19 | ja, en | 1,620 | 792 | 828 |
| p20 | ja, en | 3,546 | 792 | 2,754 |
| **total** | 38 persona-languages | **74,529** | **15,048** | **59,481** |

全 persona で `available >= required cells` が成立し、最小 headroom は p07 の 585、次点は
p17 の 612 である。ただし、これは現 pin に対する capacity existence 条件であり、artifact
発行、materialization、chunk 数、Recall、latency を証明しない。以下、この74,529件のpre-W5
full-residual candidate setを`E0`と呼ぶ。`E0`はcapacityの
上限候補であり、P/S/M/Cとの非交差、W5-current、既存event非参加、introduced W1-edit laneを加えた
assignment eligibilityではない。slot/lane ownerはこれらのquery-independent filter後に人物別件数を
再計算し、4 x language x 9 x 11の不等式を再証明しなければならない。現effective reconciliation v1は
W0-onlyで`post_w0_complete_membership_compiled=false`のため、W5-current filter後の件数は現在unknownである。
P/S/M/Cと既存compiled event participantsはpilot/event-created namespaceにあり、full-residual候補との
W0 intersectionは0だが、このorigin分離からW5 fitを推論しない。P/S/M/Cはsuite 2,400件、既存eventの
distinct source participantsは5,260件、そのunionは6,030件で、いずれも`E0`との交差はexact 0である。
したがってW0 event-free upper boundは74,529のままだが、W5 filter後の値ではない。

### 3.3 9-factの4-state policy

frozen fact graphのtruth stateと、物理sourceが現在主張するfact occurrenceを同じfieldへ畳まない。
additive ownerは次の4状態を別々に保持する。

ordered checkpoint IDはexact
`[W0, W1, W2, W3, W4, W5-pre-purge, W5-final]`の7件とする。`W1--W5`という略記から
6 checkpointへ縮約してはならない。

| state | owner / meaning |
| --- | --- |
| `canonical_truth_state` | corpus側。fact graphの`current / history-only / absent`をexact投影する |
| `source_assertion_occurrence_state` | corpus側。現在の物理source payloadがそのfactを主張するかを表す |
| `query_relevance_state` | evaluation側。oracleのanswerまたはexcluded distractorを表す |
| `selector_visibility_capabilities` | corpus history/Kio planとevaluation join。default / `--all-history` / `--include-deleted`で検索対象かを表す |

9-fact axisのquery-independent branchとexact countは次で固定する。

| branch | sources | W0 | W1--W5 |
| --- | ---: | --- | --- |
| stable | 11,704 | fact assertion、truth=current | 同じfact assertion、truth=current |
| superseded | 1,672 | fact assertion、truth=current | current stale assertionを維持、truth=history-only |
| introduced | 1,672 | neutral、対象graph factなし、truth=absent | W1 editでexact fact assertion、truth=current |

したがってW0 fact-bearingは13,376、W0 neutralは1,672、W1--W5 fact-bearingは15,048、
W1--W5 truth-currentは13,376、current stale prior assertionは1,672、introduced semantic editは
1,672である。superseded sourceは`semantic-alternative-stale-copy`であり、primary、companion、answerへ
使用してはならない。source occurrenceからtruthまたはrelevanceを推論しない。

全queryはW5-finalである。oracleが要求するprior distractor 720件は、default 480、
`--all-history` 120、`--include-deleted` 120に分かれる。prior occurrenceをW1以降history-onlyへ
消す設計ではdefault 480をhard negativeとして可視にできない。current stale copyとし、別の
evaluation-side selector-visibility ownerが5,400件すべての可視性を証明する。

## 4. I5 の不可能性と additive remediation

### 4.1 現行のままでは不可能な理由

I5 の source slot には lifecycle event と source identity の責務がある。一方、query-history
oracle の source-semantic resolution は contributor gate role と checkpoint-effective semantic
membership を必要とする。現行 100 slot は `incidental_searchable` であり、次の操作はいずれも
禁止する。

- frozen source-semantic membership の role を contributor として再解釈する
- overlay で gate role を上書きする
- I5 source intent key を新しい key に置換する
- query/oracle から contributor source ID を再生成する
- namespace v3 または effective reconciliation v1 の pin を更新する

したがって、source-matched lifecycle の 100 I5 source をそのまま primary contributor とみなす
方法では、2,100 target 全件の exact resolution を発行できない。

### 4.2 exact 100-mirror remediation

各 persona で、既存 I5 support 5 件と既存 reserved contributor anchor 5 件を一対一に結ぶ。
suite 全体では exact 100 pairs である。

mirror relation は少なくとも次を証明する。

- support は元の `incidental_searchable` source intent key と lifecycle event ownership を保持する
- mirror は既存 `reserved_unused_semantic_anchor` の source intent key を使用する
- mirror gate role は contributor であり、support の role を変更しない
- persona、topic、language、fact membership、revision selector、checkpoint visibility が exact match
- support と mirror の source intent key は異なり、一対一で、persona 間 reuse がない
- move/edit event は support が所有し、query-bearing source semantics は mirror が所有する
- evaluation row は support と mirror の両方を明示し、どちらか一方へ暗黙に畳まない

一致を証明できない pair が 1 件でもあれば fail closed とする。別の residual slot へ暗黙 fallback
せず、capacity 契約の additive revision を要求する。

## 5. 提案 artifact decomposition

名前は schema namespace 候補であり、本書から artifact ID や golden pin を発行しない。

| order | candidate owner | side | responsibility |
| ---: | --- | --- | --- |
| 1 | `source-semantic-capacity-axis-catalog/v1` | corpus | 4 topic、eligible languages、9 facts、11 replicas の lattice だけを定義する |
| 2 | `capacity-fact-truth-occurrence-policy/v1` | corpus | 9 factsのtruth、assertion occurrence、stable/stale/introduced branch、neutral payload、exact countsをquery非依存に定義する |
| 3 | `source-semantic-capacity-candidate-domain-{origin,profile,suite}/v1` | corpus | P/S/M/C・既存eventと非交差の74,529 pre-W5候補、W5 constraint、cell/lane assignment decision variablesをquery非依存solver inputとして定義する。sourceをcellへ割り当てない |
| 4 | complete projection inventory successor + `corpus-semantic-namespace/v4` | corpus | owner 1--3と既存content-only projectionだけをpinする。review/receipt、solution、final plan、query/evaluation ownerを収録しない |
| 5 | pre-solve corpus evidence closure + corpus-scoped blocker projection | corpus/evidence | namespace full body、derivation/review evidence、corpus-only historical blocker statusを束縛する。solution/evaluation依存claimは入れず、semantic namespaceやID preimageへreceiptを逆流させない |
| 6 | authoritative pre-solve evaluation input closure + evaluation-scoped blocker projection | evaluation | corpus closure、query intent、semantic oracle、evaluation-only blocker status、5,400 authored distractor requirementを束縛する。具体source assignmentはまだ持たない |
| 7 | joint problem + allocation solution/proof successor | solver | 15,048 distinct source-cell/lane assignments、W5 terminal constraints、1,672 W1 edit lane、P/S/M/C/A非交差をquery非依存に解く |
| 8 | final source plan + `source-semantic-capacity-transformation-directive/v1` | corpus plan | solutionを15,048 exact replace、authored topic/language/asserted fact、neutral/stale/introduced renderer inputへcompileする |
| 9 | solution-compiled planned history plan + planned ledger | history plan | ordered 7 checkpoints、baseline 7,630 + additive 1,672 events、105,336 truth/occurrence projections、I5 support/mirror relationをcompileする |
| 10 | `distractor-selector-visibility-eligibility/v1` | evaluation plan | evaluation closureとsolution/planned historyを下流joinし、5,400 distractorのW5 selector可視性を証明する |
| 11 | `query-history-source-semantic-resolution/v2` | evaluation plan | query/oracleを読める唯一のconcrete resolution owner。2,100 target、200 companion、5,400 distinct distractorをsolved sourceへ写像する |
| 12 | corpus closure equality/reuse + authoritative history/evaluation/suite closure successors | suite evidence | corpus projection不変ならclosure equality/reuse、変化時だけevidence-only corpus successorとし、final source/history/evaluation plan、blocker ledger、全completion gateを束縛してG0入力を閉じる |

candidate-domainのorigin/profile/suite decompositionでは、74,529 candidate row全体を無制限に複製しない。
validator が frozen pins からcandidate setを再計算し、ownerはpersona別candidate count/digest、
rejection count/digest、W5 constraint、suite aggregate proofを発行する。assignment countは0に固定する。

candidate-domainは`cell_semantics_applied_to_source=false`、`renderer_directive_available=false`、
`checkpoint_effective_membership_available=false`、`source_semantic_resolution_complete=false`を固定する。
rowはsource intent key、base topic/language、base `present_fact_set_key`、origin/shard coordinate、W0 eligibility、
W5 unresolved constraint、lane capabilityだけを持ち、capacity cell/topic/language/fact coordinateを持たない。
cell側はaxis owner、source側はcandidate-domain ownerとしてsolver problemで初めてjoinする。base present factsの
展開とexact replace判断はsolution後のtransformation ownerが
53本のfull-residual expanded fact-membership shardsをdirect dependencyとして各1回認証して所有する。
transformation ownerをnamespace v4へ収録せず、solution/final planからcontent namespaceへback-edgeを作らない。

candidate-domainのexact最小構成は29 candidate-domain JSONL、20 origin manifests
(`origin=full-residual`のみ)、20 full profile manifests、1 suite descriptorとする。JSONLは
`(persona_id, shard_ordinal)`でsubshardし、p02/p12は各3本、p01/p03/p04/p05/p18は各2本、残る13 personaは
各1本でexact 29本とする。各bodyは4,096 rows / 4 MiB以下で、first/last source-order digest、row count、
body bytes/SHAをmanifestへ束縛する。pilot domainは0件で、
空pilot artifactを作らない。full validationは53 full-residual source shards、53 expanded content-context
shards、20 residual overlay originsを独立に開く。

`query-history-source-semantic-resolution/v2` は corpus namespace に import しない。namespace v4 は
content-only owner 1--3のprojectionだけを完全列挙し、review/derivation receipt、solution/proof、final source plan、
renderer directive、compiled history、query/evaluation ownerを含めない。receiptはcorpus input closureへ入れる。
post-G0のactual body/chunk/history receiptはnamespaceへ含めず、別のevaluation-execution-ready closureが
runtime receiptを束縛する。namespaceからactual bytes/chunksを推論してはならない。complete inventory の現行 v2 は
byte-for-byte frozen とし、additive successor を新規発行するまでは namespace v4 を発行できない。
evaluation owner は persona ごとの exact 20 profile shards と 1 suite descriptor に分け、source reuse、
four-domain disjointness、distractor multiplicity、aggregate counts は suite descriptor で全 shard を
横断して証明する。persona 単独の proof から suite-global uniqueness を推論しない。

## 6. ID、canonicalization、domain separation

既存 `intent_key` は immutable source-slot key である。新しい source ID は作らず、query や oracle
を source intent key の preimage に入れない。capacity cell ID、mirror relation ID、evaluation row ID
は source ID とは別 namespace の record ID である。

capacity cell の論理 key は次の exact tuple とする。

```text
(persona_id, topic_id, language, fact_id, replica_ordinal)
```

`replica_ordinal` は string ではなく integer `1..11` である。`persona_id`、`topic_id`、`language`、
`fact_id` は pin 済み owner の lowercase ASCII stable ID を使い、表示名や query text を使わない。

候補 ID は次の framing で計算する。

```text
lower_hex(SHA256(ASCII(domain_label) || 0x00 || UTF8(canonical_json_array(tuple))))
```

canonical JSON array は fixed field order、NFC-normalized string、UTF-8、余分な whitespace なしとする。
digest は full 64 lowercase hex で保持し、truncation、base64、locale-aware sort を禁止する。

提案する domain label は次である。

| record | domain label |
| --- | --- |
| capacity cell | `kio/persona-pc-v2/source-semantic-capacity-cell/v1` |
| source-slot deterministic order | `kio/persona-pc-v2/source-semantic-capacity-slot-order/v1` |
| I5 mirror relation | `kio/persona-pc-v2/i5-contributor-mirror/v1` |
| evaluation row only | `kio/persona-pc-v2/query-history-source-semantic-resolution-row/v2` |

各 domain の exact tuple preimage は次とする。

| record | canonical JSON array tuple |
| --- | --- |
| capacity cell | `[persona_id, topic_id, language, fact_id, replica_ordinal]` |
| source-slot order | `[persona_id, source_intent_key]` |
| I5 mirror relation | `[persona_id, lifecycle_support_source_intent_key, contributor_mirror_source_intent_key]` |
| evaluation row | `[target_intent_key]` |

persona ごとに capacity cell は cell ID、candidate source intent key は source-slot order digest の
full bytes を ascending sortする。sort前にsource-slot order digestのsuite-wide collision countを検査し、
0でなければenumeration orderへfallbackせずfail closedにする。ただし同ordinalの一対一結合はpre-solve artifactで実行せず、W5 terminal、
lane、chunk/history constraintを満たすjoint solution/proofのdeterministic decision ruleとする。
残りの source はheadroomとして未割当のまま保持する。追加の format eligibility を導入する場合は
暗黙 filter にせず、
別 version の exact predicate と existence proof を要求する。この方式は dense Cartesian matrix を作らず、
query-independent で、runtime randomness、network、clock、filesystem enumeration order、Python hash seed
に依存しない。

solution内のcapacity-slot assignmentはsemantic equalityではない。assignment rowはbase topic、
base language、base `present_fact_set_key`とcapacity topic/language/factを保存するが、base present factsは
展開しない。両側が一致しなくてもassignmentは成立するため、暗黙のsemantic equalityを主張しない。
semantic application statusは`unreconciled-capacity-only-not-renderer-input`に固定し、別のeffective-semantic
final source planがbase membershipのsupersession規則とrenderer inputを証明するまで変更しない。

## 7. exact relational constraints

### 7.1 capacity candidate-domain gate

corpus側のpre-solve ownerが知ってよいのは次だけである。`T`、`D`、query/oracleを参照しない。

```text
|K| = 15,048
base capacity candidate count = 74,529
P/S/M/C or existing-event overlap count = 0
source-to-cell assignment count = 0
W5-current candidate count = unknown-not-owned-pre-solve
assignment authority = false
```

59,481はW0 filter前のconditional headroomであり、assignment headroomとして再利用しない。

### 7.2 joint solution capacity-slot/lane gate

joint problem/solution/proofはquery/oracleを読まず、次をexactに閉じる。

```text
|K| = 15,048
|A| = 15,048
assignment-eligible count after P/S/M/C, W5-live, and event-lane constraints >= 15,048
cell_to_source is a bijection from K to A
assignment source reuse count = 0
P/S/M/C/A overlap count = 0
introduced lane count = 1,672
stable-or-stale W5-current lane count = 13,376
```

ここまでのbijectionはsolution proofでありsemantic payload proofではない。solutionはbase present factsを
展開せず、source rowのbase `present_fact_set_key`だけを保持する。

### 7.3 final plan effective-semantic gate

truth/occurrence policy、transformation、reconciliationとpre-G0 final source/renderer planが次を所有する。

```text
|P| = 2,000
|S| = 100
|M| = 100
|C| = 200
|A| = 15,048
S is disjoint from P, M, C, A
P, S, M, C, A are pairwise disjoint
source_intent_key reuse count across P, S, M, C, A = 0
```

各`A`についてbase membershipをexact `replace`し、unionは0件とする。canonical truth stateはfact graphと
一致させる一方、source assertion occurrenceはstable / stale-copy / introduced branch policyと一致させ、
両者を同じfieldへ畳まない。language/topic policyが矛盾せず、renderer/final source planがcapacity directiveを
direct inputとして束縛されることを要求する。pre-G0ではdeterministic bounded render fixtureとsemantic
section/body digestまでを証明し、actual filesystem bytes/chunksは主張しない。

### 7.4 evaluation resolution gate

effective primary domainを`E = P union M`とし、evaluation側だけが次を所有する。

```text
|T| = 2,100
|D| = 5,400
D subset A
T, E, C, D are pairwise disjoint
```

各 target row は exact 1 effective primary を持つ。non-I5 row は `P` を、I5 row は `M` を primary
にし、I5 row だけが exact 1 `S` support を追加で持つ。companion が必要な authored target は exact 1
companion を持ち、その suite count は 200 である。

各 positive target は同じ persona、topic、language の distractor を exact 3 件持つ。各 distractor の
answer fact 集合は target の expected answer fact 集合と disjoint であり、3 件相互および suite 全体で
source reuse がない。各distractorはW5でauthored selectorから検索可能でなければならず、stale-copyを
primary、companion、answerへ使わない。negative target の distractor count は 0 である。

post-G0/write/index後は、actual body/chunk/history receiptをevaluation-execution-ready closureへ束縛し、
planned semantic sectionとactual searchable chunksの一致を独立attestしてから評価実行を許可する。

## 8. required proof fields と合格値

以下は将来の issued artifact が満たす候補値であり、現時点の completion claim ではない。

### 8.1 capacity axis / candidate-domain suite

| field | required value |
| --- | --- |
| `persona_count` | `20` |
| `topic_count_per_persona` | `4` |
| `fact_count_per_topic` | `9` |
| `replica_count_per_fact_cell` | `11` |
| `eligible_persona_language_pair_count` | `38` |
| `base_capacity_candidate_count` | `74_529` |
| `capacity_cell_count` | `15_048` |
| `base_candidate_minimum_persona_headroom` | `585` |
| `p_s_m_c_or_existing_event_candidate_overlap_count` | `0` |
| `w5_current_candidate_count` | `unknown-not-owned-pre-solve` |
| `source_to_cell_assignment_count` | `0` |
| `assignment_authority` | `false` |
| `capacity_cell_id_collision_count` | `0` |
| `source_slot_order_digest_collision_count` | `0` |
| `source_slot_query_or_oracle_dependency_count` | `0` |
| `capacity_cells_query_independent` | `true` |
| `cell_semantics_applied_to_source` | `false` in the capacity-only candidate |
| `base_semantic_membership_superseded` | `false` in the capacity-only candidate |
| `renderer_directive_available` | `false` in the capacity-only candidate |
| `checkpoint_effective_membership_available` | `false` in the capacity-only candidate |
| `rendered_semantics_attested` | `false` in the capacity-only candidate |
| `source_semantic_resolution_complete` | `false` in the capacity-only candidate |

suite descriptor は、persona ごとのconditional available/required/headroom、candidate-set digest、ordered cell
digest、W5 unresolved constraint、input pin mapを含める。assignment digestやsource reuse witnessを捏造しない。

### 8.2 truth/occurrence policy suite

| field | required value |
| --- | --- |
| `policy_fact_row_count` | `720` (`20 * 4 * 9`) |
| `capacity_cell_projection_count` | `15_048` |
| `checkpoint_ids` | ordered exact seven IDs |
| `stable_capacity_source_count` | `11_704` |
| `prior_capacity_source_count` | `1_672` |
| `introduced_capacity_source_count` | `1_672` |
| `aggregate_truth_current_projection_count` | `93_632` |
| `aggregate_truth_history_only_projection_count` | `10_032` |
| `aggregate_truth_absent_projection_count` | `1_672` |
| `aggregate_occurrence_fresh_current_projection_count` | `93_632` |
| `aggregate_occurrence_stale_current_projection_count` | `10_032` |
| `aggregate_occurrence_absent_projection_count` | `1_672` |
| `intentional_truth_occurrence_divergence_count` | `10_032` |
| `future_fact_before_introduction_count` | `0` |
| `slot_assignment_or_execution_claim_count` | `0` |

### 8.3 joint solution / assignment / event proof

| field | required value |
| --- | --- |
| `assignment_eligible_source_count` | exact solved value, persona-sharded |
| `assigned_alternative_source_count` | `15_048` |
| `assignment_minimum_persona_headroom` | `>= 0`, exact solved value required |
| `all_persona_capacity_inequalities_proved` | `true` |
| `p_s_m_c_a_overlap_count` | `0` |
| `assigned_existing_event_source_count` | `0` |
| `introduced_w1_edit_lane_count` | `1_672` |
| `stable_or_stale_w5_current_lane_count` | `13_376` |
| `every_capacity_cell_assigned_exactly_once` | `true` |
| `cell_to_source_bijection_proved` | `true` |
| `assignment_source_reuse_count` | `0` |
| `baseline_planned_event_count` | `7_630` |
| `additive_capacity_w1_edit_event_count` | `1_672` |
| `effective_planned_event_count` | `9_302` |
| `capacity_edit_existing_event_overlap_count` | `0` |
| `capacity_edit_source_reuse_count` | `0` |
| `persona_checkpoint_current_chunk_constraint_count` | `140` (`20 * 7`) |
| `ordered_checkpoint_current_chunk_targets_per_persona` | `[120_000, 120_000, 120_000, 120_000, 120_000, 124_800, 120_000]` |
| `persona_checkpoint_current_chunk_violation_count` | `0` |
| `persona_checkpoint_history_only_chunk_constraint_count` | `140` (`20 * 7`) |
| `ordered_checkpoint_history_only_chunk_targets_per_persona` | `[0, 24_000, 24_000, 48_000, 60_000, 64_800, 60_000]` |
| `persona_checkpoint_history_only_chunk_violation_count` | `0` |
| `query_or_oracle_dependency_count` | `0` |

1,672 editsは1 sourceにつきW1 exact 1 eventとする。別のevent encodingを採るなら、9,302を推論せず、
source-to-event mapping cardinalityとeffective totalをDecisionでversion-upする。

### 8.4 capacity transformation-directive suite

| field | required value |
| --- | --- |
| `capacity_assignment_binding_count` | `15_048` |
| `transformation_directive_count` | `15_048` |
| `base_present_fact_set_key_join_count` | `15_048` |
| `expanded_base_fact_membership_join_count` | `15_048` |
| `replace_policy_count` | `15_048` |
| `union_policy_count` | `0` |
| `authored_capacity_topic_language_fact_count` | `15_048` |
| `stable_assertion_directive_count` | `11_704` |
| `stale_copy_assertion_directive_count` | `1_672` |
| `introduced_neutral_then_assertion_directive_count` | `1_672` |
| `renderer_directive_count` | `15_048` |
| `renderer_content_state_binding_count` | `16_720` (`15_048` fact-bearing + `1_672` neutral) |
| `payload_equivalence_input_count` | `15_048` |
| `unresolved_transformation_count` | `0` |
| `query_or_oracle_dependency_count` | `0` |
| `checkpoint_effective_completion_claimed` | `false` |

transformation ownerは53本のfull-residual expanded fact-membership shardsを各trust sideで一度ずつ認証し、
各assignmentの`present_fact_set_key`をexact present factsへjoinする。全15,048 sourceをreplaceし、unionを
禁止する。checkpoint-effective truth / occurrence / selector stateはreconciliation ownerだけが所有する。

### 8.5 solution-compiled history reconciliation v2

| field | required value |
| --- | --- |
| `capacity_transformation_directive_binding_count` | `15_048` |
| `capacity_checkpoint_effective_source_count` | `15_048` |
| `capacity_checkpoint_state_projection_count` | `105_336` (`15_048 * 7`) |
| `canonical_truth_state_mismatch_count` | `0` |
| `source_assertion_occurrence_policy_mismatch_count` | `0` |
| `truth_occurrence_field_conflation_count` | `0` |
| `w0_fact_bearing_source_count` | `13_376` |
| `w0_neutral_source_count` | `1_672` |
| `w1_through_w5_fact_bearing_source_count` | `15_048` at each checkpoint |
| `w1_through_w5_current_stale_assertion_count` | `1_672` at each checkpoint |
| `introduced_w1_semantic_edit_count` | `1_672` |
| `aggregate_truth_current_projection_count` | `93_632` |
| `aggregate_truth_history_only_projection_count` | `10_032` |
| `aggregate_truth_absent_projection_count` | `1_672` |
| `aggregate_occurrence_fresh_current_projection_count` | `93_632` |
| `aggregate_occurrence_stale_current_projection_count` | `10_032` |
| `aggregate_occurrence_absent_projection_count` | `1_672` |
| `intentional_truth_occurrence_divergence_count` | `10_032` |
| `capacity_topic_language_policy_mismatch_count` | `0` |
| `capacity_lifecycle_event_gap_count` | `0` |
| `capacity_checkpoint_unresolved_source_count` | `0` |
| `i5_support_source_count` | `100` |
| `i5_contributor_mirror_count` | `100` |
| `mirror_count_per_persona` | `5` |
| `support_to_mirror_bijection_count` | `100` |
| `support_mirror_overlap_count` | `0` |
| `cross_persona_mirror_reuse_count` | `0` |
| `support_gate_role_mismatch_count` | `0` for expected `incidental_searchable` |
| `mirror_gate_role_mismatch_count` | `0` for expected contributor anchor |
| `semantic_tuple_mismatch_count` | `0` |
| `revision_selector_mismatch_count` | `0` |
| `checkpoint_visibility_mismatch_count` | `0` |
| `post_w0_checkpoint_membership_compiled` | `true` only in an accepted issued artifact |

proposal、candidate、negative fixture では最後の completion field を `false` に保つ。support と mirror
の record は、両 source intent key、persona、topic、language、fact IDs、revision chain selector、
checkpoint visibility、lifecycle capability、input pins を明示する。

### 8.6 evaluation-side resolution v2

| field | required value |
| --- | --- |
| `target_row_count` | `2_100` |
| `positive_target_count` | `1_800` |
| `negative_target_count` | `300` |
| `non_i5_primary_source_count` | `2_000` |
| `i5_support_source_count` | `100` |
| `i5_mirror_primary_source_count` | `100` |
| `companion_source_count` | `200` |
| `distinct_distractor_source_count` | `5_400` |
| `distinct_mapped_source_reference_count` | `7_800` |
| `distractors_per_positive_target` | `3` |
| `distractors_per_negative_target` | `0` |
| `max_distractor_demand_per_capacity_tuple` | `11` |
| `capacity_tuple_shortfall_count` | `0` |
| `authored_distractor_fact_substitution_count` | `0` |
| `distractor_selector_visible_count` | `5_400` |
| `distractor_selector_visibility_unresolved_count` | `0` |
| `prior_distractor_default_selector_count` | `480` |
| `prior_distractor_all_history_selector_count` | `120` |
| `prior_distractor_include_deleted_selector_count` | `120` |
| `distractor_answer_fact_overlap_count` | `0` |
| `distractor_source_reuse_count` | `0` |
| `target_primary_companion_distractor_disjoint` | `true` |
| `i5_support_mirror_disjoint` | `true` |
| `all_condition_exact_resolution_count` | `2_100` |
| `checkpoint_selector_effective_membership_compiled_count` | `2_100` |
| `unresolved_target_count` | `0` |

各 row は `same_persona`、`same_topic`、`same_language`、authored distractor fact exact、expected answer fact
subset、revision chain exact、truth state、source occurrence、W5 selector visibility、event-profile capability
subset を個別 boolean と digest で証明する。
`revision_exact_join_proved_count` は数を推測して固定せず、
`authored_revision_selector_nonempty_count` と exact equality を要求する。

### 8.7 namespace successor

| field | required value |
| --- | --- |
| `namespace_schema_version` | `4` |
| `legacy_v3_pin_changed` | `false` |
| `new_corpus_owner_projection_missing_count` | `0` |
| `evaluation_resolution_projection_count` | `0` |
| `solution_or_final_plan_projection_count` | `0` |
| `review_or_derivation_receipt_projection_count` | `0` |
| `query_or_oracle_field_leak_count` | `0` |
| `projection_body_pin_mismatch_count` | `0` |
| `independent_full_replay_passed` | `true` before issuance |
| `two_hash_seed_cold_builds_passed` | `true` before issuance |

namespace v4 は、このtableのnamespace-only gateを通るまではabsentのままとする。namespace v3のschema、
bytes、SHA、projection order、意味を一切変更しない。

### 8.8 post-namespace authoritative closure successors

| field | required value |
| --- | --- |
| `corpus_input_closure_positive_independent_review_present` | `true` |
| `corpus_scoped_blocker_projection_bound` | `true` |
| `evaluation_scoped_blocker_projection_bound` | `true` |
| `blocker_scope_projection_overlap_count` | `0` |
| `full_blocker_ledger_bound_by_g0_descriptor` | `true` before G0 |
| `query_dependent_pin_count_in_corpus_blocker_projection` | `0` |
| `query_only_change_corpus_input_closure_change_count` | `0` |
| `corpus_input_closure_complete` | `true` before G0 |
| `evaluation_input_closure_complete` | `true` before G0 |
| `solution_compiled_history_closure_complete` | `true` before G0 |
| `query_history_source_semantic_resolution_v2_bound` | `true` before G0 |
| `suite_input_closure_complete` | `true` before G0 |
| `active_g0_unresolved_count` | `0` before G0 |
| `planned_ledger_bound` | `true` before G0 |

このtableはnamespace発行後の別artifact gateであり、namespace canonical bodyやsource-ID preimageへ
closure/evidence statusを入れない。production successorではfull ledgerからcorpus/evaluation scope projectionを
deterministically導出し、full-ledger pinとprojection-derivation receiptはsuite/G0側だけが束縛する。
corpus closureはcorpus projection bytesだけを束縛するため、query-only pin変更で変化しない。既存のfrozen
bootstrap/request-only ledger/closureをこのsplitとして再解釈せず、additive schemaで実装する。

## 9. frozen dependency pins

以下は 2026-07-17 に repo の producer、independent validator、test、下流 dependency map を
read-only で照合した baseline literal である。repo には汎用 persisted `artifact_id` がないため、
binding 名、artifact schema/version、canonical bytes、full SHA-256 の組で識別する。

| binding | artifact schema | ver | bytes | SHA-256 |
| --- | --- | ---: | ---: | --- |
| `persona-v2-source-inventory-layout` | `kio.persona.pc-source-inventory-layout/v2` | 2 | 274,566 | `81fcec92df932d9357b5202a6eda3f6c11ac9bd70762a281cbc2d094d6e8579a` |
| `persona-v2-source-inventory-suite` | `kio.persona.pc-source-inventory-suite/v2` | 2 | 45,887 | `9f216f3d986bdc92f7b07e0d2bfe266dc03df46d990f8ded706ad802d227edc3` |
| `persona-v2-overlay-reservation-suite` | `kio.persona.pc-overlay-reservation-suite/v2` | 2 | 21,680 | `11d042775faebf353a284aad18d137d2735bfd0e29b528666a19d14a008f2c3d` |
| `persona-v2-source-instance-parameter-assignment-suite` | `kio.persona.pc-source-instance-parameter-assignment-suite/v2` | 2 | 72,535 | `ed95d7875cb961d4fa054f6fa8a8a281cf6906724bc5f2524d9d046b2c3e8f1a` |
| `persona-v2-format-implementation-registry` | `kio.persona.pc-format-implementation-registry/v2` | 2 | 333,881 | `59ae0b2e5c755732e6937e70ada4b243ea2c7432a9ce654c7e9c219b4a13bc5d` |
| `persona-v2-formal-source-recipe-profile-catalog` | `kio.persona.pc-formal-source-recipe-profile-catalog/v2` | 2 | 386,152 | `0ac0906397c8d81b7504637fe119d45ae2ffa7acb7cb47b719c985121ce1b2df` |
| `persona-v2-source-semantic-membership-catalog` | `kio.persona.pc-source-semantic-membership-catalog/v2` | 2 | 436,495 | `d54ad435447a6b7adf87c0190bd8ed452caa3015b82ac18da1c81825efeba63b` |
| `persona-v2-source-semantic-membership-suite` | `kio.persona.pc-source-semantic-membership-suite/v2` | 2 | 49,837 | `62394dd2a3544f7d6c332652e6799b7a60353e8e3aa6a87f80e0ff21590a2e28` |
| `persona-v2-lifecycle-demand` | `kio.persona.pc-lifecycle-demand/v2` | 2 | 463,571 | `372a466e3994c9e41662457f144fc03338d96b76f57f9306e62bbe9511422005` |
| `persona-v2-lifecycle-coverage-catalog` | `kio.persona.pc-lifecycle-coverage-catalog/v1` | 1 | 1,385,596 | `1760eeed4bde8c7a1c2c720a437fb4c3d62971af3f2159e768696e938389b9d4` |
| `persona-v2-source-matched-lifecycle-suite` | `kio.persona.pc-source-matched-lifecycle-suite/v1` | 1 | 14,605 | `c4508ed61c88db80b003e9ce3b7c35ea153776442bd3224964897400633dd2c8` |
| `lifecycle-effective-membership-reconciliation-v1` | `kio.persona.pc-lifecycle-effective-membership-reconciliation/v1` | 1 | 69,195 | `14ff220bf47656965d1ac1803a0dd0ccc6b8afa440b64f563e40e623a219bb7c` |
| `query-history-target-resolution-v1` | `kio.persona.pc-query-history-target-resolution/v1` | 1 | 4,478,576 | `fbb0fd1a78d034fcd1777a6aaf0e7ee9bc21d07255f2ce9c7d5fc9761dc11593` |
| `query-history-semantic-resolution-feasibility-audit` | `kio.persona.pc-query-history-semantic-resolution-feasibility-audit/v1` | 1 | 40,947 | `890ce6510d9baa4b5faf533cb927bd296f12e289247bb63f88ee2303565af136` |
| `complete-semantic-projection-inventory-v2` | `kio.persona.pc-semantic-projection-derivation-inventory/v2` | 2 | 697,466 | `6826fb14293e7147159fae1849f93533c35ae76f1beecbd093d190cd6ddd3e69` |
| `corpus-semantic-namespace-v3` | `kio.persona.pc-corpus-semantic-namespace/v3` | 3 | 161,665 | `a8bc67e182ff57b64ae6df0f97bd5be31faf6e5f7b7cfbd0bc3f1ba7bc5cc509` |

`query-history-target-resolution-v1` は frozen baseline input にすぎない。feasibility audit 自身が
`query-history-target-resolution-v2-not-issued` を記録しているため、v1 pin を v2 artifact として
再利用してはならない。namespace v3、complete inventory v2、matched lifecycle v1、effective
membership v1 の structural 4-pin canonical bytes 合計は 942,931 だが、これは W0 structural
context であり、missing exact source-semantic resolution の代替証拠ではない。

## 10. bounded validation / cost budget

本提案では code 実装、artifact build、full replay、cold build、folder/file 作成、重い test を実行しない。
採用後の contract-first implementation は次の bound を先に固定する。

| gate/resource | proposed hard cap |
| --- | ---: |
| fast pin/schema/leakage gate | 30 seconds、512 MiB RSS |
| all-new-owner independent full replay | 21,600 seconds、1 GiB RSS |
| isolated cold build seed 0 | 21,600 seconds、1 GiB RSS |
| isolated cold build seed 1 | 21,600 seconds、1 GiB RSS |
| each descriptor | 2 MiB canonical bytes |
| each JSONL shard | 4 MiB、4,096 rows |
| candidate-domain row | 1,024 LF-inclusive bytes |
| solution capacity-assignment row | 1,024 LF-inclusive bytes |
| each persona solution/proof aggregate | 8 MiB |
| I5 reconciliation row | 2,048 LF-inclusive bytes |
| evaluation resolution row | 4,096 LF-inclusive bytes |
| cumulative new external bodies | 256 MiB |

全 body は file-size bound を parse/copy 前に検査し、JSONL は row count と LF-inclusive row bytes を
streaming で検査する。full gate は各 trust side で各 body を exact 1 回 authenticate し、同じ body の
重複 full traversal を禁止する。provider callback 前後と final postflight で caller、direct owner、
opening-image pin を再認証し、mutable object alias と TOCTOU を fail closed にする。

candidate preprocessing は suite-wide 15,048 cells と最大74,529 base candidatesをpersona partition内で
filterし、canonical orderへ並べる処理に限定する。この前処理だけを
`O(K log K + E log E)`、working set `O(E)` 以下とし、`K=15,048`、`E<=74,529` とする。
joint assignmentそのものをsort/zipだけで解けるとは主張しない。assignmentはsolver-ownedであり、
canonical solution/proofを再生可能に発行し、上表のall-new-owner/cold build各21,600秒・1 GiB RSSと、
personaごとのsolution/proof合計8 MiB capに従う。query/evaluation inputはsolverへ渡さない。
将来、決定的なconstructive reductionが別途証明された場合に限り、そのsolver計算量をtightenできる。
`15,048 * 74,529` の約 11.2 億 edgeは上限でもdense matrixとして作らない。evaluation proof は 2,100 target と
7,800 distinct mapped source reference に対して linear に検査する。

二つの cold build は isolated process、empty output、`PYTHONHASHSEED=0` と `1`、`LC_ALL=C`、
`LANG=C`、`TZ=UTC` で行い、canonical bytes、full SHA-256、row order、proof aggregate が exact
一致することを要求する。初回実測後に time/RSS cap を緩めず、保守的に tighten する。

## 11. adoption sequence

これは folder/file materialization や history campaign の前段にある source-semantic contract
closure である。採用する場合も次の順を崩さない。

1. 独立review後、9-fact、substitution 0、4-state policy、replace-only、ordered 7 checkpoints、field allowlistを採用Decisionで先に固定する。ここではG0にしない。
2. producerより先にindependent schema/pin/leakage/domain/negative contract testsを追加する。
3. query-independent capacity-axis catalogを作り、20-person tableと15,048-cell digestを検証する。
4. truth/occurrence policyを作り、720 policy rows、3 branch、105,336 projection aggregateを検証する。
5. query-independent candidate-domainを作り、74,529 pre-W5 candidates、P/S/M/C/event overlap 0、W5 unresolved constraint、assignment 0を証明する。
6. owners 1--3のcontent-only projectionをcomplete inventory successorとnamespace v4へexactly once収録する。solution、final plan、receipt、query/evaluation ownerは収録しない。
7. positive review、projection-derivation receipts、corpus-scoped blocker projectionをpre-solve corpus evidence closureへ束縛する。solution/evaluation依存entryやfull ledger pinを入れず、G0-authoritativeとは呼ばない。
8. pre-solve corpus closure、query intent、semantic oracle、evaluation-scoped blocker projection、5,400 authored distractor requirementsをpre-solve evaluation input closureへ束縛する。具体source mappingは0で、solverはこのclosureをimportしない。
9. namespaceだけを入力にjoint problem/solution/proofを解き、15,048 source-cell/lane assignment、W5 terminal fit、P/S/M/C/A非交差、1,672 W1 edit lane、chunk/history constraintsを証明する。
10. solutionからfinal source plan、15,048 transformation directives、deterministic renderer contract、bounded render-fixture proofを順にcompileする。
11. solution/final planからbaseline 7,630 + additive 1,672 = 9,302 planned events、105,336 truth/occurrence projection、I5 support/mirrorをcompiled history planとplanned ledgerへ束縛する。
12. evaluation closureとsolution/planned historyを下流joinし、5,400 selector-visible distractorsとquery-history source-semantic resolution v2を発行する。corpus/solutionへback-edgeを作らない。
13. downstream pinsでfull production blocker ledgerを更新し、scope別projectionを再生成する。corpus-only projectionが不変ならcorpus closureはbyte-identicalに保ち、evaluation projection、authoritative history/evaluation/suite closure successorsを再構築して`active_g0_unresolved_count == 0`を閉じる。namespaceとsolutionは不変とし、query-only changeによるcorpus closure change countを0にする。
14. planned ledger、corpus/evaluation/history/suite closures、blocker ledgerをG0 suite descriptorへ束縛し、別のissuance Decision後にG0を判定する。
15. G0後にfolder/file作成、ordered 7 checkpointsの編集/history、3 fresh replayを実行し、actual body/chunk/history receiptを束縛する。
16. evaluation-execution-ready closureを発行してから検索・性能検証へ進む。

steps 3--13の各versioned ownerは、次ownerへ進む前にそれぞれ
`fast -> pre-freeze full -> cold seed 0/1 -> producer/validator golden freeze -> fast -> post-freeze full -> independent review`
を完了する。全ownerを作った後に一括でfull/coldを回す順序は禁止する。

各段階で input pin mismatch、query leakage、cardinality mismatch、domain overlap、I5 mismatch、body cap
超過が 1 件でもあれば停止する。旧 artifact を修正して通す fallback は設けない。

## 12. priority risks

| priority | risk | required response |
| --- | --- | --- |
| P0 | query/oracle が corpus-side selection、ID preimage、bytes、membership、namespace へ逆流する | import/read-set/field allowlist/leakage test で fail closed |
| P0 | solution、final source plan、compiled history、review/derivation receiptをcontent-only namespaceへ入れてhash cycleを作る | namespaceはpre-solve content projectionだけに限定し、receiptはcorpus closure、solution/final/historyはnamespace後のplanned DAGへ置く |
| P0 | corpus/evaluation/history/suite closureまたはblocker ledgerを飛ばしてG0へ進む | planned ledgerと全authoritative closure、`active_g0_unresolved_count == 0`をG0 descriptorの必須入力にする |
| P0 | stable 7-factへ縮小し、1,440件のauthored dynamic distractor factを別factで解決済みとする | 9-fact / 15,048 axisを維持し、authored fact substitution count 0を要求する |
| P0 | capacity slotへのsort/zipを、そのsourceがcell topic/language/factを実際に含むsemantic proofとして発行する | assignmentをcapacity-onlyに限定し、base/capacity coordinatesと全false semantic statusを保持。transformation/effective ownerとpre-G0 renderer proofまでsemantic planへ昇格せず、actual証明はpost-G0 receiptまで禁止 |
| P0 | canonical truthとsource assertion occurrenceを同じvisibility fieldへ畳む | additive 4-state ownerを作り、truth/occurrence/relevance/selector capabilityを別fieldとdigestで証明する |
| P0 | W0 introduced factを先取りする、またはbase 8 factsとのunionでanswer-fact overlapを隠す | introduced 1,672はW0 neutral、全15,048をreplace-onlyとし、evaluationはfull occurrence setでdisjointnessを再計算する |
| P0 | stale alternativeをprimary、companion、answerへ使う | `semantic-alternative-stale-copy` roleとevaluation-side exclusionをexactに検証する |
| P0 | selector visibility ownerなしで5,400 hard distractorをresolvedと発行する | W5 exact selector可視性5,400、unresolved 0を別ownerで証明する |
| P0 | I5 incidental role を semantic overlay で contributor とみなす | support/mirror を分離し、100-pair bijection と role pin を検証する |
| P0 | distractor source reuse、answer-fact overlap、four-domain collision | suite-global exact set proof と collision witness を必須にする |
| P0 | namespace v3 / complete inventory v2 / frozen owner を再発行する | additive schema のみ許可し、legacy full pin equality を gate にする |
| P0 | dense matching、unbounded body/provider replay で memory/time を枯渇させる | bounded sparse/canonical preprocessing、deterministic solver、streaming bounds、one-full-traversal、hard cap を強制する |
| P1 | revision selector と checkpoint-effective membership の join が曖昧になる | authored selector count equality と 2,100-row checkpoint proof を要求する |
| P1 | 74,529 base candidateをP/S/M/C、W5-live、event-lane filter後のassignment capacityと誤認する | slot assignment前に人物別eligible setを再計算し、全20 inequalityとoverlap 0をfreezeする |
| P1 | introduced W1 editを既存eventへ暗黙に重ね、凍結event countを変える | joint source/history successorで1,672 editと既存event非衝突を解き、event countを明示する |
| P1 | canonical framing、Unicode、integer/string 差で ID が drift する | fixed tuple、NFC、NUL framing、full SHA、two-seed cold build を固定する |
| P1 | persona language pool や 4 x 9 x 11 軸が upstream drift する | full dependency pin と persona table digest を再認証する |
| P1 | callback/cache alias、TOCTOU、duplicate validation が proof を弱める | immutable bytes cache、callback 前後再認証、trust-side traversal count を検査する |
| P1 | planned semantic closureへactual chunk attestationを要求してG0/writeとの循環を作る | pre-G0 deterministic render fixture proofとpost-G0 actual body/chunk/history receiptを別closure・別authorityにする |
| P2 | filter前headroomがp07 585、p17 612に集中する | future language/fact/replica 追加を in-place で行わず capacity version を上げ、filter後headroomを別値として報告する |
| P2 | descriptor/row が肥大化して観測不能になる | sharding、field allowlist、2 MiB/4 MiB/256 MiB cap を維持する |
| P2 | CI が fast だけを通し full/cold gate を忘れる | issuance workflow で full と two-cold receipt を required input にする |

## 13. 明示的に変更しないもの

本提案は、前節の dependency pin table にある全 artifact、既存 source intent key、203,000 W0 slot、
source inventory、overlay reservation、parameter assignment、format registry、formal recipe、source semantic
membership v2、lifecycle demand/coverage、source-matched lifecycle v1、effective reconciliation v1、
query target v1、feasibility audit v1、complete inventory v2、namespace v3 を byte-for-byte 変更しない。

さらに、query text、oracle answer、golden query、corpus bytes、file format 比、folder nesting、chunk plan、
history event、Recall、latency、cost、実データ dogfood の結果を本提案から生成・変更・達成済みと推論しない。
新 corpus-side owner の本番採用・authoritative consumptionにはnamespace v4が必須だが、個別owner候補の
local freezeはその上流で行う。namespace v4は本書では未発行である。
