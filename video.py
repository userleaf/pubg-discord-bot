import os
import numpy as np
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
from PIL import Image, ImageDraw, ImageFont
from config import FACT_DEFINITIONS

def create_text_overlay(text_lines, duration=8, fontsize=50, color=(255, 255, 255), y_offset=0):
    width, height = 720, 1280 
    img = Image.new('RGBA', (width, height), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    try: font = ImageFont.truetype("arialbd.ttf", fontsize)
    except: font = ImageFont.load_default()
    
    total_text_height = len(text_lines) * (fontsize + 10)
    start_y = (height - total_text_height) / 2 + y_offset
    
    for i, line in enumerate(text_lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) / 2
        y = start_y + i * (fontsize + 10)
        # Outline
        for ox in range(-2, 3):
            for oy in range(-2, 3): draw.text((x+ox, y+oy), line, font=font, fill=(0,0,0,255))
        draw.text((x, y), line, font=font, fill=color)
    return ImageClip(np.array(img)).set_duration(duration)

def generate_video_report(summary_list, highlights, rank, map_name):
    if not os.path.exists("video.mp4"): return None
    base_video = VideoFileClip("video.mp4", audio=True).subclip(0, 32)
    overlays = []
    
    # 1. Rank
    rank_num = int(rank) if rank != '?' else 50
    if rank_num == 1: text1, col1 = ["WINNER WINNER", "CHICKEN DINNER!", "🏆 TOP 1 🏆"], (255, 215, 0)
    elif rank_num > 20: text1, col1 = ["TOTAL DISASTER", f"Rank #{rank}", "Uninstall maybe? 🗑️"], (255, 0, 0)
    else: text1, col1 = ["GOOD EFFORT", f"Rank #{rank}", "Next time..."], (255, 255, 255)
    overlays.append(create_text_overlay(text1, duration=8, fontsize=70, color=col1).set_start(0))
    
    # 2. Stats
    text2 = ["📊 SQUAD STATS 📊", ""]
    for s in summary_list: text2.extend([f"{s['name']}", f"{s['kills']} Kills | {s['dmg']} Dmg", ""])
    overlays.append(create_text_overlay(text2, duration=8, fontsize=45, y_offset=-50).set_start(8))

    # 3. Highlights
    mid = (len(highlights) + 1) // 2
    text3 = ["🏆 HIGHLIGHTS [1/2] 🏆", ""]
    for h in highlights[:mid]:
        meta = FACT_DEFINITIONS[h['type']]
        text3.extend([meta['title'], f"{h['player']} ({meta['format'].format(h['value'])})", ""])
    overlays.append(create_text_overlay(text3, duration=8, fontsize=40, color=(100, 255, 100)).set_start(16))

    text4 = ["🏆 HIGHLIGHTS [2/2] 🏆", ""]
    for h in highlights[mid:]:
        meta = FACT_DEFINITIONS[h['type']]
        text4.extend([meta['title'], f"{h['player']} ({meta['format'].format(h['value'])})", ""])
    overlays.append(create_text_overlay(text4, duration=8, fontsize=40, color=(100, 255, 100)).set_start(24))

    final_video = CompositeVideoClip([base_video] + overlays)
    output = "match_reel.mp4"
    final_video.write_videofile(output, fps=24, codec='libx264', bitrate="1500k", preset="ultrafast", audio_codec="aac")
    return output