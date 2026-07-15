# Persona-PC fidelity v2 G0 contract

Status: envelope、exact topology、joint必要条件problem、generic aggregate-core solver-policy、
20人別realism profile/overlay marginal、71 variant identity/566 persona marginal catalog、541-row route候補、
20人x4 typed fact-graph leaf、negative route-review receipt、20人各1件のrepresentative
source-intent/fact-membership/history-intent、2,100 query intents/semantic oracle、非authorizing input-closure候補まで実装済み。
exact 203,000-key/73-shard source-inventory layout、overlay contract、ID-free contributor text/PDF renderer/validator、
別下流の11 incidental-format renderer/standalone validator、
source-profile catalogも候補実装があるがnon-authoritativeである。さらに下流のstructural
source packageは203,000 reference-only rows、73 canonical JSONL shard bodies、40 origin manifests、
40 pilot/full profile manifests、71 inventory-only profile IDsを束縛する。さらにsource-owned W0
semantic-membership packageは、各人45 fact profiles（suite 900）、80 persona-local topics、
71 semantic profiles、3,733 compact rowsから全203,000 sourceのcontent contextとpresent-fact setを
logicalにtotal-resolveする。さらに下流のconcrete-overlay membership packageはreservation、structural source、
semantic/fact manifestsをdirectにjoinし、40 origin + 40 profile manifests、25,560 draft memberships、
2,100 disjoint anchorsを27,660 rich rowsで束縛する。source-inventory layout自体はrow body/body SHAを持たない。
overlayのmembership schemaは候補として固定した一方、8軸ledgerはaxis draftで、byte/host-metadata整合と
scope placementが未完成である。unordered W0-current fact pairとsource-owned distinct A/B branch profiles、
reservation/sourceとのpre-solve joinは実装済みだが、raw rendition、observed search participation、scope assignmentがないため、
conflict overlayの実ファイル・検索上のrealizabilityは未証明である。
必要条件は全20人で通過し、structural row bodiesとnarrow semantic/fact projectionは完成した。上流の凍結済み
inventory catalogではformal recipe slot 71件をunboundのまま維持する一方、下流の非authorizing catalogで
71 variant-level recipe profile policyをinventory/semantic/renderer/validator slotへ1対1に束縛した。
凍結済みsource-profile catalogの10 local-ready / 61 missingは歴史的snapshotとして維持し、後続の
incidental-text 11件とraw-only 50件を局所実装した。all-71 implementation registryが8 pairs、
16 contract bodies、71 ownership rows、213 runtime probesを束縛し、現在の下流形式実装可用性と
variant-level recipe policyは71 / 71である。ただし203,000 source-instance recipe値は未束縛である。
下流のaggregate byte-distribution catalogは566 persona-variant行、300 persona-family投影、20 persona集計で
pilot/full-residual/fullの件数、complexity histogram、raw-byte sum、nearest-rank p50/p95/max、formal tailを
exactに束縛した。ただしsource-instance別parameter assignmentとactual allocated bytesは未束縛である。
20 persona/20 primary use-case catalogもexact 1対1とrole/family/representative primary scope/lifecycle/query
joinを束縛し、30,008 canonical bytes、SHA-256
`024916c0d79d30ce859d102ae0e30f34f5209f0665b587151f2c0b410df77624`である。
`kcs.persona.pc-chunk-accounting/v1`はscope-qualified endpoint、global hash、history path binding、physical
storageを分離し、19,801 canonical bytes、SHA-256
`d9c59e922a2619b1748194241ffdf47ace3eb034f136b0d04154163bda3ccea2`である。そのexact move rowをdirect inputに
持つ`kcs.persona.pc-lifecycle-demand/v2`は20 x 105 anonymous capabilitiesとsymbolic W1--W5 demandを
束縛し、463,571 canonical bytes、SHA-256
`32e0aaf88632803d41266152b81e2cc2917111d69f6dfb03be0621920c8a0080`である。ただしsource matching、W0 actual
qIM、compiled history plan、observed receiptsはfalseである。別laneの
`kcs.persona.pc-recursive-robustness-lane-catalog/v1`は76,099 canonical bytes、SHA-256
`49d6fa26cafa902bfca4a102c5e301c27683fd6761bc456a3930cd059f67a4f2`で、actual host case modeと
materializationは未束縛である。
overlay scope placement、
独立approval receipt、schema別content-only semantic projection、
実行可能solver、solution、proofは含まない。現input-closureはfull body DAGの互換性候補に限り、
source ID namespaceとして不適格である。
`g0_contract_frozen=false`、G0 root未実装、非authorizing。
現行`kcs-persona-pc-v1`、そのartifact、golden hash、writer、history planを変更しない。

Date: 2026-07-15

## 1. 目的とversion境界

v2は20人の独立したsynthetic PCを、人物ごとに20 active leaf scopes、120,000 current
contract-contributor chunks、W5 finalで180,000 current+history contract chunksとして計画する。
人物間のfile/chunk poolingは禁止する。

1 replayは20個の独立persona-PC rootsを持ち、各rootは12 primary + 8 persona-specific secondary scopesを
持つ。logical personasは常に20人であり、3 replayでも60人とは呼ばない。W0は203,000 source files/replay、
3 fresh-storage replayを保持すると60 physical roots、1,200 scopes、609,000 W0 source filesになる。
これはcardinality契約であり、pilot実測とdestination readbackなしにcapacity feasibilityを主張しない。

20 personasは20 rolesだけでなく20 distinct primary use casesとexactly one-to-oneでなければならない。
G0入力は各行に`persona_id`、`primary_use_case_id`、trigger/outcome、required family、required scope role、
required lifecycle capability、required query stratumを持ち、persona/use-case IDの双方が重複せず全20件を覆う。
全員へ共通M3-1/M3-2/M3-3回帰を課すことは、この人物別primary use-case coverageの代替にならない。
具体的な20-row候補は提案書§3.3を正とし、machine-readable artifactと独立validatorは実装済みである。
ただしsource-instance/query targetへの解決とG0 rootへのbindingは引き続きblockerとする。

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

正式な実行順は、plan freeze後、**初回を含む合計3つ**のfresh storageそれぞれで、20人を1人ずつW0
folder/file生成 -> 全scope W0 offline index/attestation -> W1-W5 edit/lifecycle mutationを実行する。
完成rootはcopyせず、各replayを同じplan/eventからW0より再生成する。3 replayすべての完了後に、
構造・比率・chunk/history・query・capacityを検証する。4回目のreplayはこの契約に含めない。

W0とW5 finalではpersona x replayごとにobserved structural/materialization receiptを必須とする。
このreceiptはfamily/variant/gate-role件数、scope別file数、file/directory depth histogram、
unique prefix数、max fan-out、extension/magic/MIME/disposition/validator結果、raw/allocated bytes、
inodes、人物・family別p50/p95/max/tail、path/casefold collision、リンク/クローン/共有inode不在を束縛する。
suite poolingによる相殺は禁止し、各20人 x 3 replayが個別にplanと一致しなければならない。

## 2. lane境界

1つの小さなsuite descriptorが、次の3つの独立したversioned lane spec hashを束縛する。

| lane | replay | formal chunk母数 | history | authority |
| --- | ---: | --- | --- | --- |
| `formal-retrieval-history-v2` | 3 fresh-storage deterministic replays | 含む | W0-W5 | G0はplanned only |
| `recursive-robustness-v1` | 1 separate-manifest replay | 含めない | 代表操作のみ | formal評価を代替しない |
| `byte-stress-v1` | 1 W0-only | 含めない | なし | capacity/I/O専用 |

