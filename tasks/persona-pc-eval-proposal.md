# 20人の独立persona-PC評価環境案

Status: W0 tiny、W1-W5 contributor/structural allocator、root-independent planned
event manifest、persona fidelity仮説metadata、bounded suite streaming planningを実装済み。
W0 history prepare/replay、fidelityのrenderer反映、formal pilot/full物理生成は未実装または未承認。

## 1. 結論

20個の用途フォルダを1人に持たせるのではなく、**20人分の独立PC root**を作る。
各PCは20個のleaf scope、独立したdevice registry、異なる職種固有path、異なる
物理ファイル形式比率を持つ。formal fullでは各人が単独で120,000 current
contract-contributor chunksを持ち、20人を合算して条件を満たすことは禁止する。

W0で生成したplanned chunksは実KCS chunkの証拠ではない。`prepare/index`後のattestorが
各人120,000を実測して初めてformal gateを通過する。Office、scan PDF、画像、音声、
domain binaryは作成しただけでは検索可能chunkへ数えない。

## 2. 1人分の物理構造

```text
<replay-root>/
  devices/
    pNN-<role>/
      persona-manifest.json
      home/
        <collection parents>/
          <project/year/phase/etc>/
            <leaf-scope>/
              pNN-src-000001.<ext>  # managed filesはleaf直下だけ
      .kcs-eval-device/             # prepare段階で作成、W0には置かない
      oracle/                       # history/query段階で作成、W0には置かない
  ledgers/<persona>/<scope>/
    w0-physical-raw.jsonl
    w0-logical-items.jsonl
    w0-searchable-expectations.jsonl
    w0-scope-manifest.json
  w0-plan.json
  w0-suite-manifest.json
  generation-capacity-receipt.json
  w0-root-binding.json
```

KCSはleaf scopeを20個別々に初期化する。PC umbrellaや中間親をscopeにしない。
これにより深いPC階層を再現しつつ、scope内のmanaged fileは必ずdirect childになる。

現在の複雑性floorは、全400 scope中63 scopeが深さ4以上、10人が深さ5以上、
最大深さ6である。例:

- SRE: `services/checkout/prod/oncall/operations`
- ML: `research/programs/model-alpha/experiments/results`
- consultant: `engagements/client-alpha/2026/phase-1/deliverables`
- construction: `portfolio/projects/project-alpha/2026/construction/drawings`
- educator: `learning/courses/course-alpha/2026/term-1/lesson-plans`
- journalist: `newsroom/investigations/story-alpha/2026/fact-check`

## 3. 20人の規模と主要形式

以下は実利用統計ではなく、検索・変換・raw-only境界を広く踏むための
**stress-design初期仮説**である。pilotの実測前に実分布と誤認してはならない。

| id | 1人として再現する属性 | full files | contributor files | 平均planned chunks/contributor | 最大scope深度 | 上位形式 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| p01 | software engineer | 12,000 | 7,512 | 16.0 | 4 | code 28%, md 22%, structured 12% |
| p02 | SRE | 15,000 | 8,160 | 14.7 | 5 | txt/log 22%, md 20%, structured 20% |
| p03 | security/GRC analyst | 10,000 | 4,140 | 29.0 | 2 | structured 15%, text PDF 15%, txt/log 12% |
| p04 | ML research engineer | 10,000 | 4,690 | 25.6 | 5 | code 18%, md/csv/notebook/text PDF 各12% |
| p05 | BI/data analyst | 12,000 | 2,700 | 44.4 | 3 | csv/tsv 20%, xlsx 15%, structured 14% |
| p06 | life-science researcher | 8,000 | 2,496 | 48.1 | 5 | text PDF 18%, csv/tsv 15%, image 9% |
| p07 | humanities researcher | 7,000 | 3,080 | 39.0 | 2 | text PDF 25%, scan PDF 20%, md 12% |
| p08 | product manager | 8,000 | 2,144 | 56.0 | 5 | docx/pptx 各15%, text PDF 13% |
| p09 | UX researcher | 9,000 | 2,565 | 46.8 | 3 | txt/log 15%, image 15%, docx 12% |
| p10 | management consultant | 7,000 | 1,736 | 69.1 | 5 | text PDF/xlsx/pptx 各18% |
| p11 | account executive | 10,000 | 2,180 | 55.0 | 3 | html/eml 25%, text PDF 16%, docx 14% |
| p12 | support/success lead | 16,000 | 6,080 | 19.7 | 3 | txt/log 20%, md/structured 各15% |
| p13 | corporate/privacy counsel | 7,000 | 2,366 | 50.7 | 3 | text PDF 28%, docx 22%, scan PDF 15% |
| p14 | finance controller | 9,000 | 1,719 | 69.8 | 5 | xlsx 27%, csv/tsv 15%, text PDF 13% |
| p15 | recruiter/people ops | 8,000 | 2,200 | 54.5 | 3 | text PDF/docx 各20%, html/eml 15% |
| p16 | clinical researcher | 8,000 | 2,736 | 43.9 | 5 | text PDF 24%, scan PDF 12%, csv/docx 各10% |
| p17 | construction PM | 8,000 | 2,064 | 58.1 | 6 | text PDF 20%, domain binary 15%, scan/image 各12% |
| p18 | manufacturing quality engineer | 12,000 | 4,128 | 29.1 | 3 | text PDF 18%, csv 15%, txt/log 12% |
| p19 | educator/instructional designer | 9,000 | 2,835 | 42.3 | 6 | text PDF 20%, docx 15%, pptx 12% |
| p20 | investigative journalist | 10,000 | 3,760 | 31.9 | 5 | txt/log 18%, text PDF 16%, html/eml 10% |

