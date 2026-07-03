# KCS 検索評価ハーネス (synthetic)

`docs/09-mvp-scope.md` §4.3 の **Recall 評価規約 (ゴールデンクエリ)** を実行するための
合成コーパス + 履歴シナリオ + ゴールデンクエリ + 評価ランナー。設計宿題 #5
(`docs/09-mvp-scope.md` §5.5、**Step 3 着手前ゲート**) の成果物。

- 依存: **Python3 標準ライブラリのみ** (追加インストール不要)。
- 決定論: すべて固定 seed (`corpus_spec.SEED`) + hashlib 由来の seed。2 回実行で byte 同一。
- `crates/` の `kcs` バイナリ (Step 1-2 実装済み) を使う。`cargo build --release` 済み前提。

## ファイル構成

| ファイル | 役割 |
| --- | --- |
| `corpus_spec.py` | **正本**。scope / anchor 文書 / 履歴シナリオ (編集・リネーム・削除) の単一定義。他スクリプトが共有し drift を防ぐ |
| `generate_corpus.py` | 合成コーパス生成 (200-500 ファイル / 複数 scope)。`corpus-manifest.json` を出力 |
| `replay_history.py` | 各 scope で `init → index → snapshot → 編集 → snapshot → リネーム → snapshot → 削除 → snapshot` を決定論再現。`history-manifest.json` を出力 |
| `golden-queries.jsonl` | ゴールデンクエリ (M3-1 / M3-2 / M3-3 各 16+ 件)。**リポジトリ保持の正本** |
| `history-manifest.json` | replay がリネーム/編集/削除したファイルの記録 (`replay_history.py` が生成) |
| `run_eval.py` | 評価ランナー。`kcs search --json` で Recall@10 を集計。expected のニーモニック → 実 `section_id` の解決層 (docs/04 §4.1 slug) を持つ。`--dry-run` は expected 実在 + 解決チェック。`--scenario` でシナリオ絞り込み |
| `test_run_eval.py` | `run_eval` の単体テスト (slugify / 解決層 / recall_at_k / exit 分類)。`python3 -m unittest eval.test_run_eval` |

## 使い方

コーパス本体は再生成可能なため **リポジトリにコミットしない** (一時ディレクトリへ生成する)。

```bash
# 0. バイナリ (未ビルドなら)
cargo build --release

# 1. 合成コーパス生成 (決定論的)
python3 eval/generate_corpus.py --out /tmp/kcs-eval-corpus

# 2. 履歴シナリオ再現 (kcs init/index/snapshot を実行し history-manifest.json を更新)
python3 eval/replay_history.py --corpus /tmp/kcs-eval-corpus --bin target/release/kcs

# 3a. dry-run: golden-queries の expected {scope,file,section} が
#     corpus-manifest.json / history-manifest.json に実在し、かつ
#     (raw_hash, section_id) へ解決できる (slugify が空でない) か検証 (Step 3 前でも通る)
python3 eval/run_eval.py --dry-run --corpus /tmp/kcs-eval-corpus

# 3b. 本評価: Recall@10 をシナリオ別に集計。
#     kcs search 未実装の間は全クエリ NOT-IMPLEMENTED → exit 2 (未実装を green にしない)。
python3 eval/run_eval.py --corpus /tmp/kcs-eval-corpus --bin target/release/kcs

# 3c. シナリオ絞り込み (複数指定可)。Step 3 の Done gate は M3-1 のみ (下記)。
python3 eval/run_eval.py --scenario M3-1 --corpus /tmp/kcs-eval-corpus --bin target/release/kcs
```

### exit コード (docs/09 §4.3, 2026-07-03 J2 裁定)

| 状況 | exit | 扱い |
| --- | --- | --- |
| 全シナリオ (対象) が Recall@10 >= 0.8 | `0` | PASS |
| `KCS-E-*-NOT-IMPLEMENTED*` 系のクエリが 1 件以上 | `2` | 未実装。Recall 判定は無効 (green にしない) |
| Recall 未達 / 実行失敗 (非 0 かつ非 3 exit・不正レスポンス・解決不能) | `1` | FAIL。当該クエリは recall 0 として集計に残す |

exit `3` (部分成功) は stdout の JSON を採点対象にする (実装後の部分成功や実バグを未実装で握り潰さない)。

## シナリオと評価コーパスの対応 (docs/09 §4)