robustness entryとbyte-stress entryをformal family ratio、scope count、chunk count、Recall queryへ
混ぜない。各laneは別root、別manifest、別receiptを持つ。
formalのネストは`home/`からleaf scopeまでD2--D6とし、managed fileはleaf直下だけに置く。
recursive robustnessはD6--D8とし、中間directoryのfile、partial/cache/conflict/case/Unicodeを含める。
両者は他方の代用にならず、formalは人物別file/directory depth histogram、unique prefix数、
max fan-out、scope file数、collision 0を、robustnessはcandidate/実現/不実現数とtraversal/除外結果を
別のobserved receiptで読み戻す。
robustnessのdepthはlane root直下`ambient-home/`からfileの親directoryまでのcomponent数とする。
1 personaあたり256 file candidates、128 authored directoriesを持ち、candidate categoryはbenign 102、
exact/near/conflict copy 38、cache/temp 38、partial download 26、hidden/lockfile 26、empty 13、
Unicode/case-collision 13へexact整数化する。20 personaのpath/depth vectorを複製せず、suite全体でD6/D7/D8を
すべて実現し、人物別planned/realized Dmaxを一致させる。native filesystemで実現不能なcase collision等は
manifest-only expected failureとしてcandidate/realizedを分け、作成済みfileへ数えない。このliteral 20-person
depth/path tableは`kcs.persona.pc-recursive-robustness-lane-catalog/v1`へ実装済みである。suite file-depthは
D6=2,855 / D7=1,901 / D8=364、planned Dmax人数は8/9/3で、bodyは76,099 canonical bytes、SHA-256
`49d6fa26cafa902bfca4a102c5e301c27683fd6761bc456a3930cd059f67a4f2`である。target OS/case modeは
metadata-only、native host case modeはunboundとし、各人253--256の実現範囲をactual receiptで閉じる。
formal 100k母数へ混ぜず、materialization/write/G0 authorityはfalseである。
byte-stress catalog projectionはformal variant source rowではなく、format encoding/validator identityだけを
参照する。lane-local gate roleは常に`raw_only`、requested chunks 0、observed gateはactual chunks 0とする。
expanded 8 MiB上限のcontainer encodingはsmall/medium size classだけ、large/tailはnon-containerだけを許す。

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
hash-spreadを使わない。domain-separated hashはreview/query/evidenceを含まないpre-solve
corpus semantic namespaceと、解かれた
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
members、chunksではない。これは観測された実PC統計ではなくstress-design仮説である。whole-source cohortと
searchable contributor densityの必要条件を満たす最終feasibility correctionでは、
p08をmd/text-PDF/docx/pptx=14/16/12/12%、
p11をmd/text-PDF/docx/pptx=5/19/11/8%、p15をmd/text-PDF/scan-PDF/docx=7/23/5/17%、
p17をmd/text-PDF/scan-PDF/xlsx/domain-binary=7/24/9/8/12%とする。p02のdomain family内は
PCAP/JSONL.GZ=30/70、p17はIFCZIP/CDE-ZIP=40/60とする。suite fullのexact family totalsは次である。

```text
md=19,660              txt_log=19,210       code=10,440
structured=15,310      csv_tsv=18,680       html_eml=14,430
ipynb=2,240            pdf_text=29,680      pdf_scan=11,200
docx=16,490            xlsx=15,270          pptx=10,180
image=11,380           media=2,150          domain=6,680
```

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

DICOMはMulti-frame Grayscale Byte Secondary Capture Storageの`.7.2` SOP Classに固定し、Part 10
metaとdatasetのSOP Class/Instance UID一致、必須Patient/Study/Series/SC/Multi-frame要素、全frameを
列挙するPage Number Vectorとそれを指すFrame Increment Pointer、complexityごとに異なる決定的SOP
Instance UID、native 8-bit MONOCHROME2 pixel長を独立validatorで検査する。

現envelopeに加え、`kcs.persona.pc-variant-catalog/v2` sidecarは71 identity、566 persona marginal、
content MIMEとKCS path MIME、形式別complexity unit、formal/byte-stress lane境界を機械化した。
canonical bodyは211,733 bytes、SHA-256
`abbe522ff37a9a091f28b7a230928fd598054498eb80cab99f08d21889f26cec`である。ID-free text renderer/
validatorとsource-profile catalogは候補実装されたが、全variantのtarget bytes/quota feasibility、
production MIME cross-language golden、source-instance recipeとG0 profile bindingを完成しない。全rowの
`parameters_complete=false`、`variant_catalog_complete=false`を維持し、G0 root hashを発行しない。

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

`kcs.persona.pc-realism-profile/v2` sidecarは20人のOS/case/device、locale/language、pinned timezone offset、
retention/mtime/permission/placement、account数とoverlay marginal rate/countをexactに束縛した。
canonical bodyは36,811 bytes、SHA-256
`a32bbb0fd7c88c57205454d8555163ad97b2b1a3024e5a5d7f7234bf56766f05`である。full suiteのmarginalは
exact duplicate 5,080、near revision 13,230、conflict 1,560、standalone attachment 5,690、pilotは各10分の1。
`profile_vectors_complete=true`と`overlay_marginal_targets_complete=true`はこの範囲だけを指す。
このsidecar単体はintent membershipを持たず、下流concrete packageがmembershipを束縛する。placement整数割当、
logical-document採点/検索参加、8軸台帳、review receiptは未完了である。

`conflict-copy`の各endpointはfact graphに実在し、同じsubject/predicate、異なるtyped value、W0で双方
`current`、異なるunordered branchでなければならない。fact-membershipが新しいfactを捏造して充足しては
ならない。現fact graphは各graphに同一subject/predicate・異なるtyped value・双方W0 `current`で、
fact-edge上で相互非到達なpairを1組持つ。source-owned semantic-membership packageは1,560 reserved pairsの
各endpointへ共通6 + branch固有1のdistinct A/B profileを割り当て、concrete packageはreservation/sourceとの
exact pre-solve joinを束縛する。一方、scope placement、raw rendition、observed search identityは存在しない。このため
`conflict_fact_realizability_proved=false`を維持し、joint allocationと実観測を完了するまでG0へ進めない。

最低限、physical materializations、logical documents、gate/search roleとchunks、container members/
attachments、current/history versions、duplicate/conflict clusters、allocated bytes、cloud/OS由来metadataと
ignored/excluded entriesを別台帳で整合させる。exact/near/conflictは排他的なcontent-relation軸、attachmentは
直交するcontainer-role軸とする。frozen envelope内のlegacy総称
`persona_fidelity_realism_profile_and_overlay_missing`は変更せず維持し、後続sidecarでは
`formal-source-recipes-and-renderer-validator-implementations`、`overlay-placement-integer-allocation-not-bound`、
`logical-document-scoring-and-search-participation-not-bound`、`eight-axis-ledger-contract-not-bound`を
具体的な未完了条件として追加する。

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
global 71 variants x 20 personasの概念空間1,420組をroute軸へ拡張しない。566 declared rowsのうち
541 activeだけが`R` rowを持ち、25 declared hard-zeroと854 undeclared/out-of-domain組は別分類とする。
`R=0`はsoft affinityなしであって配置禁止ではない。hard eligibilityはsource-intentが推移的に束縛する
`eligible_scope_keys`だけで決める。candidate matrixは各rowで`max(R)=4`、最大score scope数1--8とし、
secondary-only maximumまたは同一variant vectorの人物間cloneは独立reviewのreasoned waiverを要求する。
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
canonical bytes = 83,004
sha256          = 2a6c169a5cd02b01e330abf0f3a828d0d947a2f66b18f19e97a682d2edd50857
```

ただしroute matrixの独立review receipt、realism/source-intent refinement、source recipe/variant feasibility、
fact/oracle/query specが未束縛なので、`exact_objective_evaluable=false`、`exact_solver_executable=false`、
`policy_definition_complete_for_bound_problem=false`、`solver_policy_bound=false`である。探索上限も
`resource_limits_empirically_calibrated=false`であり、cap到達は`resource_exhausted-unknown`とする。
canonical solutionは`persona_realism_profile`/overlay、pre-solve source-intent recipe、route body、
fact membership/history templateからなるcorpus semantic namespaceを束縛する前に作ってはならない。
review receiptとquery/oracleはsolutionのpreimageへ入れず、別closureでauthority/evaluationを束縛する。

旧p17 pilotは203 contributor sourcesでglobal cohort下限211を満たさず、旧p08は211で余裕0だったため、
§5のphysical mixを明示変更した。現在は全20人のpilot/full/full-minus-pilot marginalsと必要条件が通過する。
p08/p17のpilot/full contributorsは267/2,672、p11/p15は268/2,680である。pilot global下限余裕は
最小+27、fullは最小+664、scope-boundのpilot lower headroomはp13の+56、p17の+76、
p07のupper headroomは+388である。これらはmargin regressionとして固定する。

gate-roleとdensity-sourceのsuite exact totalsは次とする。

| profile | contract | incidental | raw-only | density 1-4 / 5-20 / 21-50 / 51-70 |
| --- | ---: | ---: | ---: | --- |
| pilot | 6,925 | 6,040 | 7,335 | 731 / 1,707 / 2,498 / 1,989 |
| full | 69,236 | 60,414 | 73,350 | 7,300 / 17,042 / 24,995 / 19,899 |
| full-minus-pilot | 62,311 | 54,374 | 66,015 | 6,569 / 15,335 / 22,497 / 17,910 |

現在の必要条件artifactは次である。

```text
artifact_schema = kcs.persona.pc-joint-problem/v2
artifact_kind   = persona-pc-v2-joint-allocation-problem
canonical bytes = 744,137
sha256          = 8551472e4993f21ff71f886b3f80b9b02410c409476d0be91d773db335907074
bound envelope  = 1d49e79049b409ee5bd82d0b307db5055c2a58544df81858b77552ea82bff370
bound topology  = 204c9a136438c0dfff3718549c2fcb6009e6ccbe9debdd0cfe54bfaa4290b68f
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

