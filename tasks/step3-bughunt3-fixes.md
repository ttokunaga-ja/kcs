# 探索型 4 エンジン監査 (第 3 ラウンド) の裁定 (2026-07-04、main = 4e77b87)

防御的セキュリティ監査。新規 **2 critical + 3 major + 2 minor**。過去の M/N と非重複。
発注側で O1 (cursor スコープ迂回) と O2 (query embedding 送信) を実機/コードで再確認済み。
Spark の焦点監査 (算術・JCS 決定性) は実害級ゼロ (残りは 32-bit / u64::MAX / 破損 DB の理論値)。
今回の鉱脈は「検索境界の完全性・入力堅牢性・状態の縮退」。

## 必須修正 O1-O7

- **O1 [critical] --cursor が --scope/--descendants 制限を無条件に迂回 + cursor 無署名で偽造可能**
  (Sonnet 実機 + 発注側再確認): `run_search` の cursor 分岐 (main.rs:828-854) が
  `resolve_cursor_exec_scopes` の結果だけで exec_scopes を決め、呼び出し時の scope 制約を一切見ない。
  **実証: safe scope から `--scope . --cursor <secret の cursor>` で secret 本文 (TOP-SECRET-KEY-XYZ)
  が漏出。** さらに cursor は base64url(JCS) のみで HMAC/署名なし、query_hash は公開情報のみのため
  正規アクセスなしに偽造可能。Agent API の sandbox 境界 (docs 05 §1.7/06 §9) を破る。
  修正: (a) cursor 併用時も enumerate_scope_targets で呼び出し許可 scope 集合を計算し、cursor の
  scope をそれと**交差**させる (許可外は excluded_scopes reason="scope_restriction_mismatch" で除外)、
  (b) cursor をデバイスローカル鍵で HMAC 署名し、復号時に検証 (改ざん/偽造を検出。鍵は
  ~/.local/share/kcs 配下、無ければ生成)。方式は decisions に記録。回帰テスト: 別 scope の cursor を
  --scope . に渡すと漏れない / 改ざん cursor が拒否される
- **O2 [critical] search が --text / opt-in 未成立でも query を Gemini embedding に送信** (GPT-5.5 +
  発注側コード確認): `compute_query_embedding` (main.rs:860) が `resolve_search_mode` (866) より前で
  **無条件**に呼ばれる。実 GEMINI_API_KEY があれば `--text` 指定・embedding opt-in 未承認でも検索
  クエリ本文が外部送信される (07 §3 の opt-in 違反、Tier B/index とは別経路の秘匿漏洩)。
  修正: mode/opt-in を先に解決し、resolved_mode が vector/hybrid かつ embedding opt-in 済みの場合のみ
  compute_query_embedding を呼ぶ。回帰テスト: --text で embedding adapter が呼ばれない (mock seam の
  呼び出し痕跡で検証)
- **O3 [major] batch resume/retry が store lock を取らず二重送信/ledger lost update** (GPT-5.5):
  M1 で index/repair/reindex に配線した lock の**同型兄弟**。run_batch (main.rs:3527) が lock_store を
  取らず、TaskStore::replace_all の固定 tmp 名 (task.rs:137) で並行実行が競合。修正: run_batch 冒頭で
  repo.lock_store() を保持、replace_all の tmp を unique + create_new に
- **O4 [major] 細工 PDF (マルチバイト文字が /Type・/Page トークン近傍) で kcs index が panic**
  (Opus 実機): prepare.rs:284/291 と deterministic.rs:383/390 が `&text[index..index+N]` で
  UTF-8 char 境界を無視した str スライス → `char boundary` panic (exit 101) + **本文を stderr に
  ダンプ** (情報露出)。BT 演算子を含む通常 PDF で露出。修正: 4 箇所を `text.get(index..(index+N).
  min(len))` の境界安全スライスに。回帰テスト: マルチバイト境界 PDF で panic せずクリーン処理
- **O5 [major] 0 chunk の scope (空フォルダ / secrets のみ / text 層なし PDF) で index が
  sqlite エラー exit 2、半初期化で固着** (Opus 実機): append_stored_chunks が chunks 空で早期 return
  し .kcs/index/ を作らないが (main.rs:2271)、rebuild_sqlite_index が存在しない sqlite.db を開いて
  失敗。auto-snapshot は成功済みのため「commit あり index なし」で再 index も毎回 exit 2。
  修正: rebuild_sqlite_index 先頭で index_dir を無条件 create_dir_all。回帰テスト: 空フォルダ index が
  exit 0
- **O6 [minor] open/view の短すぎる sha256: で panic** (GPT-5.5): `sha256:a` 等が長さ検証なしで
  cas_object_path の digest[0..2] slice で範囲外 panic。修正: short hash 入口で hex 長さ >= 4 +
  lowercase hex 検証、不正は KCS-E-CONFIG-USAGE-001 exit 2
- **O7 [minor] scope_id 衝突 (.kcs 丸ごとコピー) 時、cursor 解決が Evidence 経路と違い曖昧検出しない**
  (Sonnet): resolve_cursor_exec_scopes が lookup_scope_id().next() を無条件採用。Evidence の
  KCS-E-EVIDENCE-SCOPE-AMBIGUOUS-001 と同水準の同点検出に統一

## 受け入れ条件

cargo test --workspace (回帰なし + 各 O の回帰テスト) / clippy -D warnings / fmt。
実機: (a) 別 scope の cursor を --scope . に渡して漏れない + 改ざん cursor 拒否、(b) --text で
embedding adapter 未呼出、(c) 並行 batch resume で二重送信なし + ledger 有効、(d) マルチバイト境界
PDF が panic せず、(e) 空フォルダ index が exit 0、(f) 短 sha256: が exit 2。
