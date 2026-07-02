# Document Consolidation Plan

> Status: integrated
> Canonical refs: [../README.md](../README.md), [../09-mvp-scope.md](../09-mvp-scope.md)

---

# 結果

Research の長い LLM メモを、実装向け spec へ統合する計画。現在は `docs/01-` から `docs/10-` に正本が整理済み。

# 統合後の正本構造

```text
README.md                  Reading Path
01-positioning.md          位置づけ、ターゲット、MVP
02-philosophy.md           理念
03-data-model.md           CAS、object、scope、identity
04-pipeline.md             ingest、markdownize、chunk、index、batch
05-runtime.md              search、commit、GC、purge、restore
06-cli-spec.md             CLI / exit code / API
07-adapter-spec.md         Adapter trait、tool profile、incremental
08-evidence-pointer-spec.md Evidence Pointer
09-mvp-scope.md            Phase、Done 条件、設計宿題
10-operations.md           横断規約、運用、命名
```

`11-requirements.md` は deprecated な旧統合ドラフト。

# 統合方針

```text
- 正本は docs/ 直下に置く。
- Research は正本ではなく、経緯の要点だけ残す。
- 迷った記述は design-homework.md に寄せる。
- Phase 4+ の構想は MVP spec に混ぜない。
- 凍結後の本文修正は、実装不能・互換性破壊・データ破壊リスクに限る。
```

# 今後の規律

Research に新しい LLM 出力を長文で貼らない。追加する場合は要点へ圧縮し、正本へ昇格するか、将来構想として明示する。