observed full gateは20 personas x 3 replay x 7 checkpoints = 420個のpersona/replay/checkpoint receiptを
exact要求し、人物間・replay間・checkpoint間のpoolingを禁止する。

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

checkpointの`current C`と`history-only H`は、各personaの20 scopesを横断するdistinct contract semantic endpoint
`(scope_key, chunk_id)`集合である。`chunk_id`はKCSの`chunk_hash`と同値だが、scopeを落として
persona-globalにdedupしない。`C`はそのscopeで1件以上のlive path bindingを持つendpoint、`H`はそのscopeで
live bindingがなくreachableかつnon-purgedなhistorical/deleted path bindingを持つendpointとする。C/Hは
disjointで、path alias、DB row、materialization数を重複加算しない。same-scope renameは`(0,0)`、deleted rawの
同scope reingestは`(+q,-q)`として投影する。

別metricとして、persona-global distinct `chunk_id`はcontent重複診断、distinct `(scope,chunk_id,path)`は
all-history alias/binding負荷、`(scope,object_kind,object_hash)`とregular-file/inode countersはphysical storageへ使う。
いずれもcontract C/Hへ混ぜない。cross-scope move 5件はpilotの`incidental_searchable` sourceへ割り当てる。
人物別`qIM`をその5 sourceのW0 actual endpoint chunks合計（各1--70、合計5--350）とし、moveのdeltaは
contract C/H=`(0,0)`、incidental endpoint C/H=`(0,+qIM)`、persona-global chunk ID=`0`、history path binding
`+qIM`とする。宛先scopeに同endpoint/CASがないこと、元scope live multiplicity 1、同一chunk config/profileを
compiled planのpreconditionにする。
最も厳しいW5 pre-purgeでもpilotはincidental current upper 1,020 + qIM 350 = 1,370 <
current+history cap 2,040、fullは10,200 + 350 = 10,550 < 20,400である。ただしこれは上限式の
feasibilityであり、move anchorのactual chunks > 0とcap内収束はW0 index後にattestする。

この会計境界のmachine-readable正本候補は`kcs.persona.pc-chunk-accounting/v1`である。
`chunk_id == chunk_hash`、4 metric、rename/move/duplicateのexact operation deltaと成立precondition、全6 physical
projections、checkpoint/cap、performance/Recall分母を独立再構築する。bodyは19,801 canonical bytes、SHA-256
`d9c59e922a2619b1748194241ffdf47ace3eb034f136b0d04154163bda3ccea2`である。
`kcs.persona.pc-lifecycle-demand/v2`はこのbodyをdirect inputに束縛し、各人105 anonymous capabilities、
U35/I5、P'/X'、restore net-zero、disjoint final states、`qIM <= uIM = 350`、`nIM = 5`を固定する。
bodyは463,571 canonical bytes、SHA-256
`32e0aaf88632803d41266152b81e2cc2917111d69f6dfb03be0621920c8a0080`である。これはpre-solve demandで、
source-instance matching、W0 qIM observation、compiled events、actual physical/C/H receipt、G0はfalseである。

pilot/fullのwhole-source contributor cohort比は`P/X/Y/N/U = 4/10/6/4/76`である。quota chunk合計を
この比へexactに合わせ、P/X/Y/Nはpilot/fullとも各人物の20 scopesすべてを正のsourceで覆う。
10% projectionはcheckpoint/cohort chunk targetへ適用し、source/event row countがfullの厳密10%である
ことは要求しない。

- P: W1 small edit。W5でcapacity filler P'を別pathへ作成・index後、旧P pathを1件ずつpath-purge
- X: W1 small edit、W3 major edit、W4 deleteし、capacity filler X'でcurrent chunk容量を置換
- Y: W1 small edit、W3 major edit、そのままcurrent
- N: W3 edit、W5 correction
- U: arithmetic control。安全なsame-scope rename/duplicateの母体にできる

現typed fact graphが定義するrevision visibility境界はW1だけである。replacement factをW1から
`current`として含むintentとprior factをhistory versionへ残すintentは、W1 editを持つ`P|X|Y` cohortだけへ
割当可能とする。pre-solve source intentの`allowed_history_cohort_ids`/`required_event_profile_id`とfact
membershipをjoint refinementでtotalに照合し、W1 editを持たない`N|U`へ割り当てた解を拒否する。

そのうえでpre-solve lifecycle demandでは、現契約のW3 X/Y/N editとW5 N correctionをsurface/raw lifecycle
editとし、eventの
`changed_fact_ids=[]`を要求する。ただし生成されるsource versionの全量membershipである
`present_fact_ids`は、直前versionで可視なfact集合をexactに引き継がなければならない。
表層edit自体をsemantic fact変更として数えないだけで、引き継いだfactに対するsemantic expected answerから
そのsource versionを除外する意味ではない。W3/W5の意味変更を評価対象へ加える場合は、wave別visibilityを
持つtyped revision chain、非空の`changed_fact_ids`、semantic answer membershipを追加し、input closureへ
束縛してからG0を更新する。

P'/X'はoriginalと同scope/variant/quotaでよいが、別logical document、別raw/chunk集合、独立fact/content recipeを
持ち、`capacity_replaces`関係だけを持つ。同一raw/factsのstructural copyやexact carry-forwardを使うと、
final-deleted/purged queryがlive fillerへhitするため拒否する。restored 10件はW4 deleted Xから選び、
W5でbyte-exact export、別managed direct-childへのreingest/index、対応する同variant/quotaのX' filler deleteを
1 dependency groupにする。restoreとpaired deleteの合計deltaは`(0,0)`である。

W5順序は全regular events、全ordinary scope indexes、P' current確認、persona/source順の旧P
unlink/path-purge + forced purged commit、全post-purge noop indexesである。rename/move/archive/restore等の
structural event inventory、dependency、before/after state、replacement recipeもroot-independent intentへ
exact列挙する。rendererが未完成のG0ではevent bytes/hashを作らず、intent hashだけを凍結候補にする。
pre-solve event inventoryは`persona x wave x event_type x family x variant`のexact件数を持ち、各行で
event intent、logical document/source intent、precondition checkpoint、scope relation/path transition rule、
before/after abstract raw state、
bytes/facts保持、quotaを変数とするcurrent/history delta rule、query scenario capability、visibility、
purge/restore anchorを束縛する。quotaはjoint solverの所有とし、pre-solve rowへ未解決literalや`-1`/nullを入れない。
solution後のcompiled planだけがexact before/after scope/pathとliteral deltaを持つ。件数とcompiled deltaは人物別checkpointへexactに集計でき、
M3-1/M3-2/M3-3のformat x scenario coverageに
投影できなければならない。現在の人物別「主な操作」は意図であり、このexact inventoryの
代替にはならない。
solution後のcompiled planned history planは全eventをstate machineとして適用し、各eventのcurrent/history
chunk deltaからfull/pilot全7 checkpointを独立literalとexact一致させる。W4 delete -> W5 restore集合と
W5 final-deleted集合はdisjoint、restore anchorは人物ごとexact 10 logical documents/queryと1対1にする。
同内容の別current copyで状態遷移を代用してはならない。

