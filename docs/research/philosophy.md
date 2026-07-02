# Philosophy Research Notes

> Status: integrated
> Canonical refs: [../02-philosophy.md](../02-philosophy.md), [../01-positioning.md](../01-positioning.md)

---

# 要点

KCS は Git そのものではなく、Git の良い性質を知識アーカイブ向けに再構成する。

```text
Git から借りる:
- content addressing
- snapshot / restore
- provenance
- append-only に近い履歴
- ignore / gc / tag の考え方

KCS では捨てる:
- branch / merge / rebase をユーザーに見せる体験
- テキスト差分中心の思想
- バイナリ資料を二級扱いする前提
- 履歴改変を日常操作にすること
```

# KCS の主張

1. RAG には検索精度だけでなく「知識の座標」が必要。
2. 原本ファイルは証拠であり、Normalized Markdown は証拠表現である。
3. Evidence Pointer は path ではなく、時点・原本・抽出結果・chunk/span を指す。
4. 競合はユーザーに merge させず、修正提案や別版として保持する。
5. 「忘れない」を原則にしつつ、法務・秘匿・誤取り込みには purge を用意する。

# 競合 VCS からの学び

```text
Jujutsu:
  競合を操作失敗ではなく、後で解ける状態として扱う点を借りる。

Pijul:
  patch を一級概念にする発想は参考になるが、KCS の MVP は patch 管理をしない。

Sapling:
  大規模運用と stacked workflow の UX は参考になるが、KCS は Git 互換を目的にしない。
```

# purge との緊張

KCS は履歴保存を重視するが、削除不能であってはならない。purge は通常削除ではなく、KCS 管理下の object / index / derived artifact から情報を除去する破壊的操作として扱う。

重要なのは、通常操作では「消えない」こと、purge では「消した事実を監査可能にする」こと。

# 正本へ移した内容

```text
理念・Evidence Pointer の根拠     → 02-philosophy.md
プロダクト位置づけ・ターゲット      → 01-positioning.md
purge の runtime semantics        → 05-runtime.md, 08-evidence-pointer-spec.md
MVP の範囲                         → 09-mvp-scope.md
```