p10/p14は約70 chunks/contributorで72上限に近く、実PCより少数巨大文書へ偏る。
この2人を含むsize distributionはpilot前の再設計対象であり、この初期値のまま
formal fullを承認しない。

### 3.1 PC属性と利用形態の初期仮説

職種名だけでは1人のPCを再現したことにならない。persona manifestには少なくとも
`os_semantics`、`device_class`、`locale`、ordered `languages`、`work_style`、
snapshot-only `sync_sources`、`sensitivity_profile`、depth histogramを持たせる。
OSは生成を実行するOSではなく、模擬対象PCのpath・case・locale特性であり、native実行か
emulationかを別フィールドで明記する。syncはlive接続せずsynthetic snapshot/importだけを使う。

| id | OS・端末仮説 | 言語 | 主な仕事の型 | synthetic流入元 | 機密度 | nesting型 |
| --- | --- | --- | --- | --- | --- | --- |
| p01 | macOS開発laptop | 日英 | release・非同期開発 | Git/Drive snapshot | S1/S2 | product/repo, D4 |
| p02 | Ubuntu workstation | 英 | on-call・log追記 | Git/server exports | S2/S3 | service/env/oncall, D5 |
| p03 | Windows管理laptop | 日英 | audit・incident案件 | SharePoint/SIEM exports | S3 | control/evidence, pilot D4 |
| p04 | Ubuntu GPU workstation | 英＋paper metadata | experiment/batch | Git/object-store exports | S1/S2 | program/model/experiment, D5 |
| p05 | Windows業務laptop | 日＋英schema | report/dashboard定期更新 | OneDrive/warehouse exports | S2 | analytics/report, D3 |
| p06 | Windows lab workstation | 英＋科学識別子 | protocol/cohort batch | SMB/instrument exports | S2/S3 | study/cohort, D5 |
| p07 | macOS研究laptop | 英＋引用多言語 | 長文執筆・archive/OCR | archive/drive imports | S0/S1 | source/chapter, pilot D5 |
| p08 | macOS業務laptop | 日英 | meeting・四半期roadmap | Drive/Teams exports | S2 | product/quarter, D5 |
| p09 | macOS研究laptop | 英＋日本語引用 | interview/media session | recorder/research imports | S2/S3 | study/session, D3 |
| p10 | Windows＋VDI export | 英 | client phase/deliverable | data-room/Teams exports | S3 | client/year/phase, D5 |
| p11 | Windows travel laptop | 英西 | mail/call/proposal | Outlook/CRM exports | S2 | account/opportunity, D3 |
| p12 | Windows管理laptop | 日英 | queue・高頻度更新 | ticket/CRM exports | S2 | customer/case, D3 |
| p13 | Windows DLP laptop | 日英法務 | matter/legal-hold/version | DMS/mail exports | S3 | matter/hold, pilot D5 |
| p14 | Windows財務laptop | 日英会計code | month-close/final-copy | ERP/OneDrive exports | S3 | year/quarter/month, D5 |
| p15 | Windows HR laptop | 日＋synthetic romanized名 | requisition/case | ATS/HRIS exports | S3 | requisition/candidate, pilot D4 |
| p16 | Windows clinical VDI | 日英medical | protocol/regulatory append | EDC/secure-SMB snapshot | S3 | study/year, D5 |
| p17 | Windows field laptop | 日英drawing code | offline field/revision | CDE snapshot | S2 | project/year/construction, D6 |
| p18 | Windows engineering WS | 日英規格 | controlled-doc/batch | QMS/PLM exports | S2 | product/quality, pilot D4 |
| p19 | ChromeOS由来snapshot | 日英 | term/bulk LMS import | Drive/LMS exports | S2 | course/year/term, D6 |
| p20 | macOS暗号化laptop | 日英 | deadline/evidence-chain | mail/FOIA/drop imports | S3 | story/year/evidence, D5 |

