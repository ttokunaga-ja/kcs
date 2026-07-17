# folder-history 設計監査 r14 — 名寄せ裁定記録

日付: 2026-07-16
対象: `docs/research/folder-history-sqlite-design.md` (裁定前 2,762 行 → 適用後 2,916 行)
入力: 8 系統の監査報告
ユーザー合意: 全部適用 (回帰補修 2 + major 7 + minor 24。fatal 主張はすべて降格)

| 系統 | 概要 | 判定 | fatal/major 主張 |
| --- | --- | --- | --- |
| S1 | Fable (O17 + Q01-Q03) | 不合格 | major 1 |
| S2 | R01-R07 + P01-P03 | 不合格 | fatal 2 + major 2 |
| S3 | 条件付き合格 (Q01 のみ) | 条件付き合格 | 0 (minor 1) |
| S4 | O28 + Q01-Q03 | 不合格 | major 1 |
| S5 | Codex (O28 + Q01-Q09) | 不合格 | fatal 4 + major 4 |
| S6 | 65 シナリオ系 (O28 + Q01-Q14) | 不合格 | fatal 7 + major 6 |
| S7 | Opus オーケストレータ統合 (→ `folder-history-design-audit-r14-opus.md` へ改名) | 不合格 | major 2 |
| S8 | Sonnet オーケストレータ (`folder-history-design-audit-r14-sonnet.md`) | 不合格 | major 2 |

**集約判定: 不合格 → 全採用項目を適用済み。** fatal 0 (13 件の fatal 主張は全て降格 or 却下 —
基準: fatal は恒久停止・データ喪失・SQL 非機能のみ。課金の記録喪失は「台帳 = 下限」で有界 = major)。
破壊型 regression は 4 ラウンド連続 0。検出の重心は「r13 新設規範の照合点非対称」(M1/M2/M3) と
「終端・分岐の欠落」(M4/M7/M8) — "fix が開けた穴" 15 例目 = M1 (sweep 自身が塞ぐはずの穴を sweep が持つ)。

---

## 回帰補修 (2 件)

| ID | 系統 | 内容 | 適用 |
| --- | --- | --- | --- |
| O28 残存 | S4/S5/S6/S7 | §5.7「この record から読む」/ §8-c「(§5.7 record)」が r13 修正 (参照元 = app_config) と同一文書内で矛盾 | 両箇所を app_config 参照へ統一。§5.7 に単独検索規則 (§11.2) との役割分担を明記 |
| O17 残存 | S1 | §10 step -1「step 0〜4 から除外」vs 注記「collect は通常どおり実行してよい」の矛盾 | 除外リストに「ただし step 2/4 の in-flight collect・detached 処理は除外しない」を明記 (除外対象 = 巻き戻った状態を入力にする scan/reconcile/submit/replicate) |

## major 採用 (7 件)

