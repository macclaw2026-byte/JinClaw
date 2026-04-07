# Explainable prospect scoring model

Score out of 100.

## A. Industry fit (0-30)
Highest-value target profiles:
- Interior design / design firm: 30
- Builder / developer / construction company: 28
- General contractor / remodeler: 27
- Electrician / electrical contractor / lighting installer: 25
- Realtor / brokerage / property-focused professionals: 22

## B. Buying or recommendation influence (0-20)
Signals from title:
- Owner, Principal, President, Founder
- Principal Designer, Senior Designer
- Project Manager, Procurement, Purchasing
- Broker/Team Lead

## C. Business scale / commercial relevance (0-15)
Use employee count, annual sales, and company footprint.

## D. Neosgo professional-account fit (0-20)
How likely this lead can benefit from referral/commission logic.

## E. Contactability (0-10)
Valid email, phone, website, usable company identity.

## F. Market priority (0-5)
Optional weighting for target states/metros.

## Output requirements
Each score should store:
- total score
- component scores
- textual reason summary
- segment label (S/A/B/C)
