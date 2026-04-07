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

CREATE OR REPLACE VIEW v_professional_lead_signals AS
WITH base AS (
  SELECT
    *,
    lower(coalesce(company_name, '')) AS company_name_lc,
    lower(coalesce(title, '')) AS title_lc,
    lower(coalesce(industry, '')) AS industry_lc,
    lower(coalesce(website, '')) AS website_lc
  FROM v_businesses
)
SELECT
  *,
  CASE
    WHEN title_lc LIKE '%interior designer%' OR industry_lc LIKE '%interior design%' OR company_name_lc LIKE '%interior design%'
      THEN 'interior_designer'
    WHEN title_lc LIKE '%builder%' OR industry_lc LIKE '%builder%' OR company_name_lc LIKE '%builder%' OR title_lc LIKE '%home builder%'
      THEN 'builder'
    WHEN title_lc LIKE '%realtor%' OR title_lc LIKE '%real estate%' OR title_lc LIKE '%broker%' OR industry_lc LIKE '%real estate%' OR company_name_lc LIKE '%realty%'
      THEN 'real_estate'
    WHEN title_lc LIKE '%contractor%' OR industry_lc LIKE '%contractor%' OR company_name_lc LIKE '%contractor%'
      THEN 'contractor'
    WHEN title_lc LIKE '%electrician%' OR title_lc LIKE '%electrical%' OR industry_lc LIKE '%electric%' OR company_name_lc LIKE '%electric%'
      THEN 'electrician'
    ELSE 'other'
  END AS primary_profession,
  CASE
    WHEN title_lc LIKE '%interior designer%' OR industry_lc LIKE '%interior design%' THEN 0.95
    WHEN title_lc LIKE '%builder%' OR title_lc LIKE '%home builder%' OR industry_lc LIKE '%builder%' THEN 0.90
    WHEN title_lc LIKE '%realtor%' OR title_lc LIKE '%broker%' OR industry_lc LIKE '%real estate%' THEN 0.88
    WHEN title_lc LIKE '%contractor%' OR industry_lc LIKE '%contractor%' THEN 0.86
    WHEN title_lc LIKE '%electrician%' OR title_lc LIKE '%electrical%' OR industry_lc LIKE '%electric%' THEN 0.82
    ELSE 0.20
  END AS profession_confidence,
  CASE
    WHEN industry_lc LIKE '%interior design%' OR industry_lc LIKE '%lighting%' OR industry_lc LIKE '%home improvement%' OR industry_lc LIKE '%renovat%' OR industry_lc LIKE '%remodel%' THEN TRUE
    WHEN company_name_lc LIKE '%lighting%' OR company_name_lc LIKE '%kitchen%' OR company_name_lc LIKE '%bath%' OR company_name_lc LIKE '%design%' THEN TRUE
    ELSE FALSE
  END AS has_space_product_signal,
  CASE
    WHEN title_lc LIKE '%owner%' OR title_lc LIKE '%president%' OR title_lc LIKE '%principal%' OR title_lc LIKE '%partner%' OR title_lc LIKE '%director%' OR title_lc LIKE '%realtor%' OR title_lc LIKE '%broker%' THEN TRUE
    ELSE FALSE
  END AS has_buying_influence_signal,
  CASE
    WHEN coalesce(contact_full_name, '') <> '' THEN TRUE ELSE FALSE
  END AS has_named_contact,
  CASE
    WHEN coalesce(direct_phone, '') <> '' THEN TRUE ELSE FALSE
  END AS has_direct_phone,
  CASE
    WHEN domain IS NOT NULL AND domain <> '' AND website_lc NOT LIKE '%facebook%' AND website_lc NOT LIKE '%instagram%' AND website_lc NOT LIKE '%linkedin%' THEN TRUE
    ELSE FALSE
  END AS has_business_domain
FROM base;

CREATE OR REPLACE VIEW v_professional_leads AS
WITH scored AS (
  SELECT
    *,
    CASE primary_profession
      WHEN 'interior_designer' THEN 25
      WHEN 'builder' THEN 24
      WHEN 'real_estate' THEN 22
      WHEN 'contractor' THEN 21
      WHEN 'electrician' THEN 19
      ELSE 4
    END AS profession_score,
    CASE
      WHEN has_space_product_signal AND primary_profession IN ('interior_designer', 'builder', 'contractor') THEN 20
      WHEN has_space_product_signal THEN 16
      WHEN primary_profession IN ('real_estate', 'electrician') THEN 12
      ELSE 5
    END AS industry_fit_score,
    CASE
      WHEN employee_count BETWEEN 2 AND 50 THEN 15
      WHEN employee_count BETWEEN 51 AND 250 THEN 13
      WHEN employee_count IS NULL THEN 8
      WHEN employee_count = 1 THEN 9
      ELSE 10
    END AS commercial_value_score,
    (
      CASE WHEN has_email THEN 5 ELSE 0 END +
      CASE WHEN has_business_domain THEN 4 ELSE 0 END +
      CASE WHEN has_named_contact THEN 3 ELSE 0 END +
      CASE WHEN has_direct_phone THEN 3 ELSE 0 END
    ) AS contact_quality_score,
    CASE
      WHEN primary_profession IN ('interior_designer', 'builder', 'contractor') AND has_buying_influence_signal THEN 15
      WHEN primary_profession IN ('real_estate', 'electrician') AND has_buying_influence_signal THEN 12
      WHEN has_buying_influence_signal THEN 9
      ELSE 5
    END AS project_conversion_score,
    CASE
      WHEN primary_profession = 'interior_designer' THEN 10
      WHEN primary_profession = 'builder' THEN 10
      WHEN primary_profession = 'contractor' THEN 9
      WHEN primary_profession = 'real_estate' THEN 8
      WHEN primary_profession = 'electrician' THEN 7
      ELSE 2
    END AS rebate_fit_score
  FROM v_professional_lead_signals
)
SELECT
  *,
  profession_score + industry_fit_score + commercial_value_score + contact_quality_score + project_conversion_score + rebate_fit_score AS total_score,
  CASE
    WHEN profession_score + industry_fit_score + commercial_value_score + contact_quality_score + project_conversion_score + rebate_fit_score >= 85 THEN 'A+'
    WHEN profession_score + industry_fit_score + commercial_value_score + contact_quality_score + project_conversion_score + rebate_fit_score >= 75 THEN 'A'
    WHEN profession_score + industry_fit_score + commercial_value_score + contact_quality_score + project_conversion_score + rebate_fit_score >= 60 THEN 'B'
    WHEN profession_score + industry_fit_score + commercial_value_score + contact_quality_score + project_conversion_score + rebate_fit_score >= 40 THEN 'C'
    ELSE 'D'
  END AS lead_grade,
  concat_ws('; ',
    'profession=' || primary_profession,
    'profession_confidence=' || cast(round(profession_confidence, 2) as varchar),
    CASE WHEN has_space_product_signal THEN 'space_product_signal' ELSE NULL END,
    CASE WHEN has_buying_influence_signal THEN 'buying_influence_signal' ELSE NULL END,
    CASE WHEN NOT has_email THEN 'missing_email' ELSE NULL END,
    CASE WHEN NOT has_business_domain THEN 'weak_domain_signal' ELSE NULL END
  ) AS score_reason_detail
FROM scored;

CREATE OR REPLACE VIEW v_neosgo_priority_leads AS
SELECT *
FROM v_professional_leads
WHERE primary_profession IN ('interior_designer', 'builder', 'real_estate', 'contractor', 'electrician')
  AND lead_grade IN ('A+', 'A', 'B');