| ID | 系統 (元 severity) | 内容 | 適用 |
| --- | --- | --- | --- |
| M1 | S5-Q03(fatal)/S6-Q06(fatal)/S7-Q01 + S7-Q04 統合 | (b')/token sweep 前段が found/unknown の 2 分岐のみで confirmed-absent の期限判定を欠く — 保持期限超で消えた課金済み job を無記帳で掃除・NULL 化 | detached (b) と同一の期限判定を (b')/sweep へ移植 (期限超 = 述語 → 記帳 (token) → 掃除 / 期限内 = 記帳なしで掃除)。DDL コメントの値規則も正確化 (found = 発見 job id / 期限超 absent = intent_token) |
| M2 | S8-Q01 | 無 id 記帳 3 箇所 (期限超 (ii)・(b')・sweep) が batch_requests.submission_seq の行 UPDATE を明記せず — 次の正規 close が同じ seq を計算し ON CONFLICT が実課金を黙って吸収 | 3 箇所に「同一 Tx で行を +1 へ UPDATE し、その新値で記帳」を明示 (相 3 / found 採用と同形。DDL L852「その時点の…」と整合) |
| M3 | S3-Q01(minor)/S5-Q02(fatal)/S6-Q04(fatal)/S7-Q03(minor) | 期限超の (iii) attempts+1 の直後、(iv) が上限を見ずに無条件 rotation — client_exhausted の server 対応物欠落で上限が素通り | (iii') を新設: attempts >= 上限なら state=3 (error='expired') で terminal 化し (iv) を行わない。token は記帳済み・掃除は 4.5 sweep が引継ぎ。復帰は明示 retry |
| M4 | S6-Q05(fatal) | §21.2 の削除条件が intent_token を見ない — close 後・(b') 前クラッシュの terminal 行 (token 残存) を削除すると課金追跡が再駆動キーごと消える | §21.2 削除条件に「かつ intent_token IS NULL」を追加。§9.1 detached 削除条件にも「intent_token 非 NULL は削除しない」を追加 (§9.3-d/fork は §21.2 参照で自動追随) |
| M5 | S7-Q02 | フォルダ単独検索の :current_tool 決定規則が無い (§11.2 は embedding のみ・eligible は tool gate 必須・mapping 表は app_config を明示除外) — tool 切替後の単独検索が実装不能 | :current_tool = markdown_documents の最新 generated_at の tool_profile_hash と定義。embedding (混在停止) との非対称は意図と明記。mapping 表にも反映 |
| M7 | S5-Q04(fatal)/S6-Q09(fatal) + S8-Q02(minor) 統合 | restore の保全〜rename 間の外部編集が働き先・履歴の両方から消える + 安定確認失敗時の挙動未規定 | §21.4 手順 3a: 安定確認失敗 = restore 中止 + status / rename 直前の再 lstat 照合を in-place では義務化 (§20.5 の「任意の強化」を格上げ) / 残余窓は §20.5 TOCTOU と同族の既知の残余と注記 |
| M8 | S5-Q05/S6-Q10 前段(fatal)/S7-Q14 + S7-Q05 統合 | 破損 journal の「明示解決」に対応する操作が存在せず、回復先行ゲートの literal 読みで全操作が恒久ブロック。§21.1 register も対象内の fork-journal を見ない | §21.3「journal の破損」に明示解決の実体を定義 (= §20.4 damaged 復旧: journal/flag 除去 → 新 id 再登録。回復ゲートの唯一の例外 — §21 前文にも明記)。§21.1 手順 1 に fork-journal チェック追加 (有効 = 回復先行 / 破損 = 明示解決のみ提示) |

## minor 採用 (24 件)

| # | 系統 | 内容 → 適用 |
| --- | --- | --- |
| m1 | S8-Q05(major→minor)/S7-Q19(proposal) | 期限内 confirmed-absent の伝播猶予 (token 時刻から既定 10 分は unknown 扱い — read-after-write 整合を仮定しない)。全照合点共通と明記 |
| m2 | S7-Q10 | 期限超 (iv) にも token ベースの upload 残骸掃除 (未記録 upload 含む) を明記 |
| m3 | S7-Q09/S6-Q12(minor) | ts の「発生月へ正しく配賦」→「確定月への配賦 (provider 請求時刻とはずれ得る — 正はプロバイダ側 §16)」 |
| m4 | S7-Q11 | 規約 7-(a): 全損時は in-flight 全 job が対象 (「server = 1 job」は健在時のクラッシュ窓の主張) と補正 |
| m5 | S7-Q12 | upload 削除・job 残骸掃除の「404 = 成功」を明記 (upload 後始末・sweep の両方) |
| m6 | S6-Q02(fatal→minor)/S7-Q13 | §10 step 4 のローカル vec を DELETE→INSERT に統一 (agg §9.3-c と同形) + §13 fsck は検出した孤児 vec を削除 (修復) |
| m7 | S6-Q03(major→minor) | §13 fsck に agg 親子整合検査を追加 — 不一致は agg_markdown_documents 行 DELETE + synced NULL 化で次 Replicate が全置換 |
| m8 | S8-Q11 | §8-c が profile hash を照合しない非対称は意図と明記 (行単位置換 + §11.2 gate が移行を扱う) |
| m9 | S6-Q11(major→minor)/S7-Q16 | flag 掃除 (journal 無) を id=new 限定に強化。id=old は damaged/明示解決待ち。字句「journal 記録の」→「fork_in_progress 記録 (flag の JSON)」 |
| m10 | S5-Q08(major→minor) | fork 手順 0 の前に「folders[old_id] あり・root_path 不一致なら §20.4 rebind 判定を先に完了」(was_tracked 誤判定 → 旧行残留 → damaged 偽表示を防止) |
| m11 | S8-Q09 | fork_in_progress に started_at を追加 (DDL コメント含む 2 箇所)、猶予 30 日超過で status を「fork stalled — 手動介入」へ格上げ (表示のみ) |
| m12 | S6-Q14(major→minor)/S8-Q10 | 規約 12: standalone read も fork-journal を preflight 検査 (有効 = fork 進行中で保留 / 破損 = damaged)。同 id が別 path 登録済みなら「重複コピー」を provenance に付す |
| m13 | S7-Q06 | §20.5 に insensitive 復帰時の複数系列 fold 一致 tie-break (BINARY 一致優先 → バイト昇順)。非採用系列は delete 確認へ |
| m14 | S7-Q07 | §6/§7 エスケープ条件の非対称 → **注記: 適用見送り (下記)** |
| m15 | S8-Q06/S7-Q08 | grammar v: 画像 0 文書は版判定の対象外 (常にスキップ) + 未知 v の再解析は fail-closed でスキップ + status |
| m16 | S8-Q07 | §12 解決チェーンに提示前の SHA-256 再照合 (restore と同じ規律。不一致は fsck へ誘導) |
| m17 | S8-Q08 | fork 手順 5 に「fork 完了直後・次 scan 前の GC 禁止」注記 (現在版原本が一時的に参照ゼロ) |
| m18 | S5-Q09 | 「OR IGNORE なら黙って欠落」の事実誤認を修正 — SQLite の ON CONFLICT は FK に適用されず、Tx が音を立てて失敗する (結論の保存表記固定は不変) |
| m19 | S2-R04/P02 | :query_vector の bind 形式を明記 (float32 LE raw BLOB、dimensions×4 バイト) |
| m20 | S1-Q02/S8-Q04(proposal) | §9.2 agg_chunk_fts の読み替え規則を明文化 (機械的に一意な対応表) |
| m21 | S4-Q02 | §8-e「破棄」の係り受け明確化 — agg_embeddings は行 DELETE、agg_vec のみ DROP→CREATE |
| m22 | S4-Q03/S7-Q15/S8-Q12 | profile 未設定 (bootstrap 直後) の submit/前計上は skip + status「profile 未設定」(遷移表の前に明記) |
| m23 | S7-Q18(proposal→minor) | §8 (ii) に「内容起因 4xx = 課金なし」がプロバイダ前提である旨を明文化 |
| m24 | S5-Q07 救済 | backup 規範に「復元も tick.lock 下で。lock 外の外部復元は z 判定が回収する (検出前提の回収経路であり静止復元が正)」を注記 |

**m14 の見送り理由**: S7-Q07 は「§6 のエスケープ条件 (行頭 `![`+`](obj:` 含む) が §7 認識形 (行全体
grammar 一致) の上位集合で、`![diagram](obj:see appendix)` 型の本文が un-escape されず `\` が残留」
という主張。ただし §6 のエスケープ条件を §7 の行全体一致 (hash64 込み) に狭めると、**phantom 防止の
二層目が弱まる** (hash64 部分だけ将来 grammar が緩んだ場合や部分一致攻撃面)。`\` の残留は表示上の
軽微な汚れで chunks の同一性・可逆性 (grammar 一致行) には影響しないため、r14 では条件変更せず
**現状維持が安全側**と裁定 (単一系統・S8 の X50 全段可逆検証も grammar 一致行では生存)。次回以降に
反証が出れば再考。

## 却下 (13 件)

| 指摘 | 却下理由 |
| --- | --- |
| S2-R01 (seq DEFAULT 0, fatal) | DDL コメント (L799-805) が MAX 継承と衝突理由を既に明記 — 精読不足 |
| S2-R02 (batch_job_id 意味論, fatal) | 値規則明記済み + cost_estimated=1 が推定記帳を区分。r13 採用済みの意図された設計 |
| S2-R03 (audit_ddl.sql の CHECK 欠落) | 監査側スクリプトの不備。設計文書は 3 本とも保持 (L827-830) |
| S2-R05 (missing_since CHECK) | 全 INTEGER 列への範囲 CHECK は過剰規範 |
| S2-R06 (LIKE 非 ASCII 乖離) | §11.2 は LIKE/instr を同一 ASCII 折り畳みに揃える設計を明記済み — 両者一貫で乖離しない |
| S2-R07 (fp_cache 確定条件) | 「fp 一致でも marker チェックは常に行う」の既存注意書きが被覆 (S2 自身が認める) |
| S1-Q01 (client 再実行の述語誤作動, major) | client 記帳の冪等性は seq キーの ON CONFLICT (§8(iii)) — batch_job_id 述語は server 期限超専用で client に存在しない。再実行は「row の現 seq を記帳 → +1」で中間 attempt は漏れない (S8-X41 #98-100 も独立に問題なし判定) |
| S5-Q06 (upload U1/U2 上書き, major) | r11/r12/r13 で 3 回却下済みの既知の残余 (L949 自己文書化) — **4 回目** |
| S5-Q07 (外部 metadata-only restore, fatal) | §9.3-z/step -1 が回収機構として設計済み (working 不変で再コミット・GC 24h grace)。運用注記のみ採用 (m24) |
| S6-Q07 (b' の attempts 未更新, fatal) | attempts は profile 世代別予算 (§8-a リセットは意図)。増殖には利用者の意図的 profile 往復が必要 — S8-X21 の proposal 降格と同根。課金は ledger 記帳される |
| S6-Q08 (raw 不在 restore が delete を消す, major) | 規約 11 (履歴反映はスキャン経由の単一経路) + tick 間隔内操作の丸め (X1 同族) は設計原理そのもの |
| S6-Q10 後段 (register も回復ゲートで停止, fatal の一部) | register は手順内に fork ゲートを持たず開始可能 (S7 が grep で実測)。M8 で journal チェックを正式化 |
| S6-Q13 (時計 31 日前進×退役, major) | 退役は再発見で可逆 (層 1 無傷・コスト = agg 再構築)。S8-X4 が同シナリオを独立に問題なし判定 |

## proposal 見送り (4 件)

S7-Q17 (Windows 予約デバイス名 — dirfd 規律で破綻を構成できず) / S8-Q03 (fork 回復後の
unregister no-op — UX 注記のみの価値) / S2-P01 (規約の相互参照付与) / S2-P03 (MRL 説明の詳細化 —
参考値の位置づけのため)。

---

## 全指摘 ID 対応表

| 系統 | ID | 対応 |
| --- | --- | --- |
| S1 | O17 | 回帰補修 (採用) |
| S1 | Q01 | 却下 (client は seq キー冪等) |
| S1 | Q02 | m20 採用 |
| S1 | Q03 | O17 補修に統合 |
| S2 | R01/R02/R03/R05/R06/R07 | 却下 ×6 |
| S2 | R04 | m19 採用 |
| S2 | P01/P03 | 見送り |
| S2 | P02 | =R04 (m19) |
| S3 | Q01 | M3 採用 (minor→major 統合) |
| S4 | O28 | 回帰補修 (採用) |
| S4 | Q01 | =O28 |
| S4 | Q02 | m21 採用 |
| S4 | Q03 | m22 採用 |
| S5 | O28/Q01 | 回帰補修 |
| S5 | Q02 | M3 採用 (fatal→major) |
| S5 | Q03 | M1 採用 (fatal→major) |
| S5 | Q04 | M7 採用 (fatal→major) |
| S5 | Q05 | M8 採用 (major) |
| S5 | Q06 | 却下 (4 回目) |
| S5 | Q07 | 却下 + m24 注記 |
| S5 | Q08 | m10 採用 (major→minor) |
| S5 | Q09 | m18 採用 |
| S6 | O28/Q01 | 回帰補修 |
| S6 | Q02 | m6 採用 (fatal→minor) |
| S6 | Q03 | m7 採用 (major→minor) |
| S6 | Q04 | M3 採用 (fatal→major) |
| S6 | Q05 | M4 採用 (fatal→major) |
| S6 | Q06 | M1 採用 (fatal→major) |
| S6 | Q07 | 却下 (profile 世代別予算は意図) |
| S6 | Q08 | 却下 (スキャン単一経路の原理) |
| S6 | Q09 | M7 採用 (fatal→major) |
| S6 | Q10 | 前段 M8 採用 (fatal→major) / 後段却下 |
| S6 | Q11 | m9 採用 (major→minor) |
| S6 | Q12 | m3 採用 |
| S6 | Q13 | 却下 (可逆・S8 と判定相反) |
| S6 | Q14 | m12 採用 (major→minor) |
| S7 | O28 | 回帰補修 |
| S7 | Q01 | M1 採用 |
| S7 | Q02 | M5 採用 |
| S7 | Q03 | M3 採用 (minor→major 統合) |
| S7 | Q04 | M1 に統合 (DDL 値規則) |
| S7 | Q05 | M8 に統合 |
| S7 | Q06 | m13 採用 |
| S7 | Q07 | m14 — **見送り** (理由上記) |
| S7 | Q08 | m15 採用 |
| S7 | Q09 | m3 採用 |
| S7 | Q10 | m2 採用 |
| S7 | Q11 | m4 採用 |
| S7 | Q12 | m5 採用 |
| S7 | Q13 | m6 採用 |
| S7 | Q14 | M8 採用 (minor→major 統合) |
| S7 | Q15 | m22 採用 |
| S7 | Q16 | m9 採用 |
| S7 | Q17 | 見送り |
| S7 | Q18 | m23 採用 (proposal→minor) |
| S7 | Q19 | m1 採用 (proposal→minor) |
| S8 | Q01 | M2 採用 |
| S8 | Q02 | M7 に統合 |
| S8 | Q03 | 見送り |
| S8 | Q04 | m20 採用 |
| S8 | Q05 | m1 採用 (major→minor) |
| S8 | Q06 | m15 採用 |
| S8 | Q07 | m16 採用 |
| S8 | Q08 | m17 採用 |
| S8 | Q09 | m11 採用 |
| S8 | Q10 | m12 採用 |
| S8 | Q11 | m8 採用 |
| S8 | Q12 | m22 採用 |

## 適用後の検証

- 残存禁止パターン (旧記述) 0 件: 「現行 profile (§5.7 record)」「dimensions をこの record から
  読む」「(期限超 confirmed-absent・token sweep) は」「journal 記録の old_id」「発生月へ正しく
  配賦」「OR IGNORE なら履歴が黙って」
- 新規パターン出現確認: 伝播猶予 ×5 / batch_requests.submission_seq を +1 へ UPDATE ×3 /
  error='expired' ×1 / intent_token IS NULL (§21.2) + 非 NULL 保持 (§9.1) / started_at ×3 /
  fork stalled ×1 / 最新 generated_at ×3 / 親子整合 ×1 / 明示解決の実体 ×1
- 行数: 2,762 → 2,916 (+154)

## 次ラウンド (r15) の要点

- 検証リスト: M1〜M8 + m1〜m24 (m14 見送り含む) を P 採番で追加。特に重点:
  (a) M2 の seq 行 UPDATE ×3 箇所が新たな衝突・二重加算を生まないか (期限超 (ii) → (iv) 相 1 →
  相 3 の連番一貫)、(b) M3 の error='expired' terminal と遷移表・明示 retry・sweep の整合、
  (c) M1 の期限判定移植で (b')/sweep/detached/intent 回復の 4 照合点が完全対称になったか、
  (d) M8 の回復ゲート例外が新たな穴 (例外経路の悪用・damaged 誤誘導) を開けないか、
  (e) M5 の最新 generated_at 規則の決定性 (同時刻 tie-break は §5.3 の単調採番で排除されるか)
- m14 (エスケープ条件非対称) は保留論点として X 観点に残す