`S0=公開、S1=社内、S2=機密、S3=厳格管理`。この表は統計ではなく、再現可能な
初期仮説である。synthetic-only、実PII/PHI/credentialなし、network/live syncなしは契約にするが、
正確なroleとOSの組合せや人口比であるという主張はしない。

現行のmanaged fileはleaf scope直下だけなので、性能測定には明瞭だがPC fidelityとしては
平坦すぎる。次の2 laneを分離する。

1. **formal flat-scope lane**: 1人20 active leaf scopes、chunk/latencyの厳密gate。
2. **recursive robustness lane**: 深いambient tree、未登録noise、conflict copy、partial-download風
   sentinel、Unicode/case衝突候補を追加し、構造耐性を測る。ただし正式chunk母数へ混ぜない。

全員共通の8 secondary paths、20 leaf、75/25 loadも現状は比較可能性のための仮説であり、
persona fidelityの完成形ではない。pilotでは人物別に業務60--85%、共同作業5--20%、
流入/download 5--20%、無関係なbenign noise 3--10%を初期探索範囲とする。

## 4. 人別の物理ファイル比率（15 family）

分母は各人のW0物理direct-child filesであり、logical item比、byte比、chunk比ではない。
またこれはfamily比でありextension比ではない。例えば`pdf_text`と`pdf_scan`はどちらも`.pdf`、
family内の複数variantは後段の規則でextensionへ配分される。

| persona | md | txt_log | code | structured_text | csv_tsv | html_eml | ipynb | pdf_text |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| p01 | 22% | 8% | 28% | 12% | 3% | 5% | 1% | 7% |
| p02 | 20% | 22% | 15% | 20% | 5% | 3% | 0% | 4% |
| p03 | 10% | 12% | 8% | 15% | 10% | 8% | 0% | 15% |
| p04 | 12% | 7% | 18% | 10% | 12% | 2% | 12% | 12% |
| p05 | 8% | 5% | 6% | 14% | 20% | 5% | 5% | 5% |
| p06 | 6% | 6% | 3% | 5% | 15% | 2% | 3% | 18% |
| p07 | 12% | 10% | 0% | 4% | 3% | 5% | 0% | 25% |
| p08 | 10% | 4% | 1% | 5% | 8% | 8% | 0% | 13% |
| p09 | 8% | 15% | 0% | 4% | 8% | 3% | 0% | 10% |
| p10 | 4% | 4% | 0% | 2% | 8% | 6% | 0% | 18% |
| p11 | 3% | 4% | 0% | 2% | 5% | 25% | 0% | 16% |
| p12 | 15% | 20% | 4% | 15% | 12% | 12% | 0% | 5% |
| p13 | 3% | 4% | 0% | 1% | 2% | 14% | 0% | 28% |
| p14 | 3% | 3% | 1% | 4% | 15% | 5% | 0% | 13% |
| p15 | 4% | 5% | 0% | 2% | 7% | 15% | 0% | 20% |
| p16 | 5% | 6% | 1% | 4% | 10% | 4% | 1% | 24% |
| p17 | 3% | 4% | 0% | 2% | 5% | 4% | 0% | 20% |
| p18 | 6% | 12% | 2% | 6% | 15% | 3% | 0% | 18% |
| p19 | 8% | 5% | 0% | 2% | 5% | 5% | 0% | 20% |
| p20 | 8% | 18% | 1% | 3% | 8% | 10% | 0% | 16% |

| persona | pdf_scan | docx | xlsx | pptx | image | media | domain_binary |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| p01 | 1% | 3% | 2% | 2% | 3% | 0% | 3% |
| p02 | 0% | 2% | 1% | 1% | 2% | 0% | 5% |
| p03 | 5% | 5% | 4% | 2% | 3% | 0% | 3% |
| p04 | 1% | 2% | 3% | 3% | 5% | 0% | 1% |
| p05 | 1% | 3% | 15% | 4% | 3% | 0% | 6% |
| p06 | 8% | 8% | 8% | 5% | 9% | 0% | 4% |
| p07 | 20% | 10% | 1% | 2% | 6% | 1% | 1% |
| p08 | 3% | 15% | 8% | 15% | 7% | 1% | 2% |
| p09 | 4% | 12% | 4% | 8% | 15% | 7% | 2% |
| p10 | 5% | 12% | 18% | 18% | 3% | 0% | 2% |
| p11 | 4% | 14% | 7% | 10% | 5% | 3% | 2% |
| p12 | 1% | 3% | 2% | 1% | 7% | 1% | 2% |
| p13 | 15% | 22% | 3% | 2% | 3% | 0% | 3% |
| p14 | 8% | 8% | 27% | 7% | 3% | 0% | 3% |
| p15 | 8% | 20% | 8% | 3% | 5% | 1% | 2% |
| p16 | 12% | 10% | 8% | 5% | 6% | 1% | 3% |
| p17 | 12% | 8% | 10% | 4% | 12% | 1% | 15% |
| p18 | 6% | 8% | 10% | 3% | 5% | 0% | 6% |
| p19 | 8% | 15% | 7% | 12% | 8% | 3% | 2% |
| p20 | 10% | 8% | 2% | 2% | 8% | 4% | 2% |

