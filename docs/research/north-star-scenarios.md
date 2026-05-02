# North Star Scenarios — Phase 3 完成時の Done 条件

実装着手前に、Phase 3 完成時のドッグフード用シナリオを **3 つ確定** し、判断軸とする。

> **目的**: 実装中の機能追加判断を「3 シナリオのどれに resp するか」で評価する。該当しないなら Phase 4-5 へ送る。北極星があれば「いま書いている機能はそれに必要か?」で機能スコープを切れる。

> **背景**: ドッグフード可能な具体シナリオを Done 条件に置かないと、実装中に「あれもこれも」になり Phase 4-5 を先取りしたくなる。

---

# 1. 採用シナリオ (案)

最終確定は Step 1 着手前。本書の案をそのまま採用するか、似た性質の自分のシナリオに置き換える。

## Scenario M3-1: 「3ヶ月前に書いた結論の根拠 PDF を 5 秒以内に出す」

```
状況:
  3ヶ月前に書いたメモ「○○の結論は X」の根拠となった PDF を再発見したい。
  PDF のファイル名は覚えていない。本文の数値や用語の一部だけ覚えている。

操作:
  $ kcs search "X の根拠 数値Y"
  → 上位結果に Evidence Pointer 付きで PDF 名/該当ページが表示
  $ kcs open <evidence>
  → 原本 PDF が指定ページで開く

検証する機能:
  - hybrid search (text + vector)
  - Evidence Pointer の表示
  - kcs open による原本回帰

完了条件:
  - クエリから結果表示まで p95 < 5 秒 (ローカル indexed 1万 chunk 想定)
  - Evidence Pointer に commit + raw_hash + chunk_hash + heading_path + span が含まれる
  - kcs open は OS の規定アプリで原本を開く (Adapter 不要)
```

## Scenario M3-2: 「リネーム済みファイルの過去版を含めて検索」

```
状況:
  資料をリネームしたが、過去名で書いた他メモから「あの資料」を探したい。
  または、過去のあるバージョンの資料を再発見したい。

操作:
  $ kcs search "認証仕様" --all-history
  → 現在ファイル + 過去 commit の同一 raw_hash 由来 chunk が結果に出る
  → リネーム前のファイル名でもヒットする (path_at_commit を表示)
  $ kcs view <evidence-at-commit-X>
  → 当該 commit 時点の Markdown を読める

検証する機能:
  - --all-history (snapshot DAG 横断)
  - raw_hash ベースの同一性 (リネームで死なない)
  - kcs view による過去版閲覧

完了条件:
  - リネーム前後で同じ raw_hash の chunk が両方ヒットする
  - 結果に「path_at_commit」と「現在の path」を併記
  - 過去版の Markdown は再生成せず、当該 commit の object をそのまま返す
```

## Scenario M3-3: 「削除したはずの資料から特定の数字を再発見」

```
状況:
  半年前に削除した資料の中に書かれていた数字 (例: 売上目標、API リミット) を
  もう一度見たい。ファイルは現在の working tree には存在しない。

操作:
  $ kcs search "API リミット 1000" --include-deleted
  → 削除済みファイルからもヒットする (deleted フラグ付きで表示)
  $ kcs view <evidence>
  → 削除時点の Markdown を読める
  $ kcs restore <evidence> --to ./recovered/
  → 削除されたファイルを指定ディレクトリに復元 (working tree は不破壊)

検証する機能:
  - CAS による削除済みデータの永続性
  - --include-deleted での検索
  - kcs restore (working tree 非破壊、--to 必須)

完了条件:
  - 削除済みファイルの chunk が検索結果に出る
  - kcs restore は --to <dir> を必須にする (working tree への直接書き戻しを禁止)
  - purge されたファイル (commit_type=purged) は除外され、tombstone を返す
```

---

# 2. 各シナリオの計測項目

```
Latency:
  クエリ受信 → 最初の結果表示までの時間 (p50, p95, p99)
  目標: p95 < 5 秒 (M3-1), < 7 秒 (M3-2/M3-3)

Recall:
  ground truth に対する正解出現率 (top-10 / top-20)
  目標: 各シナリオで Recall@10 >= 0.8

Evidence Quality:
  - 返された Evidence Pointer の必須フィールド充足率
  - kcs open で原本に到達できる率
  目標: 100%

Working tree 安全性:
  - kcs restore で原本を上書きしない
  - kcs view が原本を変更しない
  目標: 違反 0 件
```

---

# 3. シナリオが満たさないと判明した場合の対処

```
Latency 未達:
  - chunk 数を絞る、index を最適化、cache 追加
  - 解決しなければ Step 3 を延長
  - 解決の見通しなしなら、シナリオ条件を緩める ADR を起こす
    (例: p95 < 10 秒に緩和)

Recall 未達:
  - hybrid 重み調整、tokenizer 変更、chunk 粒度見直し
  - ground truth セットの妥当性をまず確認
  - チューニング限界なら Phase 5 (rerank Adapter) へ送る ADR を起こす

Evidence 不整合:
  - 設計の根本問題なので即対応 (ADR で撤回)
  - 4 設計宿題の (1)-(3) と整合確認

Working tree 破壊:
  - 即座に修正。CI で常時検出。リリースブロッカー
```

---

# 4. ドッグフード方針

Step 4 完了後、ユーザー (= 開発者本人 + 同じターゲット層の協力者数名) に **2 ヶ月** 使ってもらう。フィードバックをもとに以下を判断:

```
Option A: Phase 4 (auto-classification, watch) に進む
Option B: Phase 5 (Agent API, Knowledge Graph) に進む
Option C: 既存機能の精度・UX 改善に集中する
Option D: pivot (シナリオ前提が間違っていた)
```

A/B/C/D のどれが正解かは、Phase 1-3 を実際に使ってみないと分からない。**先に Phase 4-5 の詳細設計を埋めない**。

---

# 5. シナリオ凍結の規律

Step 1 着手後はシナリオを **追加・差し替えしない**。Phase 1-3 完了までシナリオを動かさない。

例外:

```
- Step 1-4 の途中で、シナリオが物理的に実装不可能と判明した場合のみ、
  ADR で撤回し代替シナリオを採用する
- 「より良いシナリオを思いついた」「もう一つ追加したい」は採用しない
- Phase 1-3 完了後のドッグフード結果でシナリオは更新可能
```
