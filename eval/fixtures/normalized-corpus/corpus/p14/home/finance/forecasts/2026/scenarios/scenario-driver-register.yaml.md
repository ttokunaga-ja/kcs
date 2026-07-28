```yaml
scenario_set: "FY2026 Q2 planning refresh"
prepared_by: "経営企画・佐伯"
prepared_at: "2026-04-02T16:00:00+09:00"
base_scenario: "base_case"
drivers:
  fulfilled_orders:
    unit: "件"
    base_case: "既存顧客の出荷増を中心に計画値を維持"
    upside_case: "大型EC顧客の追加受託を7月から反映"
    downside_case: "季節商材の受注鈍化を想定"
    owner: "営業企画"
  carrier_rate:
    unit: "円/件"
    base_case: "現行契約単価と四半期ごとの燃料調整"
    upside_case: "燃料調整額の縮小"
    downside_case: "配送網再編による単価上昇"
    owner: "物流企画"
  west_tokyo_dc_start:
    unit: "稼働月"
    base_case: "2026-09"
    upside_case: "2026-08"
    downside_case: "2026-10"
    owner: "拠点開発"
review_rules:
  - "未承認案件はベースケースへ含めない。"
  - "見越計上の確定後、費用ドライバーを再計算する。"
  - "差異説明は部門コードの変換後データで行う。"
```