初期variant内訳は `.md/.markdown=70/30`、`.txt/.log/.jsonl=70/20/10`、
`.py/.rs/.ts=34/33/33`、JSON/YAML/XML/SQL=35/25/20/20、CSV/TSV=70/30、
HTML/EML=60/40である。それ以外は現在1 variantである。

full 1 replayの195,000 W0 filesへ上の人別比率を重み付き適用したsuite集計は次のとおり。
これは容量・inode・renderer回数を見積もるための物理file-count分布であり、検索可能chunkの
分布ではない。

| family | files | suite file比 | family | files | suite file比 |
| --- | ---: | ---: | --- | ---: | ---: |
| md | 18,300 | 9.38% | txt/log | 18,930 | 9.71% |
| code | 10,400 | 5.33% | structured text | 15,070 | 7.73% |
| csv/tsv | 17,760 | 9.11% | html/eml | 13,990 | 7.17% |
| ipynb | 2,240 | 1.15% | text PDF | 27,340 | 14.02% |
| scan PDF | 11,160 | 5.72% | docx | 16,470 | 8.45% |
| xlsx | 13,630 | 6.99% | pptx | 9,620 | 4.93% |
| image | 11,140 | 5.71% | media | 2,150 | 1.10% |
| domain binary | 6,800 | 3.49% | **total** | **195,000** | **100.00%** |

これはW0 renderer/allocatorの基準としては有用だが、全員の`domain_binary`がPCAPになるのは
人物再現として不十分である。pilot前にrole別variant profileを導入し、例えばSRE/securityは
PCAP、constructionはIFC/ZIP、clinicalはDICOM風synthetic container、BI/financeはSQLite/
compressed exportのように分ける。未知拡張子はsearchable contributorへ数えない。

## 5. file count以外に分けて持つ比率

実PCらしさのため、次の4分布を混同しない。

1. physical file count比（上表）
2. logical member比（mail attachment、PDF page、sheet、slideなど）
3. allocated byte比（filesystem blockを含む）
4. current/history chunk比

pilotでは少なくとも次のsize/complexity bucketを実装・実測する。

| 対象 | small | medium | large | tail | 初期比率 |
| --- | --- | --- | --- | --- | --- |
| text/code | 1–4 chunks | 5–20 | 21–50 | 51–72 | 55/30/12/3 |
| text PDF | 1–5 pages | 6–30 | 31–200 | 201+ | 40/35/20/5 |
| EML | 0 attachment | 1 | 2–5 | 6+ | 65/25/9/1 |
| XLSX | 1 sheet | 2–5 | 6–20 | 21+ | 45/40/13/2 |
| PPTX | 1–10 slides | 11–40 | 41–100 | 101+ | 45/40/13/2 |
| image/media/domain | <256 KiB | 256 KiB–4 MiB | 4–64 MiB | 64–100 MiB | 35/40/20/5 |

この共通envelopeをそのまま全員へ複製せず、personaごとに重みを変える。p10/p14のような
高密度personaはstable contributor file数を増やすか、承認済みlocal Office変換を追加し、
p95が上限72へ張り付かないようにする。最小valid Office/PNG/WAV/PCAPだけでpilot容量を
推定することは禁止する。

## 6. 実装・生成・編集・再現・検証の順序

1. **W0 plan**: 20人×20 scopes、形式×scope cell、全source ID、1–72の予定quotaを凍結。
2. **W0 create**: source bytesとphysical/logical/search-plan ledgerを原子的に生成。
3. **W0 prepare/init/index**: 編集前の履歴境界を作り、planned quotaと実chunkを分離して記録。
4. **event manifest freeze**: 全eventのbefore/after hash、scope、chunk deltaをmutation前に検証。
5. **W1-W5 edit in place**: edit/rename/move/duplicate/derive/archive/delete/restore/purgeを適用し、
   各waveの通常変更はscopeごとに1回だけindexする。
6. **fresh replay x3**: 同じimmutable plan/eventをW0から3 rootへ独立再実行し、hard linkや
   `.kcs`コピーを禁止する。完成rootの複製は履歴再現とは認めない。
