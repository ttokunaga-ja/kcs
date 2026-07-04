# 探索型 4 エンジン監査の裁定 (2026-07-04、main = c8db101)

検証型 (契約チェックリスト) から探索型 (自由なバグ狩り) に切り替えた回。**新規 1 critical + 7 major**。
全件が実機再現または file:line 立証済み。Spark の焦点監査 (exit/error code 一貫性) は不整合ゼロ。

## 必須修正 M1-M8

- **M1 [critical] 並行実行でストア破損 → 全 scope 巻き添え** (Sonnet 実機):
  (a) 05 §6 が明記する `.kcs/.lock` が `kcs index` / `repair` / `reindex` に未配線 (snapshot/tag のみ)。
  run_index/run_repair/run_reindex の先頭で StoreLock::acquire (敗者は KCS-E-STORE-LOCKED-001 exit 3)。
  (b) 全 JSONL append (cas.rs append_jsonl / main.rs append_jsonl_cli / write_approval_record /
  TaskStore::append / CostLedger::append_monthly) が「serde_json::to_writer の複数 write + 改行の
  別 write」でレコードを書くため、O_APPEND でもバイト単位でインターリーブする。**1 レコードを
  String に組んでから単一 write_all** に統一 (これで device-global な cost-ledger.jsonl の
  cross-scope 競合も実質解消)。
  (c) 破損 JSONL の読取エラーが KCS-E-CONFIG-SCHEMA-001 (exit 2) と誤報される —
  TaskStore::all / CostLedger::monthly_total_for_adapter の parse 失敗は
  KCS-E-STORE-CORRUPT-001 + 対象ファイルパスを message に含める形へ。
  回帰テスト: 2 プロセス並行 index → 一方が LOCKED-001 exit 3、ledger/tasks が有効な JSONL のまま
- **M2 [major] kcs view (非 --json) が本文を表示しない** (Sonnet 実機): print_output が status
  最優先で "viewed" しか出さない。text フィールドを表示する分岐を追加
- **M3 [major] raw_hash 短縮解決が複数 chunk で「ambiguous」** (Sonnet 実機): resolve_short_hash が
  chunk 一致数で判定するため、見出し 2 つ以上の普通のファイルで open/view が失敗。08 §2.3 規則 4
  どおり「raw_hash 名前空間の一致はファイル単位で一意なら OK」に (open は raw 経路で直接解決)
- **M4 [major] 破損 sqlite.db が index_corrupt に分類されない** (Opus 実機): SQLite open は遅延評価で
  空/ゴミファイルでも成功し、後続クエリで Fatal → 検索全体が exit 2 (CONFIG-SCHEMA-001 の嘘)。
  健全 scope の結果も全消失 (05 §1.8 の部分失敗契約違反)。open 直後に軽量プローブ
  (SELECT 1 FROM tree_entries LIMIT 1 相当) → 失敗は Excluded("index_corrupt")。
  multi-scope = exit 3 + excluded、単独 = VEC-UNAVAIL 系の既存分岐に乗せる
- **M5 [major] CAS 展開キャッシュが非冪等** (Opus 実機): open/view の 2 回目が read-only キャッシュへの
  fs::copy で EACCES。copy 前に既存キャッシュを再利用 (is_file なら即返す)
- **M6 [major] Evidence resolver が chunk identity を束縛しない** (GPT-5.5): raw_hash/tool_profile_hash/
  gen と chunk row の一致を検証せず、改ざん pointer で「raw は B・本文は A」の不整合 evidence が成立。
  resolver で tree entry と chunk row の identity 一致を要求 (不一致 = invalid pointer / retarget)
- **M7 [major] object URI の CAS dispatch 誤り** (GPT-5.5): image/prepared/normalized がすべて
  open_raw_object (objects/raw) に流れる。object_type ごとに正しい CAS ディレクトリへ分岐
- **M8 [major] user/folder config の schema 未検証** (GPT-5.5): 起動時検証は tools.toml のみで、
  config.toml は負の budget cap 等が素通り (10 §12 / 06 §11 違反)。dispatch 前に config.schema.json で
  検証 (exit 2 KCS-E-CONFIG-SCHEMA-001) + budget reader に非負ガード
- minor: 未テスト error code 2 件 (KCS-E-CONFIG-NOT-IMPLEMENTED-001 / KCS-E-EVIDENCE-SCOPE-
  AMBIGUOUS-001) のテスト追加 (Spark)

## 受け入れ条件

cargo test --workspace (回帰なし + 各 M の回帰テスト) / clippy -D warnings / fmt。
実機: (a) 並行 index で敗者 exit 3 + ストア無傷、(b) view が本文表示、(c) 複数見出しファイルの
raw_hash open 成功、(d) sqlite.db 破損 scope 混在の multi-scope search が exit 3 + 健全結果維持、
(e) CAS 解決の view 連続 2 回成功、(f) 負 cap の config が exit 2
