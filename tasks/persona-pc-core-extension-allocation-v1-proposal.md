# Persona-PC core extension allocation v1 proposal

Status: proposal only。G0、source recipe、source instance、solver、renderer実行、filesystem write、
Kio、history、replay、evaluationの権限を与えない。

Date: 2026-07-18

## 1. 結論

`persona-core-v1`のfamily内extension配賦は、新しい人物別比率を追加せず、次の3入力だけから
決定的に導出する。

1. `persona-core-v1`の20 persona x 15 family exact W0 file count matrix
2. 既存persona-PC v2 envelopeの人物別variant weightとvariant ordinal
3. frozen all-71 format implementation registryのvariant、extension、role、renderer/validator binding

full、pilot、tinyはそれぞれのfamily countから独立に
`hamilton-largest-remainder-v1`で整数化する。full countを10で切り捨ててpilotを作らない。
core denominatorに入れるのはall-71 registryに実装済みのcanonical variantだけである。
`.msg`、`.xlsm`、`.xlsb`、`.dwg`、`.dxf`、未登録mediaなどはcanonical fallbackで同数を
置換し、coreの203,000 filesを変えない。

この規則を説明するcompact ruleは十分だが、freeze、writer、3 fresh replayの境界では、導出した
566-row sparse manifestをmaterializeし、独立validatorで再生成一致を確認する。denseな
`20 x 15 x 39`手書きmatrixを正本にしない。

人物別family比とvariant比は、実在PCを観測して推定した統計ではない。すべてversion/hash付きの
authored benchmark hypothesisであり、dogfoodや実データの観測結果として表示しない。

## 2. 三つの入力pin

canonical JSONはNFC文字列、UTF-8、key sort、compact separator、terminal LFなしとする。
入力providerはvalidation前後で同一bytes/SHAを返さなければならず、projectionを検証後に差し替える
TOCTOUを拒否する。

| order | input | consumed projection | canonical bytes | SHA-256 | authority |
| ---: | --- | --- | ---: | --- | --- |
| 1 | `kio.persona.core-family-count-matrix/v1` candidate | 下表の`family_order`、p01--p20、full exact counts | 2,410 | `045d85cf7325d0ec51217f61f2069b6dd145bfcb3b4477b4eb005d0a800d9ab7` | proposal-only、all false |
| 2 | `kio.persona.pc-envelope/v2` | `personas[].persona_id`と既存`variant_profiles`、宣言順ordinal | 71,979 | `12a5f175cbcd9b1ea9886c8a8e3b673b857f6b314ba48c9b71e6b279150244a7` | envelope全体をpinするがcore adoption権限なし |
| 3 | `kio.persona.pc-format-implementation-registry/v2` | 71 implementation rows、extension、role、disposition、renderer/validator binding | 333,881 | `59ae0b2e5c755732e6937e70ada4b243ea2c7432a9ce654c7e9c219b4a13bc5d` | renderer/validator feasibilityのみ、`g0_contract_frozen=false` |

input 1のcanonical bodyは次のshapeである。

```json
{"family_order":["md","txt_log","code","structured_text","csv_tsv","html_eml","ipynb","pdf_text","pdf_scan","docx","xlsx","pptx","image","media","domain_binary"],"profile_id":"persona-core-v1","rows":[{"counts":[2880,1200,3840,1680,480,600,24,720,12,24,20,20,480,0,20],"persona_id":"p01","total_files":12000},{"counts":[3000,4200,2250,3300,750,450,0,600,10,30,20,20,300,0,70],"persona_id":"p02","total_files":15000},{"counts":[600,500,30,1800,1400,1600,0,2400,400,800,300,20,100,0,50],"persona_id":"p03","total_files":10000},{"counts":[1000,400,2500,1400,1600,0,2000,700,10,20,20,20,300,0,30],"persona_id":"p04","total_files":10000},{"counts":[720,840,1200,2160,3000,30,25,600,10,25,2640,480,240,0,30],"persona_id":"p05","total_files":12000},{"counts":[320,320,20,400,1600,20,20,1840,1120,800,640,20,560,0,320],"persona_id":"p06","total_files":8000},{"counts":[700,700,0,210,210,280,0,1960,1540,980,20,15,350,20,15],"persona_id":"p07","total_files":7000},{"counts":[1200,20,10,240,320,480,0,1440,15,1760,640,1600,240,10,25],"persona_id":"p08","total_files":8000},{"counts":[270,1980,0,90,540,30,0,900,360,1170,30,450,1800,1350,30],"persona_id":"p09","total_files":9000},{"counts":[220,30,0,220,770,550,0,2200,330,1650,2530,2420,30,0,50],"persona_id":"p10","total_files":11000},{"counts":[300,500,0,20,200,2800,0,1800,25,2000,700,1200,400,20,35],"persona_id":"p11","total_files":10000},{"counts":[2880,4000,480,3200,1440,1920,0,800,20,480,30,20,640,30,60],"persona_id":"p12","total_files":16000},{"counts":[210,350,0,140,15,1260,0,2100,840,1750,140,20,140,0,35],"persona_id":"p13","total_files":7000},{"counts":[260,25,15,910,2600,390,0,2080,650,1300,4160,520,25,0,65],"persona_id":"p14","total_files":13000},{"counts":[320,320,0,15,720,1600,0,1920,160,2160,560,20,160,10,35],"persona_id":"p15","total_files":8000},{"counts":[160,160,15,320,1120,20,0,2080,1280,1280,480,20,400,25,640],"persona_id":"p16","total_files":8000},{"counts":[240,45,0,20,160,80,0,2000,960,400,800,240,1600,15,1440],"persona_id":"p17","total_files":8000},{"counts":[360,1920,30,480,2400,30,0,2160,600,1200,2160,60,240,0,360],"persona_id":"p18","total_files":12000},{"counts":[720,25,0,15,180,180,0,1620,360,1980,540,1800,1080,450,50],"persona_id":"p19","total_files":9000},{"counts":[600,2500,20,200,200,1500,0,2000,1200,300,15,15,1000,400,50],"persona_id":"p20","total_files":10000}],"schema":"kio.persona.core-family-count-matrix/v1"}
```