7. **attest**: 60独立registries、1,200 scopesについて、各人120,000 current、W5
   current+history 180,000以上、raw-only 0、3 replayのcanonical state一致を実測。
8. **evaluate**: 全root完成後だけRecall、履歴検索、latency、disk/inode/RSSを測定。

W0 indexは最終評価ではなく、編集を履歴として観測するための必須境界である。先に編集してから
初回indexすると、W0は履歴に存在しないため、この順序を入れ替えない。

上の1–5を最初の1 rootだけで実行してからコピーする意味ではない。凍結したplan/eventを入力に、
`replay-01`、`replay-02`、`replay-03`の各fresh rootでW0からW5まで独立実行する。開発用の
rehearsal rootを別に作る場合、それはformal 3 replayへ数えず、formal評価前に破棄する。

### 6.1 履歴chunkを破綻させないcohort案

排他的なraw-file bucketではなく、whole-sourceのcontract-contributor chunkをperson単位で
同時割当する。fullの相互排他的cohortは次である。

| cohort | W0比 | wave操作 |
| --- | ---: | --- |
| P | 4% | W1 edit、W5で旧pathを全履歴purgeし同一quotaのP'へ置換 |
| X | 10% | W1 edit、W3 major edit、W4 deleteし同一quotaのX'へ置換 |
| Y | 6% | W1 edit、W3 major edit、現行のまま保持 |
| N | 4% | W3 major edit、W5 correction |
| U | 76% | arithmetic control。安全な一部だけrename/duplicate sentinelに利用 |

fullではW1が`P+X+Y=20%`、W3が`X+Y+N=20%`、W4が`X=10%`を履歴へ加える。
W5ではNの旧版4%と、Pをcurrentから外した版4%が一旦履歴へ加わる。その後、Pの各pathを
purgeするとW0版+W1版の合計8%が削除され、最終的にcurrent 120,000、history-only 60,000へ戻る。
P/Xのreplacementは同じscope・variant・quota、別source/pathとし、形式比とcurrent量を維持する。

W5の安全な順序は `(N correction + P' create while old P remains) -> index_auto
-> [remove one old P -> purge that old path] x P source order -> index_noop` である。先にP'をindexして
normalize bindingを確立し、purged commit自身にold Pのtree deletionを持たせる。中間auto commitでは
currentが124,800、history-onlyが64,800へ一時増加し、final purged commitで120,000/60,000へ戻る。
この一時peakもcapacity receiptへ含める。Pはrename/move/duplicate禁止、各old pathはW0/W1の
2 raw versionsだけを持つ。1 pathずつ削除直後にpurgeするため、各purged commitが
`files_deleted=1`を持つ。`--raw-hash`は1版しか消さないため、このケースはpath purgeを使う。

exact chunk合計はscope別割合ではなく**person全体**でsolverが合わせる。scopeごとに割合を丸めると
fullでもedit 187/400、delete 244/400、purge 287/400 cellsが整数quota制約で不可能だった。
fullではP/X/Y/Nの全cohortを各20 scopesへ正のquotaで配置する。tinyはcohortごとのsource数が
20未満になり得るためcohortの20-scope coverageを要求しない。
fullではsource IDのhash-spread順を使い、1 scopeのcohort負荷をcohort全体の20%+最大1 source
（72 chunks）以下へ制限する。単に各scopeへ1件置いて残りを1 scopeへ偏らせる割当は拒否する。
tinyの丸めは`E=20% target; P=4%; X=10%; Y=E-P-X; N=P`とし、独立floorの加法誤差を避ける。

cross-scope move/archive/restore、near-duplicate、derived-format、createは、最初の実装では
quota 0のraw-only sentinelに限定する。これは構造・CLI lifecycleの検証であって検索Recallの
証拠ではない。検索可能なcross-scope moveを追加する場合、`(scope_key, chunk_id)`が別identityに
なるためW2 history targetを別契約で増やす。同一scope renameとexact duplicateは安全なU contributorで
検索/path-aliasを検証できる。

構造event数はtiny/pilotで1人11件、fullで1人30件に固定する。fullの内訳は
`W1=3, W2=21, W3=3, W4=2, W5=1`で、W2は20 scopes各1件のU renameと1件の
raw-only cross-scope moveを持つ。tiny/pilotのW2は代表U rename 1件+move 1件である。
W1のcreateをW4でdeleteし、W5で別の既存active scopeへpath restoreする。`archive/closed`は
登録済みactive scopeのままであり、archiveは組織上の移動を意味する。

