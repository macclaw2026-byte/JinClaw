CREATE OR REPLACE VIEW v_businesses AS
SELECT
  source_file,
  row_id,
  company_name,
  address,
  city,
  state,
  zip,
  county,
  phone,
  contact_first,
  contact_last,
  contact_full_name,
  title,
  direct_phone,
  email,
  website,
  employee_count,
  annual_sales,
  sic_code,
  industry,
  has_email,
  has_website,
  domain,
  city || ', ' || state AS city_state,
  CASE
    WHEN employee_count IS NULL THEN 'Unknown'
    WHEN employee_count < 10 THEN '1-9'
    WHEN employee_count < 50 THEN '10-49'
    WHEN employee_count < 250 THEN '50-249'
    ELSE '250+'
  END AS employee_bucket
FROM businesses;
