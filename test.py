#!/usr/bin/env python3
"""
Generate a karaoke video with fully customizable options.
Edit the CONFIG and CAPTION_CONFIG dictionaries below to change video, audio, background, and caption settings.
"""

import requests
import sys
import time
import os

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

def test_colorkey_overlay():
    """
    Predefined test for the colorkey overlay workflow using server assets.
    Steps:
      1) Upload main video by URL (no local files needed)
      2) List server overlays and select one (preferred name if available)
      3) Apply overlay with colorkey (color=black, similarity=0.15, blend=0.2)
      4) Poll status until ready
      5) Download final result to OUTPUT_FILE_PATH
    """

    # === PREDEFINED SERVER-BASED CONFIG ===
    MAIN_VIDEO_URL = "https://storage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"  # vivid sample video
    OUTPUT_FILE_PATH = "colorkey_test_output.mp4"
    OVERLAY_LOCAL_PATH = os.path.join("assets", "overlay", "old-overlay.mp4")

    COLORKEY = {
        "color": "black",
        "similarity": 0.45,  # more tolerant (key near-black)
        "blend": 0.12,       # softer edge
    }

    POLL_INTERVAL_SECONDS = 2.0
    MAX_WAIT_SECONDS = 300

    print("🎬 Colorkey Overlay Test")
    print("=" * 60)

    # Using server-based assets and remote URL for main video; no local files required

    # Step 1: Upload main video from URL
    print("📤 Uploading main video from URL...")
    upload_main_resp = requests.post(
        f"{API_BASE_URL}/api/v1/media/storage",
        data={"url": MAIN_VIDEO_URL, "media_type": "video"},
    )
    if upload_main_resp.status_code != 200:
        print(f"❌ Failed to upload main video: {upload_main_resp.text}")
        return
    main_id = upload_main_resp.json().get("file_id")
    print(f"✅ Main video uploaded: {main_id}")

    # Step 1b: Upload overlay file from local repo assets
    if not os.path.isfile(OVERLAY_LOCAL_PATH):
        print(f"❌ Overlay file missing: {OVERLAY_LOCAL_PATH}")
        return
    print("📤 Uploading overlay file from repo assets...")
    with open(OVERLAY_LOCAL_PATH, "rb") as f:
        overlay_upload = requests.post(
            f"{API_BASE_URL}/api/v1/media/storage",
            files={"file": (os.path.basename(OVERLAY_LOCAL_PATH), f, "application/octet-stream")},
            data={"media_type": "video"},
        )
    if overlay_upload.status_code != 200:
        print(f"❌ Failed to upload overlay: {overlay_upload.text}")
        return
    overlay_id = overlay_upload.json().get("file_id")
    print(f"✅ Overlay uploaded: {overlay_id}")

    # Step 2: Apply colorkey overlay via dedicated endpoint
    print("🎛️ Applying colorkey overlay (color=black) via dedicated endpoint...")
    ck_resp = requests.post(
        f"{API_BASE_URL}/api/v1/media/video-tools/add-colorkey-overlay",
        data={
            "video_id": main_id,
            "overlay_video_id": overlay_id,
            "color": COLORKEY["color"],
            "similarity": str(COLORKEY["similarity"]),
            "blend": str(COLORKEY["blend"]),
        },
    )
    if ck_resp.status_code != 200:
        print(f"❌ Colorkey overlay request failed: {ck_resp.text}")
        return
    result_id = ck_resp.json().get("file_id")
    print(f"✅ Colorkey job submitted: {result_id}")

    # Step 3: Poll status until ready
    print("⏳ Polling for completion...")
    start_time = time.time()
    status = "processing"
    while True:
        status_resp = requests.get(f"{API_BASE_URL}/api/v1/media/storage/{result_id}/status")
        if status_resp.status_code != 200:
            print(f"⚠️ Status check failed: {status_resp.text}")
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
        status = status_resp.json().get("status")
        print(f"   • status: {status}")
        if status == "ready":
            break
        if status == "not_found":
            print("❌ Job not found on server.")
            return
        if time.time() - start_time > MAX_WAIT_SECONDS:
            print("⏰ Timed out waiting for processing to complete.")
            return
        time.sleep(POLL_INTERVAL_SECONDS)

    # Step 4: Download final result
    print("📥 Downloading final composited video...")
    download_url = f"{API_BASE_URL}/api/v1/media/storage/{result_id}"
    out_dir = os.path.dirname(OUTPUT_FILE_PATH)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with requests.get(download_url, stream=True) as r:
        if r.status_code != 200:
            print(f"❌ Download failed: {r.text}")
            return
        with open(OUTPUT_FILE_PATH, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    print("🎉 Colorkey overlay complete!")
    print("=" * 60)
    print("📋 IDs:")
    print(f"   • Main Video:   {main_id}")
    print(f"   • Overlay ID:   {overlay_id}")
    print(f"   • Result Video: {result_id}")
    print("\n📥 Download Link:")
    print(f"   • {download_url}")
    print(f"💾 Saved to: {OUTPUT_FILE_PATH}")


if __name__ == "__main__":
    try:
        test_colorkey_overlay()
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed! Make sure server is running at:", API_BASE_URL)
    except Exception as e:
        print(f"❌ Error: {e}")