input 2は既存envelope全体をpinするが、core compilerが読んでよいのは人物ID、familyごとの
`(variant_id, weight, ordinal)`だけである。既存stress family count、stress variant count、source ID、
scope、history、query、solutionをcoreへ流用しない。private helperをruntime dependencyにせず、採用時に
このpinから公開されたread-only weight projectionを作る。

input 3は71 variantのID-free renderer/independent-validatorが存在することだけを証明する。
formal recipe、203,000 source instance、物理file、observed chunk、searchability、G0を証明しない。

## 3. 20 x 15 full exact family matrix

列順はinput 1の`family_order`で固定する。各rowは1人、1独立PC rootのW0 physical-file分母である。

| persona | md | txt | code | struct | csv | html | ipynb | pdf-t | pdf-s | docx | xlsx | pptx | image | media | domain | total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| p01 | 2,880 | 1,200 | 3,840 | 1,680 | 480 | 600 | 24 | 720 | 12 | 24 | 20 | 20 | 480 | 0 | 20 | 12,000 |
| p02 | 3,000 | 4,200 | 2,250 | 3,300 | 750 | 450 | 0 | 600 | 10 | 30 | 20 | 20 | 300 | 0 | 70 | 15,000 |
| p03 | 600 | 500 | 30 | 1,800 | 1,400 | 1,600 | 0 | 2,400 | 400 | 800 | 300 | 20 | 100 | 0 | 50 | 10,000 |
| p04 | 1,000 | 400 | 2,500 | 1,400 | 1,600 | 0 | 2,000 | 700 | 10 | 20 | 20 | 20 | 300 | 0 | 30 | 10,000 |
| p05 | 720 | 840 | 1,200 | 2,160 | 3,000 | 30 | 25 | 600 | 10 | 25 | 2,640 | 480 | 240 | 0 | 30 | 12,000 |
| p06 | 320 | 320 | 20 | 400 | 1,600 | 20 | 20 | 1,840 | 1,120 | 800 | 640 | 20 | 560 | 0 | 320 | 8,000 |
| p07 | 700 | 700 | 0 | 210 | 210 | 280 | 0 | 1,960 | 1,540 | 980 | 20 | 15 | 350 | 20 | 15 | 7,000 |
| p08 | 1,200 | 20 | 10 | 240 | 320 | 480 | 0 | 1,440 | 15 | 1,760 | 640 | 1,600 | 240 | 10 | 25 | 8,000 |
| p09 | 270 | 1,980 | 0 | 90 | 540 | 30 | 0 | 900 | 360 | 1,170 | 30 | 450 | 1,800 | 1,350 | 30 | 9,000 |
| p10 | 220 | 30 | 0 | 220 | 770 | 550 | 0 | 2,200 | 330 | 1,650 | 2,530 | 2,420 | 30 | 0 | 50 | 11,000 |
| p11 | 300 | 500 | 0 | 20 | 200 | 2,800 | 0 | 1,800 | 25 | 2,000 | 700 | 1,200 | 400 | 20 | 35 | 10,000 |
| p12 | 2,880 | 4,000 | 480 | 3,200 | 1,440 | 1,920 | 0 | 800 | 20 | 480 | 30 | 20 | 640 | 30 | 60 | 16,000 |
| p13 | 210 | 350 | 0 | 140 | 15 | 1,260 | 0 | 2,100 | 840 | 1,750 | 140 | 20 | 140 | 0 | 35 | 7,000 |
| p14 | 260 | 25 | 15 | 910 | 2,600 | 390 | 0 | 2,080 | 650 | 1,300 | 4,160 | 520 | 25 | 0 | 65 | 13,000 |
| p15 | 320 | 320 | 0 | 15 | 720 | 1,600 | 0 | 1,920 | 160 | 2,160 | 560 | 20 | 160 | 10 | 35 | 8,000 |
| p16 | 160 | 160 | 15 | 320 | 1,120 | 20 | 0 | 2,080 | 1,280 | 1,280 | 480 | 20 | 400 | 25 | 640 | 8,000 |
| p17 | 240 | 45 | 0 | 20 | 160 | 80 | 0 | 2,000 | 960 | 400 | 800 | 240 | 1,600 | 15 | 1,440 | 8,000 |
| p18 | 360 | 1,920 | 30 | 480 | 2,400 | 30 | 0 | 2,160 | 600 | 1,200 | 2,160 | 60 | 240 | 0 | 360 | 12,000 |
| p19 | 720 | 25 | 0 | 15 | 180 | 180 | 0 | 1,620 | 360 | 1,980 | 540 | 1,800 | 1,080 | 450 | 50 | 9,000 |
| p20 | 600 | 2,500 | 20 | 200 | 200 | 1,500 | 0 | 2,000 | 1,200 | 300 | 15 | 15 | 1,000 | 400 | 50 | 10,000 |
| suite | 16,960 | 20,035 | 10,410 | 16,820 | 19,705 | 13,820 | 2,069 | 31,920 | 9,902 | 20,109 | 16,445 | 8,980 | 10,085 | 2,330 | 3,410 | 203,000 |

