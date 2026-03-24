# Amazon Premium Wholesale Product Selection Branch

Use this branch for Amazon-oriented, broad-but-curated product selection where the goal is to find products that can generate stable natural daily orders in the rough range of tens to low hundreds of units, while avoiding overly regulated, brand-dominated, or fragile categories.

## Goal

Find Amazon products that fit this profile:
- stable natural demand
- survivable competition
- not excessively brand-dominated
- not too operationally complex
- low to moderate barrier for entry
- suitable for a premium-wholesale / curated broad-catalog approach rather than single-SKU hero branding only

## Hard filters (inherit global exclusions)
Still exclude by default:
- food / ingestible / supplements
- medicines / regulated health products
- shampoo / body wash / formulation-heavy body-contact products
- strong brand / IP / infringement-risk products
- obviously hard-to-manufacture or high-liability products

## Multi-source data model

Use several source layers together:

### 1. Amazon public data
- search results pages
- product pages
- category/bestseller surfaces when visible
- review counts
- rating patterns
- price ladder
- listing density
- variant count
- title/offer repetition

### 2. External Amazon research tools (when available)
These may include tools such as:
- Helium 10
- Jungle Scout
- SellerSprite / 卖家精灵
- other Amazon research utilities the user has legitimate access to

Use them for:
- estimated search volume
- keyword relevance
- estimated sales / BSR-driven approximations
- trend consistency
- keyword competition clues

If account access is not available, do not fake those fields. Use public/proxy methods and label confidence accordingly.

### 3. Customer voice
Use forums/reviews/community language to understand:
- recurring pain points
- dissatisfaction with current products
- desired improvements
- sub-niche opportunity clues

### 4. Competitor positioning
Use competitor pages / listings to understand:
- positioning style
- differentiation patterns
- review moat level
- whether mid-tier sellers survive

## Core inference model

Do not pretend to know exact daily sales. Infer a range.

Estimate using a weighted combination of:
- marketplace activity proxies
- review depth and distribution
- external-tool estimates when available
- search/intent strength
- competition survivability
- operational simplicity

## Daily-sales-range objective

Preferred candidate profile:
- likely capable of stable natural daily orders in the tens to low hundreds range
- avoid both dead categories and hyper-competitive giant-volume categories when survivability is weak

## Output requirement for daily report

For the daily final Excel, include one dedicated sheet for this branch.

Minimum target:
- at least 20 product candidates per run
- each product must include:
  - product name / sub-niche
  - why it fits
  - estimated daily sales range
  - evidence grade
  - competition survivability
  - competitor link(s)
  - recommendation
