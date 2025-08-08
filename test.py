#!/usr/bin/env python3
"""
Generate a karaoke video with fully customizable options.
Edit the CONFIG and CAPTION_CONFIG dictionaries below to change video, audio, background, and caption settings.
"""

import requests
import sys
import time

API_BASE_URL = "http://152.53.86.6:8000"

# === GENERAL VIDEO/AUDIO/BACKGROUND CONFIGURATION ===
CONFIG = {
    # Background image or video
    "background_url": "https://picsum.photos/1080/1920",  # Change to your image or video URL
    "media_type": "image",  # "image" or "video"
    "width": 1080,
    "height": 1920,

    # Audio (optional)
    "audio_id": None,  # Set to a file_id if you want to use a custom audio
    "kokoro_voice": "af_heart",  # TTS voice
    "kokoro_speed": 1.0,          # TTS speed
    "language": None,             # STT language code (e.g. 'en', 'fr', 'de')

    # Background effect
    "image_effect": "pan",  # "ken_burns" or "pan"
}

# === CAPTION/CAPTIONS ANIMATION & STYLING CONFIGURATION ===
CAPTION_CONFIG = {
    "caption_animation": "word",  # "word" for karaoke, "segment" for traditional
    "caption_config_line_count": 1,           # Number of lines per subtitle segment
    "caption_config_line_max_length": 25,     # Max characters per line
    "caption_config_font_size": 120,          # Font size
    "caption_config_font_name": "Happy Boy", # Font family
    "caption_config_font_transparency": 0.5,  # 50% transparent
    "caption_config_secondary_font_transparency": 0.0,  # For spoken text (default: fully visible)
    "caption_config_stroke_transparency": 0.0,    # 0.0 = opaque stroke, 1.0 = fully transparent
    "caption_config_font_bold": True,         # Bold font
    "caption_config_font_italic": False,       # Italic font
    "caption_config_font_color": "#FFFFFF",  # Font color (hex)
    "caption_config_subtitle_position": "center", # "top", "center", "bottom"
    "caption_config_shadow_color": "#000000",      # Shadow color (hex)
    "caption_config_shadow_transparency": 1.0,      # Shadow transparency (0.0-1.0)
    "caption_config_shadow_blur": 1,                # Shadow blur
    "caption_config_stroke_color": "#000000",      # Stroke/outline color (hex)
    "caption_config_stroke_size": 1,                # Stroke/outline size
}

KARAOKE_TEXT = "i will never let you go, what will you do? Lets see how this works, i will never let you go, what will you do? / Lets see how this works"            # Change to your lyrics
WAIT_SECONDS = 10                                   # Wait time for video generation

def main():
    print("🎤 Karaoke Video Generation Script (Full Config)")
    print("=" * 60)

    # Step 1: Upload background image or video
    print("📸 Uploading background media...")
    upload_response = requests.post(
        f"{API_BASE_URL}/api/v1/media/storage",
        data={
            "url": CONFIG["background_url"],
            "media_type": CONFIG["media_type"]
        }
    )
    if upload_response.status_code != 200:
        print(f"❌ Failed to upload media: {upload_response.text}")
        sys.exit(1)
    background_id = upload_response.json()["file_id"]
    print(f"✅ Background media uploaded: {background_id}")

    # Step 2: Generate karaoke video
    print("\n🎵 Generating karaoke video...")
    payload = {
        "background_id": background_id,
        "text": KARAOKE_TEXT,
        "width": CONFIG["width"],
        "height": CONFIG["height"],
        "image_effect": CONFIG["image_effect"],
        "caption_animation": CAPTION_CONFIG["caption_animation"],
        # Optional audio and TTS/STT
        "audio_id": CONFIG["audio_id"],
        "kokoro_voice": CONFIG["kokoro_voice"],
        "kokoro_speed": CONFIG["kokoro_speed"],
        "language": CONFIG["language"],
        # Caption config
        "caption_config_line_count": CAPTION_CONFIG["caption_config_line_count"],
        "caption_config_line_max_length": CAPTION_CONFIG["caption_config_line_max_length"],
        "caption_config_font_size": CAPTION_CONFIG["caption_config_font_size"],
        "caption_config_font_name": CAPTION_CONFIG["caption_config_font_name"],
        "caption_config_font_bold": CAPTION_CONFIG["caption_config_font_bold"],
        "caption_config_font_italic": CAPTION_CONFIG["caption_config_font_italic"],
        "caption_config_font_color": CAPTION_CONFIG["caption_config_font_color"],
        "caption_config_subtitle_position": CAPTION_CONFIG["caption_config_subtitle_position"],
        "caption_config_shadow_color": CAPTION_CONFIG["caption_config_shadow_color"],
        "caption_config_shadow_transparency": CAPTION_CONFIG["caption_config_shadow_transparency"],
        "caption_config_shadow_blur": CAPTION_CONFIG["caption_config_shadow_blur"],
        "caption_config_stroke_color": CAPTION_CONFIG["caption_config_stroke_color"],
        "caption_config_stroke_size": CAPTION_CONFIG["caption_config_stroke_size"],
    }
    # Remove None values (for optional params)
    payload = {k: v for k, v in payload.items() if v is not None}
    karaoke_response = requests.post(
        f"{API_BASE_URL}/api/v1/media/video-tools/generate/tts-captioned-video",
        data=payload
    )
    if karaoke_response.status_code != 200:
        print(f"❌ Karaoke generation failed: {karaoke_response.text}")
        sys.exit(1)
    karaoke_video_id = karaoke_response.json()["file_id"]
    print(f"✅ Karaoke video generation started: {karaoke_video_id}")

    # Step 3: Wait for video generation
    print(f"\n⏳ Waiting {WAIT_SECONDS} seconds for video generation...")
    time.sleep(WAIT_SECONDS)

    # Step 4: Output download link
    print("\n🎉 Karaoke video generated!")
    print("=" * 60)
    print(f"📋 Video IDs:")
    print(f"   • Background Media: {background_id}")
    print(f"   • Karaoke Video: {karaoke_video_id}")
    print(f"\n📥 Download Link:")
    print(f"   • Karaoke Video: {API_BASE_URL}/api/v1/media/storage/{karaoke_video_id}")
    print("\n⏱️  Note: Allow time for background processing before downloading!")

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed! Make sure server is running at:", API_BASE_URL)
    except Exception as e:
        print(f"❌ Error: {e}")