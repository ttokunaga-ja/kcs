```sql
-- Inspection-step checklist used by the work-instruction editor.
SELECT step_no, checkpoint, required_record
FROM quality.work_instruction_step
WHERE instruction_code = 'WI-QA-021'
  AND lifecycle_state = 'released'
ORDER BY step_no;

UPDATE quality.work_instruction_step
SET required_record = 'first_piece_photo'
WHERE instruction_code = 'WI-QA-021'
  AND checkpoint = '工具交換後の初品確認';
```