family matrixのdominant/supportingは各persona totalの99%、rare groupはexact 1%、absentは0である。
このmatrixでは`0 < family_count < persona_total / 100`をrare family、`family_count = 0`をabsent、
`family_count >= persona_total / 100`をdominant/supportingとする。全personaでrare family countの合計が
`persona_total / 100`へexact一致することを検証する。family内extension配賦はfamily totalを変えてはならない。

## 4. Hamilton配賦規則

persona `p`、profile `q`、family `f`、宣言順variant `v_i`に対し、family countを`F`、
weightを`w_i`、`D = sum(w_i)`とする。

```text
numerator_i = F * w_i
base_i      = floor(numerator_i / D)
remainder_i = numerator_i mod D
missing     = F - sum(base_i)
```

`missing`件を`remainder_i`降順、同率は既存variant ordinal昇順で1件ずつ加える。weightは非負整数、
非空profileは`D = 100`、結果は非負整数、`sum(count_i) = F`でなければ拒否する。family countが0でも
宣言済みprofile rowは0件rowとして保持する。既存profile自体がemptyでfamily countも0の場合はrowを
新造しない。positive familyにempty profileが来た場合はfail closedとする。

### 4.1 full

input 1のexact family countを`F`として、input 2の人物別variant weightを適用する。結果は566 declared
persona/family/variant rows、539 non-zero rowsとなる。suiteでは71 variantすべてが1件以上になる。

| gate role | full files | share |
| --- | ---: | ---: |
| `contract_contributor` | 68,761 | 33.87% |
| `incidental_searchable` | 62,978 | 31.02% |
| `raw_only` | 71,261 | 35.10% |
| total | 203,000 | 100.00% |

roleはinput 3からのみ得る。physical formatの実装があることから、observed chunksやpositive Recallへの
参加を推論しない。

### 4.2 exact 10% pilot

personaごとに`pilot_total = full_total / 10`とする。まずfullの15-family count vectorをweightとして、
`pilot_total`をfamily ordinal順Hamiltonで配賦する。次に各pilot family countをvariant weightで配賦する。
full extension countを個別に10で切り捨てない。

非rare familyはfullの整数percentに由来し10で割り切れ、端数はrare family内にだけ残る。したがって
pilotのrare totalもpersona pilot totalのexact 1%になる。同率はfamily order、その内側ではvariant
ordinalで決める。各pilot variant countは対応full reservation以下でなければならない。

### 4.3 200-file tiny smoke

