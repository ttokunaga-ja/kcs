# ORCHID-CKD-201 プロトコル運用ドライラン

- 実施日: 2026-07-08
- 場所: Asteria Renal Study Unit, Minato Medical Center
- 区分: 院内運用確認（合成・匿名化レコードのみ）
- 司会: Study Operations Lead



## 目的

初回スクリーニングから適格性確認、割付前の連絡、EDC への記録までを通しで確認した。これは承認済みプロトコルの改訂ではなく、担当間の受け渡しと記録様式を確かめるための作業メモである。



## 使用したシナリオ

| シナリオ | 想定した状況 | 確認した担当 |
|---|---|---|
| ALPHA-SYN-021 | 同意確認済み、検査票が揃っている | CRC / investigator delegate |
| ALPHA-SYN-034 | 検査結果の到着待ち | CRC / central lab liaison |
| ALPHA-SYN-052 | 補足の同意立会確認（supplemental consent-witness confirmation）が未完了 | CRC / investigator delegate |

個人を特定できる情報、実在患者の値、画像は使用していない。



## 実施結果

1. 受付時に subject token と版管理済み同意書の照合を行う手順は問題なく動作した。
2. 検査未完了のレコードは、適格性判定キューではなく不足資料キューへ分けて表示された。
3. 補足の同意立会確認が未完了のレコードは、CRC が完了扱いにせず investigator delegate へ引き渡した。
4. EDC の入力担当と原資料確認担当を別にしたことで、確認済み日時の取り違えを防げた。



## 安全性連絡の確認

異常な検査値や体調変化の連絡は、当日中に担当医へエスカレーションし、記録担当が連絡時刻・受領者・次の確認時刻を残す。継続可否に関する判断は、承認済み文書と担当医の評価に従う。今回のドライランでは判断値を運用メモへ転記しなかった。



## フォローアップ

| 担当 | 作業 | 期限 |
|---|---|---|
| Data Management | 不足資料キューのラベルを英日併記にする | 2026-07-10 |
| CRC Lead | 電話連絡テンプレートに受領確認欄を追加する | 2026-07-11 |
| Investigator Delegate | supplemental consent-witness confirmation の記録例をレビューする | 2026-07-15 |

次回は site initiation 前に、実運用と同じ権限設定で再確認する。