2,100 semantic anchor slotsはquery IDではなくcontributor capacityとしてpilot originへ固定する。各personaの
105 contributor slotsのうち、`U=35`（M3-1 current 30、same-scope rename 5）、`Y=30`
（old wording 10、locale-history 10、archive 10）、`X=20`（final-deleted 10、restored 10）、
`P=15`（purged-negative 15）、`N=0`の100件を匿名capabilityへ使い、残る5件を
`unused-reserved-capacity`とする。cross-scope move 5件は別の`I=5 incidental_searchable` capabilityとして
pilotのunreserved incidental sourcesへ割り当てる。fullは該当pilot rowsをbyte-identicalに再利用する。
query/oracleとの対応はevaluation-only target-resolution artifactが所有し、ordinal一致から推論しない。
この要件によりpilotのY cohort source lowerは20ではなく30以上でなければならない。

pilot/full history関係はsource subsetから推論せず、event/template key、dependency、cohort、fact transition、
compiled planned event bytesのbyte-identical reuseを独立claimとして検証する。fullでpilot eventを変更・再採番
してはならない。

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
すべて`intent_key`を参照し、この段階ではfinal source/materialization IDを持たない。各intentは
`pilot|full-residual`のimmutable originを持つ。`source_profile_id`がfamily/variant/gate role/media/
renderer/validatorをpre-solveで一意に固定し、refinementはそれを再選択せず一致を検証する。
refinementが新たに割り当てるのはscope、bucket、cohort、quota、cell-local ordinalだけである。
`eligible_scope_keys`は人物catalogの`eligible_scope_set_id`から推移的に束縛できるものとし、20 scope keyを
全source rowへ反復保存しない。

現structural packageの`source_profile_id`は71 variantすべてに一意なforeign keyを付与するが、
inventory-only identityでありformal recipe profileではない。上流の凍結済みsource-profile catalogでは
formal source recipe 71件を`reserved-unbound`/`profile_id=not-bound`のまま維持する。同catalogとID-free
text/PDF renderer/validatorはbyte/complexityの局所contractだけを検査し、10 profilesを
`ready-local-only-formal-recipe-unbound`、61 profilesを`blocked-implementation-missing`として歴史的snapshotに
記録する。後続のID-free incidental 11件とraw-only 50件はcatalog非改変で局所実装され、all-71 implementation
registryが現在の71件の実装可用性を束縛する。

さらに下流の`kcs.persona.pc-formal-source-recipe-profile-catalog/v2`は386,152 canonical bytes、SHA-256
`973a31336b90abc6271165ce4a3130679f36d5a9d65b06fece6827123e5c6cc8`である。71 inventory recipe slot、
semantic content/filename slot、renderer/validator contractとruntime receiptをvariant-level profile policyへ
1対1に束縛し、full/pilot別のeligible/base incidental capとW0--W5 exact integer checkpoint tableを持つ。
これは上流snapshotを改変せず、203,000 source-instanceのparameter、selected complexity/bytes、semantic payload、
overlay instance、fact membership、final source allocation、production MIME golden、filesystem/KCS実行を束縛しない。
すべてのauthority flagはfalseである。overlay contract候補単体もschemaを記述するだけでinstance/placementを
束縛せず、G0 rootの入力としては未採用である。instance membershipは後述のnon-authorizing downstream package
だけが束縛する。

source-owned semantic-membership packageはstructural rowの10 fieldsを変更せず、別sidecarで
`intent_key`、`content_context_id`、`present_fact_set_key`を全203,000 structural keysへexactly once解決する。
人物を跨ぐfact profile、topic、project/case identityは共有しない。fact profile cardinalityは次で固定する。

| fact profile kind | 1 persona | suite | W0 present facts |
| --- | ---: | ---: | --- |
| empty | 1 | 20 | 0。`raw_only`専用 |
| W0 singleton | 32 | 640 | 4 graph x 8 W0-current facts |
| graph-normal-W0 | 4 | 80 | graphごとのall-and-only 8 W0-current facts |
| conflict branch | 8 | 160 | 4 graph x A/B。共通6 + branch固有1 |
| 合計 | 45 | 900 | typed fact graphの部分集合だけ |

各personaは4 graphに対応する4 topicを持ち、suite合計は80 persona-local topic rowsとする。
semantic profileは71 inventory profileと1対1に対応し、profile foreign keyの欠落、余分、重複を拒否する。
`topic_id`、`graph_id`、`project_or_case_id`はpersona内でbijectiveに束縛する。`raw_only`もlanguage/topic/
content contextを持てるが、fact、検索参加、chunk寄与を意味しない。既存20件のrepresentative source/fact bodyは
schema compatibility sliceであり、full pilot bodyや全件projectionの正本ではない。

compact origin bodiesは各source shardに1件のtotal-projection rowを持つ73 rows、2,100 semantic-anchor
override rows、1,560 conflict-pair override rows、合計3,733 persisted rowsとする。expanded providerはこれを
全203,000 content-context rowsと全203,000 source-owned fact-membership rowsへstreaming展開し、missing、extra、
duplicate、foreign-persona keyを拒否する。sparse overrideは2,100 anchor source refsと、1,560 pairs x 2 =
3,120 conflict endpoint refsの合計5,220 source refsを覆う。anchorは32 singleton profilesを循環し、
conflict pairはreservationのA/B branch assignmentを保存する。

language/topicのinteger quotaはpilotとfullをそれぞれHamilton法で計算し、full-residual quotaは必ず
`full - pilot`で導出する。residualを独立丸めしない。exact/near/conflict endpoints、attachment host/member、
exact-overlap counterpartをunionしてconnected componentsを作り、最大component sizeは7とする。component内の
language/topicは分割しない。conflictとanchorのfixed topicを先に差し引き、残りをcomponent size降順、
minimum `intent_key` ASCII昇順、整数deficit score、label ASCII tie-breakで決め、最後にsingletonでexact quotaを
閉じる。このclosureはsemantic coordinateだけであり、scope/bucket/cohort/quota joint solverの解ではない。

全sourceはW0/currentである。near-revision derivativeだけをsemantic version 2とし、exact duplicate、
attachment、conflict A/B、通常sourceはversion 1とする。fullはv1 189,770 / v2 13,230、pilotは
v1 18,977 / v2 1,323、full-residualはv1 170,793 / v2 11,907でなければならない。nearのv2は
W0-visible surface revisionでありW1 history transitionではない。conflict A/Bはともにv1で、unordered branch差を
version差として表現しない。

artifact DAGは`fact graph / realism / inventory profile -> semantic catalog`、
`catalog + source origin + matching reservation origin + matching persona fact graph -> semantic-membership origin`、
`catalog + origins -> pilot/full profile`、`catalog + origins + profiles + source/reservation suites -> suite`の
一方向とする。下流manifestが同じimmutable upstreamへ冗長なdirect edgeを持つことは許すが、source/
reservation/fact graph artifactへ新packageのidentityを逆参照させない。現在のconcrete overlay packageが
reservation、source、semantic/fact manifestsを下流から束縛する。expanded membershipはpre-solveの抽象
`semantic_section_key`を持ってよいが、semantic packageへquery/oracle/review receipt、solution/final source/
materialization、observed raw/chunk/materialized-section IDを含めない。既存source packageの
`source_intent_inventory_complete=false`を変更せず、formal recipe、正式`semantic_payload` namespace、
complete 16 MiB/person cap、G0/render/write authorityを与えない。