personaごとに`tiny_total = 200`とし、full family count vectorからfamily Hamilton、その後variant Hamiltonを
行う。rare totalはexact 2 filesである。2 filesでは全rare family/variantを覆えないため、tinyをformat比率
またはformat completeness gateにしない。tinyで0件になった必要variantは、core denominator外の独立した
coverage fixtureで最低1件を検証する。

## 5. all-71 canonical extension集合

all-71 registryが所有するphysical suffixはexact 39種類である。

```text
.aiff .bmp .cpp .csv .csv.gz .dcm .docx .eml .go .html
.ifczip .ipynb .jpg .js .json .jsonl .jsonl.gz .log
.markdown .md .mid .npz .pcap .pdf .png .pptx .py .rs
.sql .tar .tif .ts .tsv .txt .wav .xlsx .xml .yaml .zip
```

| family | canonical variants / extensions | formal role |
| --- | --- | --- |
| `md` | `md`, `markdown` | contributor |
| `txt_log` | `txt`; `log`, `jsonl` | contributor; incidental |
| `code` | `py`, `rs`, `ts`, `go`, `js`, `cpp` | contributor |
| `structured_text` | `json`, `yaml`, `xml`, `sql` | incidental |
| `csv_tsv` | `csv`, `tsv` | incidental |
| `html_eml` | `html`, `eml` | incidental |
| `ipynb` | `ipynb` | incidental |
| `pdf_text` | `pdf-text(.pdf)` | contributor |
| `pdf_scan` | `pdf-scan(.pdf)` | raw-only / awaiting OCR |
| `docx`, `xlsx`, `pptx` | 同名OOXML extension | raw-only / awaiting conversion |
| `image` | `png`, `jpg`, `tif`, `bmp` | raw-only |
| `media` | `wav`, `aiff`, `mid` | raw-only |
| `domain_binary` | ZIP 19、USTAR 10、CSV-GZIP 3、JSONL-GZIP 3、`dcm`、`ifczip`、`npz`、`pcap` | raw-only |

同じsuffixを複数variantが共有するcollisionはexactに次のとおりである。

- `.pdf`: `pdf-text`、`pdf-scan`
- `.csv.gz`: `assay-csv-gzip`、`csv-gzip`、`erp-csv-gzip`
- `.jsonl.gz`: `crm-jsonl-gzip`、`hris-jsonl-gzip`、`jsonl-gzip`
- `.tar`: 10個のpersona-domain USTAR variant
- `.zip`: 19個のpersona-domain ZIP variant

manifestとfilenameだけでvariantを再推論しない。各source rowは`variant_id`を保持し、extension、compound
suffix parts、magic、content MIME、expected Kio path MIME、container structure、independent validator
receiptをinput 3の同一implementation rowへ束縛する。`.csv.gz`と`.jsonl.gz`は`.gz`ではなくcompound
suffix全体を比較する。PDFはtext layer/scan structure、OOXMLとarchiveはcontainer member、mail/CADは
対応registryが追加された場合にそのmagic/MIMEを検証する。

## 6. all-20 rare exact 1% split

次はfullのrare family countへ現行variant weightとHamiltonを適用したexact結果である。domain archiveは
extensionが同じでもvariant IDを省略しない。

