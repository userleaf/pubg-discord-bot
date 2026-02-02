import os
import random
from PIL import Image, ImageFont, ImageDraw

# === CONFIG ===
SYMBOLS = ['🍒', '🍋', '🍇', '💎', '🔔'] 
OUTPUT_FOLDER = "slot_gifs"
# Tiny size for mobile friendliness
GIF_SIZE = (200, 70) 
FONT_SIZE = 40 

# Point to Windows Emoji Font
FONT_PATH = "C:/Windows/Fonts/seguiemj.ttf" 

try:
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
except:
    font = ImageFont.load_default()

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def create_frame(s1, s2, s3):
    img = Image.new('RGB', GIF_SIZE, color=(47, 49, 54))
    draw = ImageDraw.Draw(img)
    # Adjusted centering for 200x70
    draw.text((15, 10), s1, font=font, fill=(255, 255, 255), embedded_color=True)
    draw.text((80, 10), s2, font=font, fill=(255, 255, 255), embedded_color=True)
    draw.text((145, 10), s3, font=font, fill=(255, 255, 255), embedded_color=True)
    return img

print(f"🎬 Generating Fast GIFs + Static PNGs...")

for r1 in SYMBOLS:
    for r2 in SYMBOLS:
        for r3 in SYMBOLS:
            base_name = f"{OUTPUT_FOLDER}/{r1}_{r2}_{r3}"
            frames = []
            
            # 1. HYPER SPIN (Fast Flicker) - 50ms per frame
            # 20 frames = 1 second of chaos
            for _ in range(20):
                frames.append(create_frame(random.choice(SYMBOLS), random.choice(SYMBOLS), random.choice(SYMBOLS)))

            # 2. STOP REEL 1
            for _ in range(10): frames.append(create_frame(r1, random.choice(SYMBOLS), random.choice(SYMBOLS)))
            
            # 3. STOP REEL 2
            for _ in range(10): frames.append(create_frame(r1, r2, random.choice(SYMBOLS)))
                
            # 4. FINAL RESULT (Long Pause)
            final = create_frame(r1, r2, r3)
            # Add 30 copies = 1.5 seconds of "stillness" at the end
            for _ in range(45): frames.append(final)

            # SAVE GIF (Duration 50ms = Very Fast)
            frames[0].save(f"{base_name}.gif", save_all=True, append_images=frames[1:], optimize=True, duration=50, loop=0)
            
            # SAVE STATIC PNG (For the final result)
            final.save(f"{base_name}.png")

print("✅ Done! Upload 'slot_gifs' folder (It now has .gif AND .png files).")