`kcs.persona.pc-concrete-overlay-membership-origin-manifest/v2`、同profile manifest、
`kcs.persona.pc-concrete-overlay-membership-suite/v2`はoverlay contract、reservation suite、source suite、
semantic-membership suiteをdirectに束縛する一方向のdownstream packageである。40 origins + 40 pilot/full
profilesが19,870 content-relation rows、5,690 attachment rows、2,100 semantic-anchor rows、合計27,660
rich rowsを持ち、25,560 draft reservation membershipsをexactに再投影する。46,840 unique overlay source refsと
それらからdisjointな2,100 anchorsにより48,940 unique joined sourcesを解決する。full relation内訳はexact
5,080、near 13,230、conflict 1,560、attachment hostsは2,800、exact-overlap attachmentsは1,390である。
full profileはmatching pilot origin/shardのexact bytes/SHAを再利用し、shard indexはorigin-local 0-basedである。

このpackageはpre-solve membershipだけを完成させる。`placement_class_requirement`はjoint solverへの要件であり
scope assignmentではない。formal recipes、semantic namespace/query/history target mapping、scope joint
allocation/solution/proof、actual payload/raw/chunk/search observation、render/write/history/KCS、complete persona
cap、G0は証明しない。origin/profile/suiteのauthority mapはすべてexact falseである。suite descriptorは
51,133 canonical bytes、SHA-256
`4763e06e9408109ad90c5e07a1bb16cd430fd65e6c5730d0015dcbea60cdf41a`に固定する。

```text
catalogs:
  fidelity_profiles / source_profiles / projects / entities / facts
  filename_templates / content_templates / permission_profiles / mtime_buckets
  validators / renderer_profiles
intents:
  persona_id / intent_key / origin / source_profile_id / eligible_scope_set_id
  project_or_case_id / entity_ids / fact_ids / period / status / version
  contributor_eligibility / allowed_bucket_ids / allowed_history_cohort_ids
  required_event_profile_id / expected_incidental_chunks_upper
  target_complexity / target_bytes / duplicate_or_conflict_group / payload_seed
overlay_memberships:
  relation_kind / cluster_key / intent_keys / search_participation
```

aggregate solutionに続くsource-intent refinementは、各`intent_key`のpre-bound family/variantを検証し、
scope、bucket/cohort/quota、cell-local ordinalをexactに割り当て、overlay/duplicate-cluster constraintも検証する。
planned source/materialization IDはcontent-affecting bodyだけを束縛するcorpus semantic namespaceと、
解かれたsemantic coordinates/cell-local ordinalの
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

fact/oracle/queryは混在bodyにしない。人物ごとに(1) intent/query/answerを参照しないtyped fact graph、
(2) `intent_key`とlogical document keyだけを持つsemantic answer membership、(3) corpus rendererから
参照不能なquery-intent、(4)これらのbytes/SHAを束縛するmanifestへ分ける。rendererにはfinal source plan、
fact graph、corpus template/seedの最小projectionだけを渡し、answer/distractor/query membershipを渡さない。
query text、compiled final-ID relevance、actual rank/score/latencyはそれぞれ後段artifactとする。
fact graphは人物ごとexact 4、suite exact 80 graphとし、現在のleafは各人物16 entities、36 typed facts、
4 unordered W0-current conflict sets、4 revision chainsを持つ。suiteでは320 entities、720 facts、
80 conflict sets、80 revision chainsである。revisionのprior factはW0だけ`current`、W1以降`history-only`、replacement
factはW0だけ`absent`、W1以降`current`とし、W1 small-edit境界とexactに一致させる。

各人物はexact 90 positive queries（30 x M3-1/M3-2/M3-3）と15 purged-negative（5 x 3）を持つ。
suite全体は1,800 positive + 300 negative = 2,100 intentで、3 replayは同じintentを各1回実行して
5,400 positive + 900 negative = 6,300 observation rowsを作る。intentをreplay間で分割・水増ししない。
positive query text 1,800件はsuite内byte-uniqueにする。scenario内の30問は次の3 strataを各10問とする。

- M3-1: `current-fact` / `cross-format-fact` / `locale-language-fact`
- M3-2: `old-wording` / `rename-move` / `locale-language-history`
- M3-3: `deleted` / `restored` / `locale-language-lifecycle`

各stratumのpre-solve selectorは次で固定し、全行`evaluation_checkpoint=W5-final`、`top_k=10`、
semantic段階のdedupはlogical-document keyとする。正式評価ではcompiled distinct `(raw_hash, section)`へ置換する。

| stratum | selector | required evidence state |
| --- | --- | --- |
| `current-fact` / `cross-format-fact` / `locale-language-fact` | default current | `current` |
| `old-wording` | `--all-history` | `old-wording-history` |
| `rename-move` | `--all-history` | `rename-move-history` |
| `locale-language-history` | `--all-history` | `locale-language-history` |
| `deleted` | `--include-deleted` | `final-deleted` |
| `restored` | default current | `current-restored` |
| `locale-language-lifecycle` | `--all-history` | `locale-language-lifecycle-history` |
| M3-1/M3-2/M3-3 purged-negative | scenarioと同じcurrent/all-history/include-deleted | `purged-absent`、expected empty |

M3-3の`restored` stratumには人物ごと最低10個のdistinct searchable restore logical documentsを割り当てる。
人物間で同じlogical document/intentを再利用せず、suite minimumは200 distinct anchorsとする。
pre-solve semantic oracleが束縛できるのは`intent_key`、logical-document key、`answer_membership_key`
（expected fact/revision/predicate/value-stateへの参照）、abstract restore event/template key、checkpoint、
検索selectorと`required_evidence_state`までである。solution後のcompiled history planがsolved cohort、
planned source/materialization/event IDへ写像し、render/index後のcompiled relevanceとlifecycle receiptが
observed materialization、期待`(raw_hash, section)`/chunk membershipを束縛する。これらdownstream identityを
pre-solve oracleへ逆流させない。各文書は最終的にrestore後のcontract-contributorとしてindexされなければ
ならず、quota-zero/raw-onlyのstructural sentinel、同一logical documentの複数path、未index fileはこの10件へ
数えない。`restored`はW5-finalで`required_evidence_state=current-restored`として採点し、W4 deleteとW5
restoreのlifecycle receiptおよび新materializationへの一致を必須にする。同じ内容の別current copyだけが
ヒットしても不合格である。これと分離して`deleted` stratumはW5-finalで
`required_evidence_state=final-deleted`とし、`--include-deleted`の本来の削除済み検索を検証する。

pre-solve artifact graphは少なくとも次の別bodyを一方向にhashする。query情報をcorpus rendererへ流さず、
source-intentとの循環参照を作らないため、1 bodyへ統合しない。

- `kcs.persona.pc-source-intent-origin-shard/v2`: source profile、scope候補、正本`present_fact_ids`、complexity/bytes
- `kcs.persona.pc-fact-membership/v2`: intentからlogical document/revision/branch/fact/sectionへのmembership。
  `present_fact_ids`を独立定義せずsource-intent正本の集合をexact projectionとして完全一致検証する
- `kcs.persona.pc-history-intent/v2`: solverがcohortを割り当てる前のW1--W5 conditional event template/constraint、
  `changed_fact_ids`、delete/restore依存、checkpoint state。exact event列とplanned IDを持つcompiled history planは
  solution後の別artifactとする
- `kcs.persona.pc-query-intent/v2`: corpus rendererから参照不能なquery intent
- `kcs.persona.pc-semantic-oracle/v2`: queryからlogical documentとrequired evidence stateへの期待値
- `kcs.persona.pc-fact-oracle-query-manifest/v2`: 上記bodyとfact graph/history manifestのSHA束縛
- `kcs.persona.pc-corpus-semantic-namespace/v2`: source profile、realism、route body、source intent、overlay、
  fact membership、history templateなど**内容に影響するcanonical bodyだけ**のroot。review/evidence receipt、
  query/oracleを含めず、solver/solutionとplanned source/materialization/event IDの唯一のnamespaceとする
- `kcs.persona.pc-corpus-input-closure-manifest/v2`: corpus semantic namespaceと、そのexact bodyを承認する
  independent review/authority evidenceを束縛する。receipt差替えだけでsource identityを変更しない
- `kcs.persona.pc-evaluation-input-closure-manifest/v2`: exact corpus input closure、query intent、semantic oracle、
  fact-oracle-query manifestを束縛する
- `kcs.persona.pc-suite-input-closure-descriptor/v2`: corpus/evaluationの両rootと全completion blockerを束縛する