| persona / rare total | exact variant split |
| --- | --- |
| p01 / 120 | `ipynb` 24、`pdf-scan` 12、`docx` 24、`xlsx` 20、`pptx` 20、`source-export-zip` 14、`source-ustar` 6 |
| p02 / 150 | `pdf-scan` 10、`docx` 30、`xlsx` 20、`pptx` 20、`pcap` 21、`jsonl-gzip` 49 |
| p03 / 100 | `py` 21、`go` 6、`ts` 3、`pptx` 20、`pcap` 20、`evidence-zip` 30 |
| p04 / 100 | `pdf-scan` 10、`docx` 20、`xlsx` 20、`pptx` 20、`npz` 21、`model-metadata-zip` 9 |
| p05 / 120 | `html` 20、`eml` 10、`ipynb` 25、`pdf-scan` 10、`docx` 25、`warehouse-zip` 18、`csv-gzip` 12 |
| p06 / 80 | `py` 17、`cpp` 2、`ts` 1、`html` 14、`eml` 6、`ipynb` 20、`pptx` 20 |
| p07 / 70 | `xlsx` 20、`pptx` 15、`wav` 12、`aiff` 8、`tiff-ustar` 9、`archive-zip` 6 |
| p08 / 80 | `txt` 12、`log` 3、`jsonl` 5、`py` 6、`js` 1、`ts` 3、`pdf-scan` 15、`wav` 7、`aiff` 3、`product-export-zip` 18、`team-export-ustar` 7 |
| p09 / 90 | `html` 11、`eml` 19、`xlsx` 30、`recording-project-zip` 21、`session-ustar` 9 |
| p10 / 110 | `txt` 21、`log` 3、`jsonl` 6、`png` 15、`jpg` 11、`tif` 3、`bmp` 1、`data-room-zip` 40、`snapshot-ustar` 10 |
| p11 / 100 | `json` 11、`yaml` 2、`xml` 3、`sql` 4、`pdf-scan` 25、`wav` 14、`aiff` 6、`crm-zip` 21、`maildir-ustar` 14 |
| p12 / 160 | `pdf-scan` 20、`xlsx` 30、`pptx` 20、`wav` 24、`aiff` 6、`ticket-zip` 42、`crm-jsonl-gzip` 18 |
| p13 / 70 | `csv` 9、`tsv` 6、`pptx` 20、`dms-zip` 25、`legal-hold-ustar` 10 |
| p14 / 130 | `txt` 16、`log` 4、`jsonl` 5、`py` 11、`js` 1、`ts` 3、`png` 14、`jpg` 6、`tif` 4、`bmp` 1、`erp-csv-gzip` 39、`close-package-zip` 26 |
| p15 / 80 | `json` 7、`yaml` 2、`xml` 4、`sql` 2、`pptx` 20、`wav` 7、`aiff` 3、`ats-zip` 21、`hris-jsonl-gzip` 14 |
| p16 / 80 | `py` 12、`cpp` 2、`ts` 1、`html` 7、`eml` 13、`pptx` 20、`wav` 20、`aiff` 5 |
| p17 / 80 | `txt` 27、`log` 9、`jsonl` 9、`json` 5、`yaml` 3、`xml` 9、`sql` 3、`wav` 12、`aiff` 3 |
| p18 / 120 | `py` 21、`cpp` 6、`rs` 3、`html` 14、`eml` 16、`pptx` 60 |
| p19 / 90 | `txt` 18、`log` 2、`jsonl` 5、`json` 6、`yaml` 2、`xml` 5、`sql` 2、`course-package-zip` 35、`lms-ustar` 15 |
| p20 / 100 | `py` 16、`js` 2、`ts` 2、`xlsx` 15、`pptx` 15、`foia-zip` 35、`source-drop-ustar` 15 |

各rowのsplit合計がrare total、rare totalがpersona full totalの1%にexact一致しなければ拒否する。

## 7. unsupported variantとcanonical fallback

次は現all-71 registryにないため、現在のcore denominatorへ入れない。

```text
.sh .tf .parquet .tex .bib
.m4a .mp3 .mp4 .mov
.msg .mbox
.xlsm .xlsb およびその他macro-enabled Office
.dwg .dxf
.heic .svg .webp
```

CLIがgeneric text sniffまたはMIME recognitionできることと、benchmark renderer/independent validatorが
存在することは別である。たとえば`.sh`や`.webp`をCLIが扱える場合でも、all-71 registryにない形式を
canonical core variantと呼ばない。

未拡張時は次のfallbackをexact適用する。

| persona / family / full total | registry拡張後候補 | current canonical fallback |
| --- | --- | --- |
| p09 media / 1,350 | `.m4a` 675、`.mp3` 270、`.wav` 270、`.mp4` 135 | `.wav` 945、`.aiff` 405 |
| p19 media / 450 | `.mp4` 225、`.m4a` 90、`.mp3` 90、`.wav` 45 | `.wav` 248、`.aiff` 90、`.mid` 112 |
| p20 media / 400 | `.m4a` 200、`.mp3` 100、`.wav` 60、`.mov` 40 | `.wav` 300、`.aiff` 100 |
| p11 mail/web / 2,800 | `.html` 420、`.eml` 1,680、`.msg` 700 | `.html` 560、`.eml` 2,240 |
| p14 spreadsheet / 4,160 | `.xlsx` 3,328、`.xlsm` 624、`.xlsb` 208 | `.xlsx` 4,160 |
| p17 domain / 1,440 | IFCZIP 360、CDE ZIP 360、`.dwg` 432、`.dxf` 288 | `ifczip` 576、`cde-zip` 864 |

unsupported形式を試す場合はcore分母外の別`format-coverage` profileへ追加する。専用renderer、magic/MIME
validator、independent receiptがない段階ではplanned/pending fixtureであり、実装済みraw-only fixtureと
再分類しない。registry拡張後にcoreへ入れる場合は、core matrixのfamily totalを変えず、registry、allocation
manifest、source plan、solver input、全下流closureをadditive re-freezeする。

## 8. 566-row manifest contract候補

