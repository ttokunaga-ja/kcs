# Harbor PRD review notes

レビューで確認したいのは、Signal Inbox が「一覧」ではなく引継ぎ可能な判断の単位になるかどうか。



## 問い

- 空の状態で、利用者は最初に何を入れるべきか理解できるか。
- 担当を変えた後、前の判断と次の約束が追えるか。
- Evidence Link を貼れない時、情報がないのか、共有範囲が違うのかを分けられるか。
- Account Brief の編集は、元の会話を消さずに行えるか。



## 受け入れ条件の補足

重要なのは perfect classification ではない。A reviewer should be able to leave a signal in a clear, recoverable state even when the correct owner is not known yet.

| 領域 | 今回確認する | 後で検討する |
| --- | --- | --- |
| タグ | 手動で選べること | 推薦の精度 |
| 担当 | pending と理由を残せること | routing の自動化 |
| 根拠 | 確認日と共有範囲を見せること | 要約の自動生成 |

計測は UI のクリック数ではなく、翌日の再読時に前提が戻せるかを定性・定量で見る。