各注入bodyの既知schemaに対するfield completeness、型、相互制約は、そのbodyと一緒に注入するexact
provider validatorを正本とする。input-closure scannerはその代替validatorではなく、canonical field名と
この契約で明示したaliasに対する追加のfail-closed defense-in-depthである。したがって任意の未知同義語を
scannerだけで意味解析できるとは主張せず、validator未実行、`True`以外の戻り値、provider bodyとpinの
bytes/SHA/identity不一致はすべて拒否する。この境界も現candidateへ実行・G0・write authorityを与えない。

query bodyだけの変更はevaluation closureとsuite descriptorだけを変更し、corpus semantic namespace、corpus
input、solution、planned IDs、rendered corpus bytesを変更してはならない。同じsemantic bodyに対するreview
receiptだけの差替えはevidenceを含むclosure/descriptorだけを変更し、semantic namespace、solution、planned
IDs、rendered corpus bytesを変更してはならない。route bodyそのものの変更はsemantic namespaceを変更する。
各upstream bodyがauthority/completion/blockerなど可変の証拠metadataを同居させる場合、semantic namespaceは
schema別にallowlistした`semantic_payload` projectionのbytes/SHAだけを束縛し、corpus input closureがfull body
とmetadataを束縛する。projection未実装の現candidate full bodyをsemantic namespaceとして採用してはならず、
このため現時点のsemantic namespace/rootは未発行である。
corpus rendererのinput projection/import graphにはquery/oracle/answer/distractor SHAやevaluation root resolverを
渡さず、query artifactが欠落・valid差替えでも同じcorpus bytesを生成できるcapability境界を要求する。

多言語personaの`locale-language-*`には非primary languageを最低1問含める。negativeはRecall母数外で
`false-positive@10 == 0`を要求する。各positiveには同topic/languageのdistractor sourcesを3件以上
持たせる。G0 freeze時は`query_spec_hashed=true`、実query text生成前は
`query_instances_rendered=false`とし、両者を1つの`query_rendered` claimへ畳まない。

## 9. hash graphとresource boundary

canonical JSONはsorted keys、compact UTF-8 NFC、integer-only、duplicate keyなしとする。root/runtime
path、replay number、timestamp-nowをplan hashへ入れない。logical epochとexact offsetを使う。

hash graphはacyclicとし、概念上次の一方向だけを許す。

```text
content-affecting bodies -> corpus semantic namespace
corpus semantic namespace -> aggregate + source-intent-refinement solution/proof
solution/proof -> final planned source plan -> compiled planned history plan -> planned ledger
corpus semantic namespace + independent review receipts -> corpus input closure
corpus input closure + query intent + semantic oracle -> evaluation input closure
planned ledger + corpus/evaluation closure -> G0 suite descriptor
render/index/lifecycle receipts -> compiled observed relevance -> observed ledger/evaluation terminal
```

query/oracle/review receiptをcorpus semantic namespace、solution、planned IDへ逆流させない。
policy SHAを先行problemへ逆流させず、self-hash fieldをcanonical bytesへ含めない。missing、duplicate、unused、
cyclic、foreign-persona referenceはfail closedとする。

現在のcanonical core inventoryは次のexact bytes/SHAである。候補overlay/text/source-profile出力はこの表の
core/G0 rootへ含めず、正式なupstream pinが更新されるまでnon-authoritativeとする。

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| envelope | 71,979 | `1d49e79049b409ee5bd82d0b307db5055c2a58544df81858b77552ea82bff370` |
| topology | 134,195 | `204c9a136438c0dfff3718549c2fcb6009e6ccbe9debdd0cfe54bfaa4290b68f` |
| joint necessary problem | 744,137 | `8551472e4993f21ff71f886b3f80b9b02410c409476d0be91d773db335907074` |
| solver policy | 83,004 | `2a6c169a5cd02b01e330abf0f3a828d0d947a2f66b18f19e97a682d2edd50857` |
| realism profile | 36,811 | `a32bbb0fd7c88c57205454d8555163ad97b2b1a3024e5a5d7f7234bf56766f05` |
| variant catalog | 211,733 | `abbe522ff37a9a091f28b7a230928fd598054498eb80cab99f08d21889f26cec` |
| route candidate | 70,626 | `e8a401193fc751ed3d7b2a47e3661202835579df8700392ce9fdfd30ad07c790` |

次のstructural source packageはcore/G0 rootの外側にあるnon-authorizing下流artifactとして固定する。

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| all-71 inventory profile catalog | 87,391 | `be5e807d97ade4c50de8a47cb017137d12740baea2fb0396d8ac45d39a84e196` |
| source inventory suite descriptor | 45,887 | `b62fadfa42b0f3f61b6de017300e65c48a5c07fb801dc470999c3d89a39dd706` |
| p01 pilot origin manifest | 13,043 | `b72ea3b5b11744b39499f1c24a4de5b4d65ee2b67cfea351a604df4b7f9ca1df` |
| p01 pilot profile manifest | 7,814 | `89fb76b9a6867790ef7c55ca6ae94b9e8dd97a5a981ed236e7677b2fbfb3b65b` |
| p12 full-residual origin manifest | 15,474 | `418345d14d8a494ab59d342c21ad4cb0323fab6fcf9a064ec677ce64a60177fe` |
| p12 full profile manifest | 10,369 | `bdf7371dff9cb5ae106564026d616887fffa05ccf9735bff637936fd7fcac41b` |

bounded artifact上限は次を目標とする。すべて最大nesting depth 64、string 4,096 bytesとし、最終loaderは
bodyを読む前のframed byte capを持つ。現solver-policy sidecarの512 KiBはmaterialize済みvalueに対する
in-memory canonical capである。16 MiB object readerと、16 MiB body/65,536 rows/1 row LF込み64 KiBの
JSONL readerはpre-read cap、exact declared length/SHA、UTF-8/NFC/canonicalityをfail closedで検証する候補を
実装したが、外側frame header/dispatcherとartifact-schema別capのbindingは未実装なのでloader blockerを解除しない。

- suite/fixture envelope: 2 MiB
- persona realism profile: 256 KiB/suite（現在36,811 bytes）
- variant identity/marginal catalog: 2 MiB/suite（現在211,733 bytes）
- joint necessary problem: 4 MiB/suite（現在744,137 bytes）
- joint solver policy: 512 KiB/suite
- W0 persona plan: 16 MiB、最大16,000 W0 sources、20 scopes
- source-intent shard: 4 MiB、最大4,096 intents。pilotは専用shard、fullは同じpilot bytesを再利用して
  full-residual shardだけを追加する
- source-intent人物package: frame/header、manifest、intent/overlay shardを含む合計16 MiB。rowは最大768 bytes
- fact-membership shard: 4 MiB、最大4,096 rows、rowはLF込み最大768 bytes。人物manifestはshard count、
  first/last key、row count、body SHAをexactに束縛する
- joint allocation execution receipt or independently verifiable proof: 8 MiB/person
- history intent/event recipe: 16 MiB/person、event-created sources最大4,096/person。最大4,096 rows/4 MiBの
  shard、LF込みrow最大1,024 bytesとし、人物合計event/template rows上限は16,384
- fact/oracle/query bundle: 4 MiB/person。fact graph 1 MiB、semantic oracle 1.5 MiB、query intent 1 MiB、
  manifest 128 KiBをsubcapとし、positive 90、negative 15
- suite descriptor/compact summaries: 4 MiB

現203,000件を上記shard規則で分けると、20 pilot shardsと53 full-residual shardsの計73 intent shardsとなる。
pilot/fullは同じ行を再生成して同値とみなすのではなく、full人物manifestがpilot shardの同一bytes/SHAを
参照し、residualだけを追加する。

`kcs.persona.pc-source-inventory-layout/v2`はこの算術とkey-range予約だけをcanonical化し、274,566 bytes、
SHA-256 `ef52b756c7100c719f66323cd3cdb4dfc58a78e48d78f2857ca378cb1eb83dba`である。20,300 pilot +
182,700 residual、20 + 53 shards、566 persona/variant marginals、69,236/60,414/73,350のfull gate-role countsを
exactに束縛する。一方、row body、body bytes/SHA、source profile assignment、overlay/fact membership、
16 MiB package proof、source inventory/G0/write authorityはこのlayout単体には持たない。pilot keyは既存代表sliceと互換な4桁、
residual keyは最大14,400件を覆う5桁ordinalとし、originごとにordinalを独立させる。

