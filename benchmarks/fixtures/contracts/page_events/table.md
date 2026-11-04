# Table page_events

Partitioned by event_date. payload holds free-form event JSON. Dataset example_web.

| Column | Type |
|---|---|
| event_id | STRING |
| event_date | DATE |
| user_id | STRING |
| event_name | STRING |
| payload | JSON |
