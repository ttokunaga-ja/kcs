# Synchronization Research Notes

> Status: reviewed
> Canonical refs: none yet. v2 / Phase 5+ concept.

---

# 位置づけ

同期・共有・Web 修正提案は MVP では扱わない。MVP は単一端末 local-first の object store / search / restore / purge を優先する。

# UX 原則

ユーザーに Git 用語を見せない。

```text
branch     → 修正提案
merge      → 反映
commit     → 変更履歴 / 版
conflict   → 最新版と重なる編集
main       → 共有版
revert     → 以前の版に戻す
```

# 同期対象

```text
1. 原本ファイル
2. Normalized Markdown
3. 共有データ: shared note / tag / view / dataset
4. 個人データ: personal note / tag / history / view
```

それぞれ同期ルールを分ける。

# 原本ファイル

原本は自動 merge しない。内容が変わったら新しい版として保存する。

```text
same hash:
  新版を作らない。

different hash:
  新版として追加。

restore:
  過去版を current に直接戻すのではなく、過去版内容の新しい版を作る。
```

# Normalized Markdown

原本から生成された read-only artifact。同期先で手編集しない。再抽出は別 artifact として保存し、active を切り替える。

# 共有データ

共有版を優先し、自動反映できない変更は「修正提案」として残す。未反映提案は RAG の正本に混ぜない。

# 個人データ

個人メモ、閲覧履歴、個人タグは共有データと分離する。共有に昇格する場合は明示操作にする。

# 競合

競合を操作失敗にせず、保存可能な proposal object にする。自動解決できるものは共有版へ反映し、曖昧なものだけ人間の判断に回す。

# MVP へ混ぜない理由

同期は権限、競合、purge、個人/共有境界を一気に複雑化する。まず single-device の truth model を固め、その上に sync layer を重ねる。