正本候補は`kio.persona.core-extension-allocation-manifest/v1`とし、exactly 566 rowsをpersona、family、
variant ordinal順に持つ。1 rowのkey setは次のexact 23 keysであり、optional keyはない。

```text
schema_version
row_schema = kio.persona.core-extension-allocation-row/v1
row_id
profile_id = persona-core-v1
persona_id
family_id
family_ordinal
variant_id
variant_ordinal
variant_weight
filename_extension
compound_suffix_parts
gate_role
expected_offline_disposition
family_full_count
full_count
family_pilot_count
pilot_count
family_tiny_count
tiny_count
renderer_binding_id
validator_binding_id
format_registry_sha256
```

validatorは`set(row.keys())`がこの23-key setへexact一致することをsemantic field validationより先に確認し、
unknown keyとmissing keyをともに拒否する。`schema_version`はboolではないexact integer `1`、
`row_schema`はexact string `kio.persona.core-extension-allocation-row/v1`である。

`family_ordinal`はboolではない0-based exact integerで、§2の`family_order`に対応する`0..14`である。
`variant_ordinal`もboolではない0-based exact integerだが、global ordinalではない。各
`(persona_id, family_id)`の宣言済みvariant順に対するfamily-local `0..n-1`であり、次のfamilyでは0へ戻る。
`schema_version`、`family_ordinal`、`variant_ordinal`、`variant_weight`、`family_full_count`、`full_count`、
`family_pilot_count`、`pilot_count`、`family_tiny_count`、`tiny_count`はすべて`type(value) is int`相当を要求し、
言語実装上integerのsubclassとなる`true/false`を受理しない。

`row_id`は
`persona-core-v1-extension-{persona_id}-{family_id}-{variant_id}`とする。row JSONはkey sort、compact UTF-8、
NFC、exactly one terminal LFでframingする。566 rowsをdescriptorへ埋め込まず、外部LF-JSONL bodyとして
束縛する。このproposalの3 inputと§4から再生成したbody candidateのpinは次である。

| descriptor field | exact candidate value |
| --- | --- |
| `artifact_schema` | `kio.persona.core-extension-allocation-manifest/v1` |
| `artifact_id` | `persona-core-v1-extension-allocation-manifest-v1` |
| `body_id` | `persona-core-v1-extension-allocation-rows-v1` |
| `row_schema` | `kio.persona.core-extension-allocation-row/v1` |
| `body_encoding` | `canonical-json-per-row-utf8-nfc-lf` |
| `body_embedded` | `false` |
| `body_final_lf` | `true` |
| `body_canonical_bytes` | 426,889 |
| `body_sha256` | `f31f696e1692758e4fc52133dba733af77b74d16711034ee05d75b16d64f7d45` |
| `row_count` | 566 |
| `full_nonzero_row_count` | 539 |
| `row_order` | persona ordinal、family ordinal、variant ordinal |
| `first_row_id` | `persona-core-v1-extension-p01-md-md` |
| `first_row_lf_bytes` / `first_row_sha256` | 745 / `351991d32d2b21171ec21a77fd3ba2a52ef89638e845cf2ce590addeba885fb5` |
| `last_row_id` | `persona-core-v1-extension-p20-domain_binary-source-drop-ustar` |
| `last_row_lf_bytes` / `last_row_sha256` | 778 / `e663127e173334127c6333909370038fa83181d903a1866a9d1380711fd0b09b` |
| `maximum_lf_inclusive_row_bytes` | 786 |

このbody pinはdesign proposal上のexpected candidateであり、golden発行ではない。後述の
`Manifest Golden-Freeze Decision/Gate`がproducer/independent-validatorの実装後に同じbytes/SHAを再生成して
初めてgoldenとなる。不一致時は値をその場で更新せず、design変更と再reviewへ戻る。

descriptorは3 input binding、この外部body binding、persona totals、family totals、role totals、extension set、
authority、orders、canonical limitsを持つ。source ID、logical document ID、scope key、history cohort/event、query、
solution coordinate、path、raw hash、section ID、observed chunks、receipt結果を含めない。

候補boundは次とする。

- descriptor canonical body: 512 KiB以下
- external LF-JSONL body: exact 426,889 bytes、512 KiB以下、descriptorへ非埋込
- one canonical row: LFを含め2,048 UTF-8 bytes以下
- observed maximum LF-inclusive row: exact 786 bytes
- canonical nesting depth: 32以下
- one string: 4,096 UTF-8 bytes以下
- exact rows: 566、full non-zero rows: 539
- exact personas: 20、families: 15、variants: 71、physical extensions: 39
- file count: persona 7,000--16,000、suite 203,000
- integer fields: boolを拒否し、0以上のbounded integer
- row order: persona ordinal、family ordinal、variant ordinal
- duplicate `(persona_id, family_id, variant_id)`、foreign variant、unknown extensionを拒否

