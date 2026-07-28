```xml
<?xml version="1.0" encoding="UTF-8"?>
<closeExceptions company="東雲フルフィルメント株式会社" closeMonth="2026-02" generatedAt="2026-03-04T10:05:00+09:00">
  <exception id="CE-202602-008" severity="medium">
    <category>expense_cutoff</category>
    <department>物流企画部</department>
    <description>2月28日納品の配送委託費について請求書が未着</description>
    <proposedEntry account="配送委託費" amountJpy="932000">見越計上候補</proposedEntry>
    <owner>石田</owner>
    <status>reviewed</status>
  </exception>
  <exception id="CE-202602-011" severity="low">
    <category>master_data</category>
    <department>情報システム部</department>
    <description>Orion利用料の配賦先に旧部門コードが残存</description>
    <proposedEntry account="システム利用料" amountJpy="0">翌月マスタ更新</proposedEntry>
    <owner>杉本</owner>
    <status>scheduled</status>
  </exception>
</closeExceptions>
```