下流の`kcs.persona.pc-source-inventory-profile-catalog/v2`は71 inventory profile identitiesを
variant-catalog順に束縛する。`kcs.persona.pc-source-inventory-origin-manifest/v2`、
`kcs.persona.pc-source-inventory-profile-manifest/v2`、`kcs.persona.pc-source-inventory-suite/v2`は、203,000の
reference-only source-slot rowsを73 canonical JSONL bodiesへstreaming materializeし、40 origin manifests、
40 pilot/full profile manifests、各body bytes/SHAをexactに束縛する。総shard bodyは108,682,911 bytes、
最大rowはLF込み558 bytes、最大shardは2,225,794 bytesである。full profileはpilot origin manifestと
pilot shard descriptorsのexact referenceを先頭に再利用し、再生成同値をreuse証明としない。
pilot/fullの各profile manifestはoverlay reservation suite SHAを直接束縛し、origin manifest経由の
間接参照だけに依存しない。
既存representative `...-0001` artifactsはkey grammarのみ互換で、formal pilot bodyとして再利用しない。

人物別current-component ledgerの分母は、各人物の**unique source shard bodies + pilot/full-residualの
2 origin manifests + pilot/fullの2 profile manifestsのみ**である。最大p12は8,598,540 bytes / 16 MiBで
現source-only component capを満たす。semantic suiteのcurrent-component ledgerはこれにmatching reservation
origins、semantic catalog全量、compact semantic bodies、semantic origin/profile manifestsを保守的に加算し、
最大p12は12,070,092 bytes、16 MiBまでのheadroomは4,707,124 bytesである。このsemantic ledger単体には
concrete overlay、frame/header、formal recipesを含まない。concrete overlay suiteのcurrent-component ledgerは
semantic ledgerをexact baseとし、overlay contract全量、unique concrete origin bodies、pilot/full profile
manifestsを加算する一方、reservation/catalogを二重計上せず、draft projection receiptとglobal suite descriptorも
各personaへ課金しない。最大p12は13,275,672 bytes、headroomは3,501,544 bytesである。それでも
`formal_complete_persona_package_cap_proved=false`、`source_intent_inventory_complete=false`を維持する。
専用CI job `persona-v2-source-inventory-full`でpackage validatorを分離実行する定義を追加したが、
実行結果のgreenは本契約では主張しない。

semantic-membership packageは専用CI job `persona-v2-source-semantic-membership-full`でcatalog、origin/profile/
suite、expanded providers、Hamilton/component closure、version counts、tamper rejectionを回帰する。catalogは
436,495 canonical bytes / SHA-256
`45e849cb2b94392820a21870c93e88e879f99d55a8b83c211663e7b3d1497d62`、suite descriptorは49,837 bytes /
`62394dd2a3544f7d6c332652e6799b7a60353e8e3aa6a87f80e0ff21590a2e28`に固定する。compact bodiesは
1,006,627 bytes、expanded context/fact-membership body receiptsは121,020,941 / 135,741,615 bytesを束縛する。
remote CI greenは主張しない。このsemantic gate単体からconcrete overlay completionを推論しない。

concrete-overlay membership packageは専用CI job
`persona-v2-concrete-overlay-membership-full`でshape、DAG/cross-binding、draft projection、relation/attachment/
anchor invariants、pilot reuse、byte ledger、tamper rejection、builder-independent validationを回帰し、timeoutを
90分とする。producer shape testは172.190秒 / 最大RSS 237,158,400 bytes、full buildは155.45秒 /
最大RSS 192,757,760 bytesと計測した。full independent acceptanceは354.770秒 / 外側最大RSS
271,368,192 bytesでPASSし、384 MiB RSS gateもPASSした。remote CI greenは主張しない。
concrete packageまでのcurrent-component capを満たしても、frame/header、formal recipes、
semantic namespace、solution/proof等を含むcomplete persona packageの16 MiB formal proofへ昇格させない。

`pdf-text`の局所feasibilityは1--72 ASCII text-layer pages、4,096 + 2,048 × (pages - 1) bytesを固定し、
PDF 1.4のnon-stream 255-byte line上限、xref/trailer/page treeを独立validatorで検査する。renderer contractは
2,075 bytes / `ab66e11d93e2aa7896bdffd28f1c1fec9f443a4ff3b48ba6dcc4d1c12bab69f6`、validator contractは
2,233 bytes / `78c90d4cccb254f67bc030e79eaef46704ce4d8555a3edc8f42edc293e91805e`、source-profile catalogは
72,559 bytes / `6e38fab07851f9fdcbf9d6e67e502484aea7edb66167ea86db1539593b8b58ac`である。これにより
10 contributor feasibility variantsがfull 69,236 contributor sourcesを局所的に覆うが、多言語content、
sourceごとのsemantic recipe、positive query anchor、production KCS chunks、G0を証明しない。

incidental-textの局所feasibilityは`csv`、`eml`、`html`、`ipynb`、`json`、`jsonl`、`log`、`sql`、
`tsv`、`xml`、`yaml`をstdlib-onlyの決定論的rendererとbuilder非依存validatorで検査する。renderer contractは
9,139 bytes / `22fae0f62a67856ef20b5820c7274aad542a2de06f76c93c5c68acdaed9652f4`、validator contractは
10,090 bytes / `67a0f0913de6087ca4b1c836d6dff4f845d6ee50a3adf12b794236f128baed75`である。各出力は
512 KiB以下、EMLはCRLFかつwire line 78 bytes以下とする。この11 variantはinventory marginal上full 60,414
incidental sourcesを覆うが、formal source recipe、source別semantic content、materialization、actual incidental
chunks、KCS、G0、filesystem/write authorityを証明しない。

suite buildは1 personaずつ行い、20 full plansを同時保持しない。p12の16,000 W0 sourcesと
event-created replacement recipesは別inventory/別上限であり、W0 capを暗黙超過させない。

G0は`persona x family x origin`ごとにsource count、ordinary/tail count、rendererで表現可能な
complexity histogram、raw-byte sum、nearest-rank p50/p95/max、allocated-byte upperの算出根拠、
gate-role別requested-chunk policyをexactに束縛する。fullはcount、histogram、raw-byte sumのすべてで
`pilot + full-residual`に閉じる。p50/p95は差し引かずfull source列から再計算する。
aggregate catalogは566 persona-variant行、300 persona-family投影、20 persona集計を実装し、full 203,000 filesの
raw sum 5,034,302,718 bytes、4 KiB丸め後5,194,530,816 bytes、nearest-rank p50 8,192 bytes、p95
129,024 bytes、max 2,621,440 bytes、formal tail 160件を束縛した。最大人物p12の4 KiB丸め後
417,591,296 bytesを含め全人物が480 MiB/personの計画上限内である。canonical bodyは1,576,125 bytes、
SHA-256 `7f2fdcc823885401cb7ed1b8fc42c9010b38af63d2c58879babb28aadeb6b343`である。
ただしsource-level parameter assignment、actual allocation、CAS/index/history amplification、root-bound capacityが
未束縛の間はcapacity/write authorityをfalseのままにする。

capacityは次の2境界を混ぜない。

- **source-tree envelope**: personaのmanaged source filesと、その400 leaf scopeへ至るauthored directoryだけ。
  `.kcs`、raw/prepared/normalized/chunk/tree/commit CAS、SQLite/FTS/WAL/SHM、registry、plan/ledger/
  receipt、temp/staging、history、recursive/byte-stress laneは含めない。W0の512 MiB/personかつ
  10 GiB/replay、W5 finalの1.25 GiB/personかつ25 GiB/replay、W5 pre-purgeの
  `floor(27 GiB / 20)`/personかつ27 GiB/replayは、この境界だけの未較正なrenderer設計候補である。