| シナリオ | フラグ | コーパス上の対象 | 判定 |
| --- | --- | --- | --- |
| **M3-1** 現行検索 | (なし) | 編集/リネーム/削除しない安定 anchor。本文の数値・用語の部分記憶で引く | 現行 tree の該当 file がヒット |
| **M3-2** リネーム追跡 | `--all-history` | リネームされた anchor (旧名で記憶) + 編集された anchor (旧値は履歴のみ) | 旧 raw_hash の chunk が両方ヒット |
| **M3-3** 削除再発見 | `--include-deleted` | 削除された anchor の数値を再発見 | 削除済み file の chunk がヒット |

`expected` は `{scope, file, section}` の分離形式 (docs/09 §4.3、`03-data-model.md` §3
「直下のみ」規則)。`section` は **英語ニーモニック** (例 `"recall"`) であり、実 `section_id` ではない。

### expected → (raw_hash, section_id) の解決 (J2 裁定, 2026-07-03)

Recall の突き合わせ単位は `(raw_hash, section_id)` (docs/09 §4.3)。`expected` はニーモニックと
`{scope, file}` の分離形式なので、ハーネスが以下の手順で実値へ解決する:

1. **section (ニーモニック) → heading (実見出しテキスト)**
   `corpus-manifest.json` / `history-manifest.json` の anchor `sections[]` が
   `{slug: ニーモニック, heading: 実見出し}` を持つ (正本は `corpus_spec.ANCHORS`)。
   例: `"recall"` → 見出し `"回収率と精度"`。
2. **heading → section_id** … `docs/04-pipeline.md §4.1` の slug 規則で `slugify(heading)`。
   例: `slugify("回収率と精度")` = `"回収率と精度"` (日本語は保持。英語ニーモニックとは一致しない)。
   これが J2 の核心: `"recall"` を実 `section_id` として突き合わせると必ずミスする。
3. **{scope, file} → raw_hash** … manifest が記録する `raw_sha256` (ファイル bytes の sha256) から
   `raw_hash = "sha256:" + raw_sha256`。M3-2 (編集/リネーム) / M3-3 (削除) は
   `history-manifest.json` が **旧内容** の `raw_sha256` と heading を記録し、そちらを優先する。

突き合わせ時、`evidence_pointer.section_id` (docs/08 §2 では heading_path を "/" 連結した slug) は
最深 (leaf) セグメントを取り、`slugify(heading)` と比較する (見出し「回収率と精度」→ `"回収率と精度"`)。

### Recall 実測の gate タイミング

- **Step 3 の Done gate は M3-1 のみ** (`--scenario M3-1`)。M3-2 / M3-3 の Recall 実測は
  `--all-history` / `--include-deleted` が揃う **Step 4 完了時**に判定する。

## dogfood との関係 (docs/09 §4.3)

評価コーパスは 2 種:

- **synthetic** (本ハーネス): 公開可能な生成文書。CI / Done 判定の**正本**。数値を公開してよい。
- **dogfood**: 開発者自身の実フォルダ (非公開)。数値は公開せず、3 シナリオの**主観成功確認**に使う。
  本ハーネスは dogfood の数値を扱わない。dogfood は同じ `golden-queries` 形式を各自ローカルで用意する。

Done 条件 = **synthetic で各シナリオ Recall@10 >= 0.8** + **dogfood で 3 シナリオの手動成功確認**。

## クエリ凍結規律 (重要)

`docs/09-mvp-scope.md` §4.3 / §4.2 に従う:

- ゴールデンクエリの追加は **Step 3 着手前まで**。
- **Step 3 着手後は `golden-queries.jsonl` の追加・差し替え・削除を禁止** (シナリオ凍結規律に準ずる)。
  悪化を隠すためのクエリ削除は禁止。物理的に実装不可能と判明した場合のみ docs 側で撤回 + 代替採用。
- コーパス定義 (`corpus_spec.py`) と履歴シナリオも同様に凍結対象。変更は Recall 数値の連続性を壊すため、
  Step 3 着手後は原則行わない。

## 決定論の検証

```bash
python3 eval/generate_corpus.py --out /tmp/c1
python3 eval/generate_corpus.py --out /tmp/c2
diff -r /tmp/c1 /tmp/c2   # 差分なし (byte 同一) であること
```

`history-manifest.json` の renamed/edited/deleted と scope 別 commit 件数も、フレッシュな
コーパスに対して 2 回再現すれば同一になる (commit hash / timestamp は非決定なので manifest に含めない)。
