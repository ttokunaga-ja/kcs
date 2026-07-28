# 2026年7月 脅威モデル・フォローアップ

対象: Operator Hub、Grid Console、Vendor Edge の運用データフロー



## 前回レビューからの確認事項

- Operator Hub から Evidence Vault へ送る操作記録は、利用者 ID と操作種別を分けて扱う。監査用の抜粋では不要な属性を含めない。
- Vendor Edge は委託先ネットワークから入る経路があるため、信頼境界の名称をサービス台帳と同じ表記にそろえる。
- Grid Console の緊急操作は通常の管理操作と経路が異なる。チケット参照を残すが、画面の自由記述を分析用のイベントに複写しない。



## データフロー台帳の更新

| フロー | 送信元 | 送信先 | 状態 |
|---|---|---|---|
| 管理操作イベント | operator-network | control-plane | 確認済み |
| 証跡の収集ジョブ | control-plane | evidence-vault | 確認済み |
| 委託先接続ログ | vendor-edge | control-plane | 境界名を修正中 |



## 次の作業

1. Edge Platform が Vendor Edge のネットワーク区分をサービス台帳に反映する。
2. Trust Engineering が証跡抜粋のデータ項目を Privacy Office と確認する。
3. Security Operations が緊急操作の検知ルールと脅威モデルのリンクを追加する。

次回は 8月上旬の設計レビューで、更新後の境界図と運用手順に矛盾がないかを確認する。