source、source version、materializationを分離する。rename/move/archiveは同一materialization、
exact copyとrestoreは同一source/version/rawから新materialization、near/derive/createは新sourceを使う。
near PNGは親のRGB 1 channelだけを±1し、derived scan PDFは別の親PNGの同じdecoded pixelsを
text layerなしで埋め込む。このwitnessを再計算できないeventは拒否する。

full 1 replayのW0は195,000 physical files、400 scopes、2,400,000 planned current chunksである。
structural sentinelは1人あたり新source ID +3、final live +4なので、final activeは
1 replay 195,080、3 replay 585,240 filesになる。P/X replacementを含むlifecycle distinct
source IDsは1 replay 204,766、3 replay 614,298になる。3 replayは1,200 scopes、
7,200,000 current planned chunks、
W5後は10,800,000 current+history contract chunksを計画する。W5 pre-purgeの一時peakは
1 replay 3,792,000、3 replay 11,376,000 contract chunk identitiesであり、最終値だけで
容量を見積もらない。fullのW4+W5 contributor replacementは1 replay 9,706 files、
3 replay 29,118 filesを追加生成する。

## 7. 現時点の実装境界

実装済み:

- 20人・400 scope・15 familyのmachine-readable spec
- 20人ごとのOS/locale/language/work-style/source/sensitivity/nesting/size/domain-binary
  fidelity仮説metadataと、共通small/medium/large/tail size-complexity bucket
  （どちらも実ユーザ統計ではなくrenderer未適用）
- 決定論的format×scope allocatorとsource-level quota
- 25 variantの標準ライブラリrenderer
- physical/logical/search-planの3 ledgerとsuite manifest
- P/X/Y/N whole-source contributor cohort allocatorとcanonical rebuild validator
- quota-neutral structural allocator、parent-bound transform dispatcher、canonical validator
- event/boundary/scheduleを分離したroot-independent planned event manifestとleaf算術検証
- 20人の個人manifestをhash束縛し、root-wide lock下の全順序を固定するsuite schedule
  （tiny tested）
- 1人ずつのbounded event shardと、20 compact summariesからschedule/locator/MMRを作る
  O(20) suite composer（tiny legacy SHA exact、formal publicationは未承認）
- W0不変内容とpost-W0 runtime envelopeを分離したread-only verifier
- 1人分のplanを最大16,000 sources、8 MiB、20 scopesに制限して構築・再検算するAPI
- fullの43,596 events / 5,175 boundaries / 48,771 schedule items/replayを
  event manifest非構築で導出するcount/resource oracle
- pilot/root読み戻し前はblockedのcapacity projection/receipt API
- no-replace canonical JSONL shard storage（source inode rename blockerにより常にnon-formal）
- root directory/owner markerをinode固定し、W0 bytesを変えず保持するread-only
  replay-root lease primitiveとlease-held root FD貸出し（POSIXのみ。executor未接続）
- strict KCS result/environment/binary-receipt boundary（TOCTOU対策完了前は全execution/mutation gate false）
- canonical all-person plan SHAを1人ずつ再構成し、root/person/device/scopeのexact 20×20と
  宣言artifact SHAを束縛するnon-executing prepare-receipt composer（全semantic claim false）
- profile、canonical scope quota、file bytes/content rootを束縛するpartial semantic attestor
  （完全形状でも`history_ready_attested=false`）
- no-replace/owned-root/capacity/reparse/hard-link安全境界
- tiny W0 writer（4,000 files、400 shards、4,131 planned chunks）
- 2 fresh tiny rootのbyte同一性、inode非共有、strict no-op、改ざん拒否

未実装または未承認:

- metadataを実bytesへ反映するpersona別rich size distribution、role別extension/domain-binary renderer、
  native/emulated OS behavior（現行render behaviorは未変更）
- W0 init/index prepare executor・native FD-bound SQLite/WAL snapshotを含むcomplete KCS semantic
  history-ready attestor、W1-W5 safe mutation/journal/replay、query generator
- pilot/fullのW0 writer・suite streamのformal publication/RSS/readback/`wait4` gate・実測byte cap
- Windows directory-handle durability（planは可、物理publishは現状blocked）
- full 120,000 actual KCS chunks/personの証明

履歴blockerの原因は確定した。現行の「raw filesの1%をpurged」と「4%=4,800 chunksをpurge」は
別々に割り当てられ、full 20人中16人で両立しない。上記P/X/Y/Nのjoint modelは現行W0 plan上の
tiny/pilot/full全60 persona-profileでexact subsetが存在し、full P/X/Y/Nの20-scope coverageも実現可能と
確認し、source-ID cohort allocator、structural allocator、planned event manifestのcanonical
rebuild validatorまで実装した。full 1 replayではP path 2,775件、X replacement 6,931件、P+X
replacement 9,706件となる。root-wide leaseとlease-held root FD貸出しは実装したが、W0
history-ready receipt、prepare executor、safe mutation、append-only journal、replay executorは
未実装なので、W1-W5 mutationは引き続きfail closedとする。
planned quota/manifestは実KCS chunk attestationの代用ではない。

