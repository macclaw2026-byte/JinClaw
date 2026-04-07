# Scene image workflow

## Goal
Create ecommerce-ready lifestyle images for Neosgo draft listings.

## Minimum acceptance
- at least 3 scene images per listing
- scene images ranked in first 3 slots
- product structure, finish, and proportions remain faithful
- no watermark, no extra wrong fixtures, no obvious deformation

## Working method
1. take a product source image from the listing
2. use ChatGPT image generation with the product image as reference
3. ask for one realistic ecommerce lifestyle scene image
4. download the result locally
5. upload to Neosgo listing
6. verify it appears in the product image list

## Prompt pattern for lighting
Use a prompt like:
- keep the exact fixture structure and finish from the reference
- place it in a realistic room that matches the product type
- keep the product as the hero object
- premium retail listing look
- realistic light/shadow
- no text, no watermark, no redesign

## Scene mapping examples
- chandelier -> dining room / foyer / kitchen island
- pendant light -> kitchen island / breakfast nook / hallway
- ceiling light -> bedroom / hallway / living room
- wall light -> bedside / corridor / bathroom vanity

## Quality gate
Reject images with:
- changed arm count or lamp count
- wrong metal finish
- duplicated or missing fixture parts
- surreal geometry
- messy background that hides the product
