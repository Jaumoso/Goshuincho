from django.db import migrations

FORWARD = """
ALTER TABLE visits ADD CONSTRAINT visits_precision_date CHECK (CASE visited_precision
  WHEN 'day'     THEN visited_on IS NOT NULL
  WHEN 'month'   THEN visited_on IS NOT NULL AND extract(day FROM visited_on) = 1
  WHEN 'season'  THEN visited_on IS NOT NULL AND extract(day FROM visited_on) = 1
                      AND extract(month FROM visited_on) IN (3, 6, 9, 12)
  WHEN 'year'    THEN visited_on IS NOT NULL AND to_char(visited_on, 'MM-DD') = '01-01'
  WHEN 'unknown' THEN visited_on IS NULL
END);

CREATE INDEX visits_user_place_idx ON visits (user_id, place_id, visited_on DESC NULLS LAST);

ALTER TABLE stamps ADD CONSTRAINT stamps_visit_fk
  FOREIGN KEY (visit_id, user_id, place_id) REFERENCES visits (id, user_id, place_id)
  ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE stamps ADD CONSTRAINT stamps_goshuincho_fk
  FOREIGN KEY (goshuincho_id, user_id) REFERENCES goshuincho (id, user_id)
  ON DELETE SET NULL (goshuincho_id);

CREATE VIEW user_place_summary AS
WITH live AS (
  SELECT * FROM visits WHERE deleted_at IS NULL AND kind = 'in_person'
),
counts AS (
  SELECT user_id, place_id, count(*) AS visit_count, min(visited_on) AS first_visit
  FROM live GROUP BY user_id, place_id
),
last AS (
  SELECT DISTINCT ON (user_id, place_id)
         user_id, place_id, visited_on AS last_visit, visited_precision AS last_visit_precision
  FROM live
  ORDER BY user_id, place_id, visited_on DESC NULLS LAST
),
st AS (
  SELECT user_id, place_id, count(*) AS stamp_count
  FROM stamps WHERE deleted_at IS NULL GROUP BY user_id, place_id
)
SELECT user_id, place_id,
       coalesce(c.visit_count, 0) AS visit_count,
       c.first_visit, l.last_visit, l.last_visit_precision,
       coalesce(st.stamp_count, 0) AS stamp_count
FROM counts c
JOIN last l USING (user_id, place_id)
FULL JOIN st USING (user_id, place_id);
"""

BACKWARD = """
DROP VIEW user_place_summary;
ALTER TABLE stamps DROP CONSTRAINT stamps_goshuincho_fk;
ALTER TABLE stamps DROP CONSTRAINT stamps_visit_fk;
DROP INDEX visits_user_place_idx;
ALTER TABLE visits DROP CONSTRAINT visits_precision_date;
"""


class Migration(migrations.Migration):
    dependencies = [("visits", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, BACKWARD)]