full count/resource oracleの3 replay値は130,788 events、15,525 boundaries、146,313 schedule itemsである。
上限はpersona plan 8 MiB、sources 16,000、scopes 20、worker RSS 384 MiB、composer RSS
128 MiB、process tree RSS 512 MiB、worker同時1、JSONL 512 rows/shardかつ32 MiB/shardの早い方である。
ただしworker/suite receiptは呼出側が宣言したprojectionであり、
`formal_capacity_gate_satisfied=false`のままである。artifact readbackとsupervisor `wait4`証拠が必要である。

capacity projectionはcanonical pilot measurement receiptの読み戻し前は
`blocked_missing_pilot_evidence`、root-bound checkはfilesystem identity/allocation unit/availability/cap/reserve
の読み戻し前は`blocked_measurement_receipt_readback_required`である。どちらもphysical
writeまたはactual KCS attestationを許可しない。streaming storageはcanonical shardを
no-replace publish/readbackするが、verified source directory inodeをrenameのatomic preconditionにできないため、
`formal_publication_attested=false` / `source_directory_inode_not_bound_by_rename`である。

KCS runnerはvalidatorとisolated environment recipeを持つが、scope path検証後の
`Popen(cwd=...)`にsame-user TOCTOUが残る。そのため`HANDLE_RELATIVE_EXECUTION_AVAILABLE`、
`PERSONA_FILESYSTEM_MUTATION_AVAILABLE`、`TRUSTED_BINARY_EXECUTION_AVAILABLE`はすべてfalseであり、
init/index/version subprocessもpersona mutationも実行しない。partial semantic attestorはprofile、
persona/scope identity、quota算術、file content rootsとtyped callback receiptsを束縛するが、
SQLite/CAS、HEAD/commit、binary/config、root/prepare intentの完全な検査ではなく、
20人/400 scopes/20 devicesが揃ってもformal semantic coverageと
`history_ready_attested`はfalseである。checker-local observationは
`formal_transport_attested=false`固定で、legacy nine-field callbackへ昇格できない。
各directoryは名前またはMerkle childを保持する前に16,384 direct entriesでhard capされる。
`HISTORY_ASSIGNMENT_EXECUTABLE=False`を維持する。

lease-derived callbackはtrusted-rootのpath-check/open seamを閉じるが、同一process checkerの
FD複製・一時再束縛、same-UID ABA、immutable snapshot/process isolationは未解決である。
さらにPython標準`sqlite3`ではheld directory FDをauthorityにしてscope DBとregistry
main/WAL/SHMをcross-platformに同一epochで検査できない。native read-only VFSまたはwriter排除下の
immutable snapshotが入るまで、actual chunk/history-readyを主張しない。

post-W0 verifierはstrict W0 exact-tree verifierを緩めない。別APIでW0のowner/root binding、
ledger、source bytesを再検証し、canonical intentが宣言する400個の`.kcs`と20個の
`.kcs-eval-device`、固定`.kcs-persona-history/{control,receipts}`だけを外側envelopeとして許す。
opaque内部はtyped semantic attestorがdirectory identity/content-rootを証明しない限り
`opaque_unattested`であり、常に`history_ready_attested=false`を返す。これはprepare/replayの
安全な前提であって、init/index実行やhistory-ready receiptそのものではない。

tiny全20人のsuite scheduleは1,076 events、908 boundaries、1,984 itemsで、W1--W4を
全persona regular events→全ordinary indexes、W5を全regular→全ordinary indexes→
persona/source順のpurge event/commit pair→全noop indexesへ直列化する。個人manifestの
self hash、phase、logical order、root/host非依存性を再検証し、単一`prior_item_id`鎖へ束縛する。
旧in-memory builderとは別に、1人分のevent manifestだけを保持して
events/boundaries/schedule projectionをbounded shardへpublishし、20 compact summariesから
global schedule、external row locator、schedule/locator MMRを作るO(20) composerを実装した。
tinyの件数、schedule SHA-256、suite-manifest SHA-256は旧builderと完全一致する。
ただし下位storageの`source_directory_inode_not_bound_by_rename`を継承して
`formal_publication_attested=false`であり、fullのsupervisor実測RSS、artifact readback、`wait4`
receiptも未証明である。このlayerはformal fullまたはW1-W5 mutationを実行可能にしない。

