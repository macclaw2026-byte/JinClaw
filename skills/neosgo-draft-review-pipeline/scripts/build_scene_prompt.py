#!/usr/bin/env python3
import sys

title = sys.argv[1] if len(sys.argv) > 1 else 'lighting product'
kind = sys.argv[2] if len(sys.argv) > 2 else 'fixture'
scene = {
    'chandelier': 'a stylish dining room with warm natural light',
    'pendant': 'a premium kitchen island scene with tasteful decor',
    'ceiling': 'a clean, upscale living space with realistic ambient light',
    'wall': 'a refined hallway or bedside scene with soft light',
}.get(kind, 'a realistic upscale interior')

prompt = f'''Use the uploaded product image as the reference product. Generate one realistic ecommerce lifestyle scene image for this {title}. Keep the exact product structure, finish, proportions, and visible design details consistent with the reference. Place it in {scene}. Make it look like a premium retail listing image that increases purchase desire. The product must remain the clear hero object, centered and fully visible, with realistic shadows and lighting. No text, no watermark, no extra wrong fixtures, no deformed geometry, no redesign of the product.'''
print(prompt)
