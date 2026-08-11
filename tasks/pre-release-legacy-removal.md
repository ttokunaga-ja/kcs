# 公開前に落とす後方互換分岐 — 一覧

**方針の正本は [docs/10-operations.md §12.5](../docs/10-operations.md)。**
未リリースなので外部に既存 store は無い。「本規則の導入以前に作られたデータ」を
特別扱いする分岐は、仕様からも実装からも落とす。

**この一覧は 2026-08-11 に `docs/*.md` を走査して作った。実装側 (`crates/`) は未走査。**
各項目を落とすときに、対応する実装とテストを同時に探すこと。

# 1. 落とす — 仕様本文が「導入以前」と明記しているもの

| # | 場所 | 内容 |
|---|---|---|
| 1 | [03 §2 format_version](../docs/03-data-model.md) | 「読めない・欠落した store は旧版とみなし read-only + migration 誘導」。**同じ文の前方互換 (新しい版の store を read-only 縮退) は残す** — 混在しているので切り分けが要る |
| 2 | [04 §? 旧 DB snapshot](../docs/04-pipeline.md) | 「旧 DB からの snapshot は第 2 の source として残す — object 導入前に書かれた store を運ぶのはこれだけ」。**用途がそれだけなら丸ごと落ちる** |
| 3 | [08 §2 path_at_commit](../docs/08-evidence-pointer-spec.md) | 「03 §3 の forward 規則以前に作られた検証済み legacy tree 由来の entry に限り、区切りを含む旧 path をそのまま保持する」 |
| 4 | [08 §3 lifecycle epoch](../docs/08-evidence-pointer-spec.md) | 「legacy の epoch 欠落」の扱い |
| 5 | [07 §3 承認行](../docs/07-adapter-spec.md) | 「`approved_at` / `approval_method` を欠く legacy 承認行」 |
| 6 | [06 §2 ref 名](../docs/06-cli-spec.md) | 「legacy raw-name ref」と legacy read 規則 |
| 7 | [10 §7.5.1 fsck](../docs/10-operations.md) | legacy 警告の種別。上記が消えれば警告する対象も消える |
| 8 | [10 §? tree hashing](../docs/10-operations.md) | 「該当フィールド欠落は legacy として読取可 (欠落 = 旧 semantics)」 |
| 9 | [05 §1.8 refresh](../docs/05-runtime.md) | 修復経路の理由のうち「write-through 導入前に索引された scope」の一句。**修復経路自体は残す** — replica の実体喪失に要る |

# 2. 落とさない — 後方互換ではないもの

洗い出しの過程で誤分類しかけたもの。**同じ判断を繰り返さないために残す。**

| 場所 | 見え方 | 実際 |
|---|---|---|
| [03 §2](../docs/03-data-model.md) Windows で物理化できない Unix 名 | legacy 対応に見える | **OS 差の吸収。**旧データの話ではない |
| [03 §6 digest-only 物理名](../docs/03-data-model.md) | 「旧物理名を読む fallback」 | 仕様自身が **portability correction** と書いている |
| [03 §2 NFC / case folding](../docs/03-data-model.md) | 版間の話に見える | **Unicode 正規化。**世代と無関係 |
| [03 §3 path 検証](../docs/03-data-model.md) | 拒否規則 | 新規に書く規則であって過去の受理ではない |
| 前方互換の read-only 縮退 | 「互換のため」 | **未来の版が書いた store を今の binary が読む話。**公開前後を問わず必要 |

# 3. 判断が要るもの

- [05 §1.5 cursor `v=1`](../docs/05-runtime.md) — 「binding を持たない legacy `v=1` は `KIO-E-SEARCH-CURSOR-001` で拒否する (cursor は durable artifact ではない)」。
  **既に拒否しているので分岐は 1 本だけ**であり、cursor は永続物でないので版が混ざる窓は短い。
  落とすと未知バージョンの cursor が別の経路でエラーになるだけで、**利用者から見た差は無いはず**。
  ただし cursor の版判定を完全に消すと将来 v=2 を足すときに判定点が無くなる。**残すのが妥当か要検討。**

# 4. 一緒に片付けたいもの (後方互換ではないが、公開前でしか直せない)

| 場所 | 内容 |
|---|---|
| [07 §5.3 ローカル embedding](../docs/07-adapter-spec.md) | `dimensions` が「V3 決着まで暫定」なのに `tool_profile_hash` の確定値が既に記載されている。**`tool_profile_hash` は first-instance-wins で永続化される** ([03 §5.1](../docs/03-data-model.md)) ので、暫定のまま実データを作ると V3 決定後に全 embedding の再生成が要る。**V3 決定を実装着手のブロッカーにする** |
| [03 §? per-`.kio` dedup](../docs/03-data-model.md) | 重複生成の容認理由が「将来 LLM コスト低下前提」と書かれている。**これは将来予測であって設計理由ではない。**実際の理由はフォルダ単位の権限境界 ([01 §7](../docs/01-positioning.md)) から導かれる制約のはずで、書き換えるべき (要確認) |