row bodyはproducerが生成するが、独立validatorはproducer moduleをimportせず、3入力providerと公開された
Hamilton仕様から全566 rowsを再構成する。外部body providerはexactly two readsとする。read 1をowned bytesへ
copyしてsize/SHA/framing/rowを検証し、accept直前にread 2を別owned bytesとして再取得する。read 2も同じ
size/SHAを認証し、`read_1 == read_2`をbyte-for-byte要求したうえで、accept対象はread 2と同じbufferとする。
parserや後続consumerがpathを再openしてはならない。provider call count、artifact/body ID、bytes/SHAを固定し、
検証中のmutation、symlink/path substitution、mutable alias、subclass、duplicate key、Unicode non-NFC、oversize、
unknown fieldをfail closedとする。

## 9. validation invariants

manifest golden freeze前に最低限、次をすべて機械確認する。

1. 3 inputのschema、bytes、SHAが§2へexact一致する。
2. persona IDはp01--p20、family orderは15件、matrix row totalとsuite totalは§3へexact一致する。
3. 各rowがexact 23 keysを持ち、schema version、family-local ordinal、exact integer型制約へ一致する。
4. full/pilot/tinyの各persona/familyでvariant sumがfamily countへexact一致する。
5. fullで566 declared、539 non-zero、71 variants全件non-zero、39 suffix exact集合となる。
6. full role totalsが68,761 / 62,978 / 71,261、suite totalが203,000となる。
7. full、pilot、tinyのrare totalが各persona totalのexact 1%となる。
8. §6の全20 rare splitとexact一致する。
9. absent familyは0、positive familyにempty profileがない。
10. pilot rowは対応full row以下、tinyはcoverage completenessを主張しない。
11. variant、suffix、compound suffix、MIME、disposition、renderer/validator bindingが同一registry rowへ一致する。
12. raw-only countからsearchable-positive、actual zero chunks、Recall、latencyを推論しない。
13. unsupported variantがcore manifestに0件で、fallback totalが元family totalを保存する。
14. external bodyが426,889 bytes / `f31f696e1692758e4fc52133dba733af77b74d16711034ee05d75b16d64f7d45`、
    566 / 539 rows、first/last ID、maximum row 786へexact一致する。
15. bodyはdescriptor外部にあり、two-read providerの両owned bytesがbyte-for-byte一致し、provider call countが2となる。
16. producer再実行、独立validator、`PYTHONHASHSEED=0/1`でcanonical bytes/SHAが一致する。
17. authority fieldが非空かつすべてexact falseである。

## 10. dependency DAGと権限境界

```text
core family matrix + variant-weight envelope + all-71 registry
  -> Design Adoption Decision
  -> contract tests / implementation candidate
  -> 566-row external body + descriptor candidate
  -> Manifest Golden-Freeze Decision/Gate
  -> content-only namespace
  -> pre-solve corpus/evaluation closures
  -> namespace-only, query-independent joint solution/proof
  -> final source plan (frozen extension manifestをdirect binding)
  -> solution-compiled history plan / planned ledger
  -> post-solution evaluation resolution
  -> full production blocker ledger update + scoped blocker projections
  -> corpus closure equality/reuse + authoritative history/evaluation/suite closure successors
  -> active_g0_unresolved_count == 0
  -> G0 suite descriptor / separate G0 issuance Decision
  -> writer -> ordered history -> 3 fresh replays -> evaluation-execution-ready closure -> evaluation
```

矢印は発行順として一方向である。pre-solve closuresはsolverより先に閉じるが、solverのsemantic inputは
content-only namespaceだけである。query/oracle/evaluation closure、review receipt、blocker ledgerをjoint
problem/solution/proofへimportしない。extension manifestはsolution前のcontent artifactとしてnamespaceへ入る。
一方、final source planはsolution後にのみ発行し、solutionとfrozen extension manifestをdirect bindingする。

allocation manifestはquery、history、solution、filesystem receiptを入力にしない。downstream artifactはmanifestを
bindできるが、input 1--3をmanifestやsolutionへbackedgeさせない。既存`benchmark_stress_mix_v2`のsource rows、
solution、receiptを`persona-core-v1`へ読み替えない。

このproposalと将来のmanifest candidateでは、少なくとも次をすべてfalseにする。