- **root-bound capacity**: retained replay roots、進行中root、`.kcs`の全object/index/history、device state、
  plan/ledger/receipt、staging/transient、共有workspaceを含む実行先filesystem全体。この境界に固定の
  full byte/inode capはまだない。旧88 GiBはsource-tree候補25+25+27 GiBとworkspace仮置き11 GiBの
  算術にすぎず、root-bound cap、hard cap、Go証拠のいずれにも使わない。

`scope-local-regular-file-per-distinct-chunk-v1`、すなわち各distinct `(scope, chunk)`がscope-localのregular
chunk objectを1つ持つstorage modelをcampaign直前にruntime再検証する。この仮定が成立する場合、formal
成功時に必ず存在するものだけでも、pilot W0の保守的inode下限は次である。

```text
pilot_sources                 = 20,300
pilot_authored_path_dirs      = 1,097
pilot_current_chunk_cas       = 20 personas * 12,000 = 240,000
pilot_formal_success_floor    = 261,397 inodes

full_sources_per_replay       = 203,000
full_authored_path_dirs       = 1,097
full_current_chunk_cas        = 20 personas * 120,000 = 2,400,000
full_W0_success_floor/replay  = 2,604,097 inodes
```

`pilot_current_chunk_cas`/`full_current_chunk_cas`はplanned quotaではなく、actual chunk gateを満たすrunに
条件付けた下限である。261,397はraw/prepared/normalized/tree/commit CAS、SQLite/FTS/WAL、各`.kcs`の
fanout directory、registry、ledger/receipt、staging/transient/historyをすべて除外しているので上限ではない。
runtime再検証で上記storage modelが不成立なら、このinode下限をGo/No-Go根拠へ流用せずcapacity gateを
fail closedにし、観測した実storage modelで再契約する。
したがって旧pilot `inode_cap=250,000`はformal成功より小さく、廃止する。新しい数値inode capはpilot実測前に
設定しない。byte-stressの740 MiB payload/person、768 MiB/person、15 GiB totalもlane-local
source payload候補であり、formal root-bound capacityへ加算する場合は別receiptを要求する。

pilot readbackは人物・componentごとに`raw/cas/index/history/staging/transient`を分け、canonical pilot
plan SHA、component basis/observed units、`st_blocks`相当のallocated bytes、additional inodes、
filesystem device/allocation unitを束縛する。basisは順に`final_active_files`、
`transient_current_chunks`、`transient_current_plus_history_chunks`、`history_only_chunks`、
`w0_physical_files`、`transient_extra_chunk_rows`で固定する。component `i`のpilot観測を
`(B_i,N_i,U_i)`、対象unit数を`T_i`とすると、25% headroom込みのprojectionはintegerだけで次を使う。

```text
projected_bytes_i  = ceil(ceil(B_i * T_i / U_i) * 5 / 4)
projected_inodes_i = ceil(ceil(N_i * T_i / U_i) * 5 / 4)
```

retained bytesは`raw+cas+index+history`の20人和、sequential staging peakは人物別`staging`の最大、
W5 transient peakは全20人で同居する`transient`の和とする。inode側はsource/directory/ledger等の
`exact_known_*_inodes`へcomponent別`projected_additional_inodes`を加え、unknownを0へ変換しない。
replay数を`r`（pilot=1、full=3）として、root-independent planは次を出す。

```text
payload_peak = r * retained + max(sequential_staging_peak, coexisting_W5_transient_peak)
inode_peak   = r * retained_inodes + max(sequential_staging_inodes, coexisting_W5_transient_inodes)
required_root_bytes = payload_peak + inode_peak * destination_allocation_unit
```

root-bound preflightはactual destinationの同一deviceから読み戻した`free_bytes/free_inodes`、allocation unit、
explicit byte/inode cap、reserveをplan/manifest SHAへ束縛し、`required_root_bytes <= byte_cap`、
`inode_peak <= inode_cap`、減算後のfree値がreserve以上の4条件をすべて要求する。caller-declared projection、
missing/zero component、別device、stale measurement、float、overflowはfail closedとする。現状はactual
pilot/root measurement readerが未実装なので、32 GiB pilot byte capと96 GiB reserveも候補にとどまり、
`formal_capacity_gate_satisfied=false`、`authorizes_physical_write=false`を維持する。

## 10. G0 negative authority

G0 artifact/receiptは次を固定する。

```text
g0_contract_frozen               = false  # 全400 paths/load/solver/oracle完了まで
activity_unit_review_receipt_bound = false
solver_policy_bound              = false
route_affinity_matrix_review_receipt_bound = false
overlay_contract_authoritative   = false
overlay_instances_bound          = false  # concrete packageは存在するが正式G0 rootへ未束縛
source_recipe_profile_id_bound   = false  # G0 descriptor/rootへの正式binding。下流71-profile catalogだけではtrueにしない
text_renderer_profile_bound      = false  # G0 descriptor/rootへの正式binding。下流format registryだけではtrueにしない
source_profile_vertical_slice_complete = false  # source-instance parameter/materialization/observationが未完成
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
query_spec_hashed                = false  # complete evaluation input closureがG0 descriptorへcanonical bindingされた時だけtrue
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
3. 人物別`persona_realism_profile`/overlayと8軸台帳、20 persona/20 primary use-case catalog、aggregate byte分布、
   chunk-accounting sidecar、recursive robustness catalog、pre-solve source-intent/lifecycle recipe/variant feasibility、
   route matrix、fact graph/membership/history templateのcorpus semantic namespace、独立reviewを含むcorpus
   input closure、独立query spec/oracleを含むevaluation input closure。候補overlay contract、
   contributor text/PDF renderer/validator、11 incidental renderer/validator、source-profile catalogは正式な
   profile ID、instance、upstream hashへ束縛する
4. full/pilot family/variant/scope/bucket/source quota/cohort aggregateとper-intent overlay assignmentの
   exact refinement、bounded canonical exact replayまたは完全proofによる最適性の検証、cycle-free final ID導出
5. P/X/Y/N/U history操作順、scope coverage、checkpoint exact projection。pre-solve lifecycle demandは実装済みだが、
   source-instance matchingとcompiled exact eventsが必要である。現W3/W5
   surface editのeventは`changed_fact_ids=[]`、source versionの`present_fact_ids`は直前の可視集合を
   exactに引き継ぐことを要求する。
   semantic変更にする場合は追加typed revision chainと非空changed membershipを要求する
6. W0-W5全source/destinationのpath/basename collision、resource cap validation
7. v1 identity/goldenの非回帰
8. 20人を1人ずつbuildしたcanonical bytes/hashと16 MiB cap
9. M3-3用に人物ごと10 distinct searchable restore logical documentsとsemantic oracle/abstract event binding。
   W5 current-restoredとfinal-deletedを分離し、同内容の別current copyによる偽PASSを拒否する。
   planned source/materialization/event IDはsolution後のcompiled planned history planへ含めてよいが、observed
   materialization/chunk/`raw_hash`/section bindingはG0へ逆流させず、render・index後のcompiled observed
   relevance/receiptで検証する
10. M3-2用searchable cross-scope rename/move、M3-1用text-layer PDFの多言語content recipe、KCS chunk
    attestation、positive anchor最低数。局所ASCII PDF feasibilityだけでM3-1を合格扱いしない。
    scan PDFは現v2ではoffline raw-only/`awaiting_ocr`のstructural/negative対象で、positive Recall relevanceへ
    数えない。将来local deterministic OCR derivativeを追加する場合は別variant/provenance/contributor契約を
    version updateで先に束縛する

次の実装順は、(1) source-instance matchingを伴うcompiled exact lifecycle-event inventory、203,000 source-instance parameterと
corpus semantic/query/history mapping、(2) joint allocation/solution/proof、(3) allocation/rendering、
(4) folder/file write、(5) edits/history、(6) fresh-storage replays、(7) evaluationとする。
concrete pre-solve membershipとvariant-level recipe policyの完成からscope placement、source-instance recipe、
G0、render/writeを推論しない。

G0後のrender/index実行ゲートは、logical-document expectedから正式MVP distinct `(raw_hash, section)`
relevanceへのcompiled binding、observed materialization/chunk ID、lifecycle receiptを別artifactで検証する。
`formal_relevance_compiled=false`はG0で必須であり、pure planningだけでtrueへ変更してはならない。
