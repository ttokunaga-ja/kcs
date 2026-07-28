```sql
-- ORCHID-CKD プログラムの週次スクリーニング用。
-- 対象は CKD の支持療法、腎機能モニタリング、研究運用に関する文献。
WITH candidate_articles AS (
    SELECT
        a.article_id,
        a.title,
        a.journal,
        a.publication_date,
        a.abstract_text,
        a.language
    FROM literature.article AS a
    WHERE a.publication_date >= DATE '2023-01-01'
      AND a.language IN ('ja', 'en')
      AND (
          a.title ILIKE '%chronic kidney disease%'
          OR a.abstract_text ILIKE '%chronic kidney disease%'
          OR a.title ILIKE '%慢性腎臓病%'
          OR a.abstract_text ILIKE '%慢性腎臓病%'
      )
), tagged_articles AS (
    SELECT
        c.article_id,
        c.title,
        c.journal,
        c.publication_date,
        c.language,
        STRING_AGG(t.tag_name, ', ' ORDER BY t.tag_name) AS matched_topics
    FROM candidate_articles AS c
    LEFT JOIN literature.article_tag AS t
      ON t.article_id = c.article_id
    WHERE t.tag_name IN ('supportive care', 'renal monitoring', 'trial operations', 'safety review')
       OR t.tag_name IS NULL
    GROUP BY c.article_id, c.title, c.journal, c.publication_date, c.language
)
SELECT
    article_id,
    title,
    journal,
    publication_date,
    language,
    COALESCE(matched_topics, 'manual triage') AS screening_route
FROM tagged_articles
ORDER BY publication_date DESC, title;
```