```text
authorizes_g0_freeze
authorizes_source_recipes
authorizes_source_instances
authorizes_source_plan
authorizes_solver_execution
authorizes_renderer_execution
authorizes_physical_write
authorizes_filesystem_mutation
authorizes_kio_execution
authorizes_history_mutation
authorizes_replay_execution
authorizes_query_plan
authorizes_evaluation
actual_payload_bytes_attested
actual_chunks_attested
formal_capacity_gate_satisfied
```

## 11. adoption sequence

1. **Design Adoption Decision**で`persona-core-v1`、3 input pin、Hamilton、fallback、external-body/descriptor
   contractを設計として採用する。これは実装済みmanifest、golden、namespace、G0を意味しない。
2. core family matrixをproposalから独立したbounded artifactへ実装し、2,410-byte projectionを再生成する。
3. envelopeからvariant-weight-only public projectionを作る。private helperやstress countをruntime依存にしない。
4. 566-row LF-JSONL producer、descriptor、builder-independent two-read validator、tamper/TOCTOU testsを
   implementation candidateとして実装する。
5. `fast -> pre-freeze full -> cold/hash-seed 0/1`を通し、expected 426,889 bytes /
   `f31f696e1692758e4fc52133dba733af77b74d16711034ee05d75b16d64f7d45`を再現する。
6. **Manifest Golden-Freeze Decision/Gate**をDesign Adoption Decisionとは別に発行し、実装後のdescriptor/body
   bytes/SHA、566/539、first/last ID、maximum row bytes、validator pinをgoldenとして固定する。不一致ならstep 1へ戻る。
7. `fast -> post-freeze full -> independent review`を通した後、frozen manifestをcontent-only namespaceへ収録する。
8. pre-solve corpus/evaluation closuresを閉じる。solverへはcontent-only namespace以外をimportしない。
9. namespace-only、query-independentなcore joint problem/solution/proofを新規生成する。stress solutionから推論しない。
10. solutionとfrozen manifestをdirect bindingしたfinal source planを発行し、solution-compiled history plan / planned
    ledgerを構築する。
11. evaluation closureとsolution/planned historyを下流joinし、post-solution evaluation resolutionを発行する。
12. full production blocker ledgerとscoped projectionsを更新し、corpus closure equality/reuse、authoritative
    history/evaluation/suite closure successors、`active_g0_unresolved_count == 0`を閉じる。
13. G0 suite descriptorへ全pinを束縛し、Design Adoption DecisionともManifest Golden-Freeze Decision/Gateとも
    別のG0 issuance DecisionでG0を判断する。
14. G0後にtiny、pilot、full replay-01をwriterで生成し、W0--W5 historyを実行する。
15. replay-02/03はcopy/clone/hardlink/reflinkを使わずfresh storageへ再生成する。
16. 3 replay sealとevaluation-execution-ready closureの後にのみ、actual file/format/chunk、history、Recall、
    latency、costを評価する。

本proposalの作成、hash、reviewだけではstep 1以降を実行してよいことにならない。

## 12. blockers

### P0

- Design Adoption Decision、core family matrix、variant-weight projection、566-row external body/descriptorの正式
  artifactとtwo-read independent validator、Manifest Golden-Freeze Decision/Gateが未実装・未凍結。
- all-71 registryはformat feasibilityのみで、formal source recipe、source instance、G0 authorityがない。
- core専用source plan、joint problem、solution、independent proofがなく、120,000 chunks/personの同時充足を証明していない。
- `.msg/.xlsm/.xlsb/.dwg/.dxf`等をfallbackなしでcore denominatorへ入れることはできない。
- 203,000 sourceの物理render/write、W0 attestation、actual role/chunk observationがない。

### P1

- suffix collisionをvariant ID、magic、MIME、container structureで束縛するmanifest/validatorが未実装。
- full/pilot/tinyのnested Hamilton、rare exact 1%、566/539/role totalsを独立再生成するgateが未実装。
- raw-only actual chunks zero、incidental actual indexed chunks、contract exact chunksをpersona別に実測していない。
- 3 fresh replay間の同一logical allocationと非共有physical materializationをattestしていない。

### P2

- 実務上重要な未登録形式のrenderer/validator/registry拡張と別format-coverage replay。
- authored hypothesisとdogfood観測値の差をversioned comparisonとして還元する手順。
- extension比、byte比、chunk比、logical-document比を混同しない表示・reporting gate。

## 13. 非主張

このproposalは、実在利用者の形式比、全formatのsearchability、100,000超chunksの性能、history correctness、
M3-1/M3-2/M3-3、Spotlight/ripgrep-all比較、TTFV、AI強化時間、コスト、3 replay再現性を証明しない。
証明するのは、採用候補となる3入力、整数配賦規則、期待されるexact totals、fallback、将来manifestの
validation boundaryを曖昧なく記述したことだけである。