2026-07-14のfresh-process開発probeでは、p01/full planned manifestは23,487,210 bytes、
4,693 events、421 boundaries、5,114 schedule items、最大RSS 166,510,592 bytes、79.17秒だった。
全員中event数最大のp02/fullは25,389,043 bytes、5,087 events、446 boundaries、5,533 items、
最大RSS 185,860,096 bytes、92.37秒だった。全20人のplanだけを1人ずつ生成した場合は合計
58,300,452 bytes、最大person plan 4,697,330 bytes、最大RSS 66,109,440 bytesだった。
これらはplanner実装可能性の参考値で、20人full物理生成・KCS index・正式性能gateの達成値ではない。

full 1 replayの正確なplanned件数は43,596 events、5,175 boundaries、48,771 schedule itemsで、
3 fresh replayでは各130,788、15,525、146,313 executionになる。full suiteはperson shardを
逐次publishし、global in-memory manifestを作らない。初期上限はpersona worker 384 MiB、
coordinator/composer 128 MiB、process tree 512 MiB、同時worker 1、persona plan 8 MiB、
event logical bytes 64 MiB/person、events 6,000、boundaries 600、schedule 6,600とする。
JSONL shardは512 rowsまたは32 MiBの早い方で切り、全20 workerのreceiptが上限内であることを
formal full承認前に実測する。

同日の別のread-only開発probeでは、fresh tiny W0のp01だけを20独立scopeとして
`init -> index --offline --yes`し、planned contributor 375に対してactual contributor 375、
incidental 47、raw-only 0を確認した。各scopeの初回commitはparentなしのauto commit 1本で、
再indexはHEAD不変のstrict noopだった。raw payload約0.80 MiBに対して20個の`.kcs`は
allocated約14.8 MiBであり、小さなscopeを多数持つ構成ではSQLite/CAS固定費が支配的になる。
これはp01/tinyの実装可能性probeであって、400 scope history-ready barrier、pilot/full容量、
または120,000 actual chunks/personの証拠ではない。

同日の別fresh rootでは、tiny全20人・400 scopes・4,000 W0 files・4,131 planned chunksを
生成し、plan SHA
`fb0f704a94f596bac8b9e00188e0908c06f8233923567b11b45125aaae5adaaa`を再確認した。
このうちp01の2 scopesだけをisolated offline `init/index`で開発probeした。primary-01は
20 physical sourcesのうち13 contributorから38 chunks、7 incidentalから7 chunksで合計45、
primary-09は10 sourcesのうち6 local contributorだけがSQLite/chunkへ入り、4 DOCXはHEAD treeと
raw CASには存在するがnormalizeなし・SQLite `tree_entries`なし・pending online taskとなった。
したがってformal attestorは「HEAD tree=全physical sources」と「SQLite tree_entries=normalized
sources」を別台帳として検査しなければならない。この2-scope結果も400-scope attestationではなく、
外部APIを使わない開発probeに限る。

現行20人はMVPの**職業知識労働者**を広くstressする集合であり、家庭用PC人口を代表しない。
creative/media制作、学生個人、家庭写真中心、SMB general-adminまで対象を広げる場合は、既存比率を
統計とみなさずpersonaの入替えまたは追加suiteを行う。

variant fidelity全体もpilot blockerである。現在は全員のimage/media/domain binaryが
PNG/WAV/PCAPへ寄り、archive familyもない。JPEG/HEIC/TIFF/SVG、M4A/MP3/MP4、ZIP/7z、
SQLite/Parquet、role別IFC/DICOM風container、legacy Office/MSG等を、検索寄与を勝手に主張しない
raw-only variantとして追加する。persona manifestにはdata-age/retention、update cadence、
duplicate/conflict率、naming disorder/Unicode、hidden/empty/noise counts、byte分布、
permission/unreadable、sync-stateも持たせる。

## 8. 現在使えるW0コマンド

生成物はGit外、既存しないplain parent配下へ置く。

```bash
python3 eval/generate_persona_corpus.py plan \
  --profile tiny \
  --plan-out /private/tmp/kcs-persona-tiny-plan.json

mkdir -p /private/tmp/kcs-persona-runs
python3 eval/generate_persona_corpus.py generate \
  --plan /private/tmp/kcs-persona-tiny-plan.json \
  --out /private/tmp/kcs-persona-runs/replay-01 \
  --replay-id replay-01

python3 eval/generate_persona_corpus.py verify \
  --plan /private/tmp/kcs-persona-tiny-plan.json \
  --root /private/tmp/kcs-persona-runs/replay-01 \
  --replay-id replay-01
```

macOSの`/tmp`はsymlinkなので安全境界が拒否する。`/private/tmp`または
`Path(tempdir).resolve()`を使う。`pilot`/`full`はplan生成のみ可能で、物理writeは
streaming/RSS/pilot capacity gateが入るまで明示的にblockedである。
