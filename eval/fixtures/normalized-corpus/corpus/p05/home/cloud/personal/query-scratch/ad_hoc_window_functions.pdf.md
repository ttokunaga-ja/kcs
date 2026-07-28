Harborline Commerce | Commercial Intelligence

Query scratchbook



Harborline Commerce | Commercial Intelligence

Query scratchbook



Harborline Commerce | Commercial Intelligence

Query scratchbook

AD-HOC ANALYSIS NOTE | FY2026 Q2



Harborline Commerce | Commercial Intelligence
Query scratchbook
AD-HOC ANAL YSIS NOTE | FY2026 Q2
Harborline Storefront
partition
7
1.
2.
3.
‘ORDER BY‘
Owner: Commercial Intelligence • Working material
1 / 3


Harborline Commerce | Commercial Intelligence
Query scratchbook
PATTERN 01 | DAIL Y MOVEMENT
7
WITH daily_sales
AS
SELECT
business_date,
territory_group,
SUM
(net_sales_amount)
AS
net_sales
FROM
mart_storefront_daily
WHERE
business_date >=
DATE
'2026-04-01'
GROUP BY
1, 2
SELECT
business_date,
territory_group,
net_sales,
net_sales - LAG(net_sales) OVER w
AS
day_delta,
AVG
(net_sales) OVER (
PARTITION
BY
territory_group
ORDER BY
business_date
ROWS BETWEEN
6 PRECEDING
AND
CURRENT ROW
AS
rolling_7d
FROM
daily_sales
WINDOW w
AS
PARTITION
BY
territory_group
ORDER BY
business_date
ORDER BY
territory_group, business_date;
‘day_delta‘
0
7
Scratch pattern • not production SQL
2 / 3


Harborline Commerce | Commercial Intelligence
Query scratchbook
PATTERN 02 | MONTH-TO-DATE
SELECT
business_date,
channel_name,
SUM
(net_sales_amount)
AS
daily_sales,
SUM
SUM
(net_sales_amount)) OVER (
PARTITION
BY
DATE_TRUNC('month', business_date), channel_name
ORDER BY
business_date
AS
month_to_date_sales,
RATIO_TO_REPORT(
SUM
(net_sales_amount)) OVER (
PARTITION
BY
business_date
AS
daily_mix
FROM
mart_storefront_daily
WHERE
business_date
BETWEEN DATE
'2026-04-01'
AND DATE
'2026-06-30'
GROUP BY
1, 2
ORDER BY
1, 2;
•
•
•
•
Harborline Storefront • Q2 close preparation
3 / 3


# PATTERN 01 | DAILY MOVEMENT



# PATTERN 02 | MONTH-TO-DATE



# 月次レビュー前の累計確認



# 前日比と 7 日平均



# ウィンドウ関数の
探索メモ

Harborline Storefront の日次売上を読むための下書き

**このメモの位置づけ** 定例モデルに入れる前の検算用クエリ。確定レポートの数値は、必ず正式な月次モデルを参照する。



# 検算用の形

WITH daily_sales AS (
    SELECT
        business_date,
        territory_group,
        SUM(net_sales_amount) AS net_sales
    FROM mart_storefront_daily
    WHERE business_date >= DATE '2026-04-01'
    GROUP BY 1, 2
)
SELECT
    business_date,
    territory_group,
    net_sales,
    net_sales - LAG(net_sales) OVER w AS day_delta,
    AVG(net_sales) OVER (
        PARTITION BY territory_group
        ORDER BY business_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS rolling_7d
FROM daily_sales
WINDOW w AS (
    PARTITION BY territory_group
    ORDER BY business_date
)
ORDER BY territory_group, business_date;



## 累計と構成比


SELECT
  business_date,
  channel_name,
  SUM(net_sales_amount) AS daily_sales,
  SUM(SUM(net_sales_amount)) OVER (
    PARTITION BY DATE_TRUNC('month', business_date), channel_name
    ORDER BY business_date
  ) AS month_to_date_sales,
  RATIO_TO_REPORT(SUM(net_sales_amount)) OVER (
    PARTITION BY business_date
  ) AS daily_mix
FROM mart_storefront_daily
WHERE business_date BETWEEN DATE '2026-04-01' AND DATE '2026-06-30'
GROUP BY 1, 2
ORDER BY 1, 2;




## 使いどころ



### 観測単位

店舗日次。地域と販売チャネルは、必要なときだけ **partition** に加える。



### 見たい変化

前日比、7日移動平均、月初からの累計、同じ曜日との比較。



## 引き渡し前チェック

- 月初の累計が日次合計と一致すること。
- 販売チャネルの合計が全体行と一致すること。
- 対象期間のフィルタをメモ本文とクエリの両方で確認すること。
- よく使う断片は共有前に命名ガイドへ移し、個人用の下書きに残し続けないこと。

Harborline Storefront • Q2 close preparation

3 / 3

### 注意点

返金や取消は確定日ではなく業務日で揃える。遅延到着の行は別途確認する。



## 最初の確認

1. 対象日が連続しているかを確認する。
2. 集計前の明細で重複キーがないかを見る。
3. 'ORDER BY' は表示順ではなく、業務日と安定した補助キーで固定する。

Owner: Commercial Intelligence • Working material

1 / 3

# 読み方

'day_delta' は比較対象がない最初の行では空になる。これを 0 に置換すると、初日の変化が実在したように見えるため、探索段階では空のまま残す。7 日平均は休日の偏りをならすための補助であり、施策評価の結論には使わない。

Scratch pattern • not production SQL

2 / 3