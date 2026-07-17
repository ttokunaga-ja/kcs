# 補足指摘 — r14 監査が見落とした §8-c 内部矛盾 (Q01 再確認)

対象: `docs/research/folder-history-sqlite-design.md` (r14 時点)
監査日: 2026-07-16
重大度: **major** (fatal ではないが、新規フォルダで vec 次元照合の参照元が決まらず初回 vec 作成が不能になる可能性)

---

## 指摘 Q01 — §8-c の vec 次元照合の参照元が §5.7 のまま (O28 修正が §8-c 本体に未到達)

### 矛盾の所在

- **§8-c 本文 (L651-652):**
  > c. embedding_vec は完全導出物: tick の Embed submit 冒頭で vec 表の**次元と距離 (distance_metric)**
  > を現行 profile (**§5.7 record**) と照合し、…

- **§8 冒頭 起動時検査 (L632-633) — O28 の修正着弾箇所:**
  > 次元 (現行 profile の dimensions — **app_config の embedding_profile record から読む**。§5.7 は
  > 履歴の保管庫で新規フォルダでは空 — §10 step 3 と同一の参照元。…

- **§10 step 3 (L1503-1504) — O28 の修正着弾箇所:**
  > (i) embedding_vec の**次元と距離**を現行 profile と照合し、… (§8-c。**「現行 profile」の参照元は
  > app_config の embedding_profile record** — §5.7 は履歴の保管庫であり、新規フォルダでは
  > profiles が空のため <dim>/<metric> の展開元にならない。…

### 矛盾の内容

O28 (`folder-history-design-audit-prompt.md` L2214: "§8 冒頭の起動時検査 — 次元の参照元 = **app_config の embedding_profile record**") は §8 冒頭 (L632) と §10 step 3 (L1503) には正しく適用されたが、**§8-c の本文 (L652) には届いていない**。§8-c は今も「現行 profile (**§5.7 record**) と照合」と書いている。

§8 冒頭・§10 step 3 自身が「§5.7 は新規フォルダでは空 → 参照元にならない」と明記しているため、§8-c の「§5.7 record と照合」は以下の破綻を招く:

### 再現シナリオ (major)

- 初期状態: 新規フォルダを register (§21.1)。この時点で §5.7 `profiles` は空 (§8 冒頭・§10 step 3 の自己記述通り)。app_config には `embedding_profile` record が 1 行存在 (§9.1)。
- 操作列: 最初の tick が step 3 (Embed submit) に到達。§8-c に従い「vec の次元・距離を §5.7 record と照合」しようとする。
- 壊れる状態: §5.7 が空のため照合の参照値が得られない。実装が「§5.7 が空なら skip」とすると初回 vec 作成 (§21.1 手順2 で遅延された vec の初回作成) が永久に行われず、embeddings が vec なしのまま放置される。実装が「§5.7 空なら app_config を見る」と補えば §8-c の記述と食い違う。いずれにせよ §8-c をそのまま実装不能 / または §10 step 3 の app_config 参照と二重基準になる。

### 修正案 (最小)

L652 の「現行 profile (**§5.7 record**)」を「現行 profile (**app_config の embedding_profile record** — §5.7 は履歴の保管庫で新規フォルダでは空)」に修正し、§8 冒頭 (L632) ・§10 step 3 (L1503-1504) と参照元を統一する。

### 注記

- r14 監査 (`folder-history-design-audit-r14-sonnet.md`) は N40 で「現行 profile 参照元 = app_config + profiles 空許容」を fixed としたが、引用行は **L1443-1445 (unreadable metadata の fence 論理)** であり §8-c (L652) / §10 step 3 (L1503) ではない。§8-c 本体の §5.7 言及は検証されていない → 本指摘は r14 の網羅性漏れ。
- 本指摘は §18/§19 で決着済みの設計選択 (SQLite 正本 / LWW / 表分離) を蒸し返すものではない。参照元の表記統一のみを求める。
