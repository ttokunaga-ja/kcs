# Poppy Gateway docs の棚卸し

**July 2026 · Ledger Platform**



## 読み手の導線

Poppy Gateway の資料を、初期設定・受信側の実装・障害時の確認に分けて並べ直した。README は短い起動手順に絞り、署名検証や再送の扱いは別ページで背景と一緒に説明する。



## 更新候補

- configuration example から環境依存の値を外す
- webhook receiver の例で、本文を読む前にヘッダを検証する流れを示す
- delivery result の説明に、運用画面で探せる識別子を添える
- Orchid Ledger との関係は event handoff の説明だけにする



## レビュー時の観点

画面操作を知らない実装担当者が、必要な情報に迷わず辿り着けることを確認する。個別の加盟店設定や検証用の通知先は docs に残さない。
