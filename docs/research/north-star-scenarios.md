# North Star Scenarios

> Status: integrated
> Canonical refs: [../09-mvp-scope.md](../09-mvp-scope.md)

---

# Phase 3 Done 条件

MVP の完成判定は、機能数ではなく以下の 3 シナリオで判断する。

## M3-1: 3ヶ月前に書いた結論の根拠 PDF を 5 秒以内に出す

必要な能力:

```text
- normalized / chunk / evidence pointer
- hybrid search
- source PDF / span への到達
- latency target
```

## M3-2: リネーム済みファイルの過去版を含めて検索

必要な能力:

```text
- raw_hash ベース identity
- path 変更と content identity の分離
- snapshot DAG
- --at / time-travel search
```

## M3-3: 削除したはずの資料から特定の数字を再発見

必要な能力:

```text
- 通常 delete では履歴を消さない
- 過去 snapshot から検索できる
- restore / view で根拠へ戻れる
- purge は通常 delete と区別する
```

# 計測項目

```text
search latency
evidence pointer resolve rate
restore success
deleted / renamed file hit rate
fallback rate
false positive / duplicate rate
```

# 規律

新機能は 3 シナリオのどれに効くかで採否を判断する。効かないものは Phase 4+ へ送る。
