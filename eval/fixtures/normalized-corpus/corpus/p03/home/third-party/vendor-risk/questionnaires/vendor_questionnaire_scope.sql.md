```sql
-- Vendor Risk の質問票で、Nami Grid の監査対象サービスに関係する回答だけを抽出する。
-- 直接識別子は選ばず、レビューの割り当てに必要な項目だけを返す。

WITH in_scope_services AS (
  SELECT service_id
  FROM vendor_service_mapping
  WHERE service_name IN ('Operator Hub', 'Grid Console', 'Vendor Edge')
    AND lifecycle_state = 'active'
), latest_response AS (
  SELECT
    response.vendor_id,
    response.question_id,
    MAX(response.submitted_at) AS submitted_at
  FROM vendor_questionnaire_response AS response
  GROUP BY response.vendor_id, response.question_id
)
SELECT
  vendor.display_name AS vendor_name,
  question.control_area,
  question.prompt_key,
  response.response_state,
  response.submitted_at,
  mapping.service_id
FROM vendor_questionnaire_response AS response
JOIN latest_response AS latest
  ON latest.vendor_id = response.vendor_id
 AND latest.question_id = response.question_id
 AND latest.submitted_at = response.submitted_at
JOIN vendor AS vendor ON vendor.vendor_id = response.vendor_id
JOIN questionnaire_question AS question ON question.question_id = response.question_id
JOIN vendor_service_mapping AS mapping ON mapping.vendor_id = vendor.vendor_id
JOIN in_scope_services AS scope ON scope.service_id = mapping.service_id
WHERE question.control_area IN ('access_management', 'incident_response', 'subprocessor_management')
ORDER BY vendor.display_name, question.control_area, response.submitted_at DESC;
```
