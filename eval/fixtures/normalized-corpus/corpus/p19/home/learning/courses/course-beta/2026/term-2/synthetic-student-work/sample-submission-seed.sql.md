```sql
-- Review practice records for RPS201; kept separate from live submissions.
CREATE TABLE IF NOT EXISTS proposal_practice_rows (
  practice_id TEXT PRIMARY KEY,
  question_text TEXT NOT NULL,
  context_note TEXT NOT NULL,
  method_sketch TEXT NOT NULL,
  review_state TEXT NOT NULL DEFAULT 'ready'
);

INSERT INTO proposal_practice_rows
  (practice_id, question_text, context_note, method_sketch)
VALUES
  ('practice-a', 'How do commuter students use quiet study areas?', 'Campus access patterns', 'Short observation log'),
  ('practice-b', 'What helps readers compare two sources?', 'Evidence note-taking', 'Think-aloud interview');
```
