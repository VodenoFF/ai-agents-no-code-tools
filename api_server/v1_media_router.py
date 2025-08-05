from fastapi import Query, Request, status, APIRouter, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Literal, Optional
import os
from loguru import logger
import matplotlib.font_manager as fm

from video.tts import TTS
from video.tts_chatterbox import TTSChatterbox
from video.stt import STT
from video.storage import Storage
from video.caption import Caption
from video.media import MediaUtils
from video.builder import VideoBuilder
from utils.image import resize_image_cover

CHUNK_SIZE = 1024 * 1024 * 10  # 10MB chunks

def iterfile(path: str):
    with open(path, mode="rb") as file:
        while chunk := file.read(CHUNK_SIZE):
            yield chunk


v1_media_api_router = APIRouter()

storage_path = os.getenv("STORAGE_PATH", os.path.join(os.path.abspath(os.getcwd()), "media"))

storage = Storage(
    storage_path=storage_path,
)
stt = STT()
tts_manager = TTS()
tts_chatterbox = TTSChatterbox()

@v1_media_api_router.post("/audio-tools/transcribe")
def transcribe(
    audio_file: UploadFile = File(..., description="Audio file to transcribe"),
    language: Optional[str] = Form(None, description="Language code (optional)"),
):
    """
    Transcribe audio file to text.
    """
    logger.bind(language=language, filename=audio_file.filename).info(
        "Transcribing audio file"
    )
    captions, duration = stt.transcribe(audio_file.file, beam_size=5, language=language)
    transcription = "".join([cap["text"] for cap in captions])

    return {
        "transcription": transcription,
        "duration": duration,
    }

@v1_media_api_router.get("/audio-tools/tts/kokoro/voices")
def get_kokoro_voices():
    voices = tts_manager.valid_kokoro_voices()
    return {"voices": voices}


@v1_media_api_router.post("/audio-tools/tts/kokoro")
def generate_kokoro_tts(
    background_tasks: BackgroundTasks,
    text: str = Form(..., description="Text to convert to speech"),
    voice: Optional[str] = Form(None, description="Voice name for kokoro TTS"),
    speed: Optional[float] = Form(None, description="Speed for kokoro TTS"),
):
    """
    Generate audio from text using specified TTS engine.
    """
    if not voice:
        voice = "af_heart"
    voices = tts_manager.valid_kokoro_voices()
    if voice not in voices:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Invalid voice: {voice}. Valid voices: {voices}"},
        )
    audio_id, audio_path = storage.create_media_filename_with_id(
        media_type="audio", file_extension=".wav"
    )
    tmp_file_id = storage.create_tmp_file(audio_id)

    def bg_task():
        tts_manager.kokoro(
            text=text,
            output_path=audio_path,
            voice=voice,
            speed=speed if speed else 1.0,
        )
        storage.delete_media(tmp_file_id)

    # background_tasks.add_task(bg_task)
    logger.info(f"Adding background task for TTS generation with ID: {audio_id}")
    background_tasks.add_task(bg_task)
    logger.info(f"Background task added for TTS generation with ID: {audio_id}")

    return {"file_id": audio_id}


@v1_media_api_router.post("/audio-tools/tts/chatterbox")
def generate_chatterbox_tts(
    background_tasks: BackgroundTasks,
    text: str = Form(..., description="Text to convert to speech"),
    sample_audio_id: Optional[str] = Form(
        None, description="Sample audio ID for voice cloning"
    ),
    sample_audio_file: Optional[UploadFile] = File(
        None, description="Sample audio file for voice cloning"
    ),
    exaggeration: Optional[float] = Form(
        0.5, description="Exaggeration factor for voice cloning, default: 0.5"
    ),
    cfg_weight: Optional[float] = Form(0.5, description="CFG weight for voice cloning, default: 0.5"),
    temperature: Optional[float] = Form(
        0.8, description="Temperature for voice cloning (default: 0.8)"
    ),
    chunk_chars: Optional[int] = Form(1024, description="Max characters per chunk (default: 1024)"),
    chunk_silence_ms: Optional[int] = Form(
        350, description="Silence duration between chunks in milliseconds (default: 350)"
    )
):
    """
    Generate audio from text using Chatterbox TTS.
    """
    audio_id, audio_path = storage.create_media_filename_with_id(
        media_type="audio", file_extension=".wav"
    )

    sample_audio_path = None
    if sample_audio_file:
        if not sample_audio_file.filename.endswith(".wav"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "Sample audio file must be a .wav file."},
            )
        sample_audio_id = storage.upload_media(
            media_type="tmp",
            media_data=sample_audio_file.file.read(),
            file_extension=".wav",
        )
        sample_audio_path = storage.get_media_path(sample_audio_id)
    elif sample_audio_id:
        if not storage.media_exists(sample_audio_id):
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": f"Sample audio with ID {sample_audio_id} not found."},
            )
        sample_audio_path = storage.get_media_path(sample_audio_id)

    tmp_file_id = storage.create_tmp_file(audio_id)

    def bg_task():
        try:
            tts_chatterbox.chatterbox(
                text=text,
                output_path=audio_path,
                sample_audio_path=sample_audio_path,
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
                temperature=temperature,
                chunk_chars=chunk_chars,
                chunk_silence_ms=chunk_silence_ms,
            )
        except Exception as e:
            logger.error(f"Error in Chatterbox TTS: {e}")
        finally:
            storage.delete_media(tmp_file_id)

    # background_tasks.add_task(bg_task)
    logger.info(f"Adding background task for Chatterbox TTS generation with ID: {audio_id}")
    background_tasks.add_task(bg_task)
    logger.info(f"Background task added for Chatterbox TTS generation with ID: {audio_id}")

    return {"file_id": audio_id}


@v1_media_api_router.post("/storage")
def upload_file(
    file: Optional[UploadFile] = File(None, description="File to upload"),
    url: Optional[str] = Form(None, description="URL of the file to upload (optional)"),
    media_type: Literal["image", "video", "audio"] = Form(
        ..., description="Type of media being uploaded"
    ),
):
    """
    Upload a file and return its ID.
    """
    if media_type not in ["image", "video", "audio"]:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Invalid media type: {media_type}"},
        )
    if file:
        file_id = storage.upload_media(
            media_type=media_type,
            media_data=file.file.read(),
            file_extension=os.path.splitext(file.filename)[1],
        )

        return {"file_id": file_id}
    elif url:
        if not storage.is_valid_url(url):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": f"Invalid URL: {url}"},
            )
        file_id = storage.upload_media_from_url(media_type=media_type, url=url)
        return {"file_id": file_id}


@v1_media_api_router.get("/storage/{file_id}")
def download_file(file_id: str):
    """
    Download a file by its ID.
    """
    if not storage.media_exists(file_id):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": f"File with ID {file_id} not found."},
        )

    file_path = storage.get_media_path(file_id)
    return StreamingResponse(
        iterfile(file_path),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename={os.path.basename(file_path)}"
        },
    )


@v1_media_api_router.delete("/storage/{file_id}")
def delete_file(file_id: str):
    """
    Delete a file by its
    """
    if storage.media_exists(file_id):
        storage.delete_media(file_id)
    return {"status": "success"}


@v1_media_api_router.get("/storage/{file_id}/status")
def file_status(file_id: str):
    """
    Check the status of a file by its ID.
    """
    tmp_id = storage.create_tmp_file_id(file_id)
    if storage.media_exists(tmp_id):
        return {"status": "processing"}
    elif storage.media_exists(file_id):
        return {"status": "ready"}
    return {"status": "not_found"}


@v1_media_api_router.post("/video-tools/merge")
def merge_videos(
    background_tasks: BackgroundTasks,
    video_ids: str = Form(..., description="List of video IDs to merge"),
    background_music_id: Optional[str] = Form(
        None, description="Background music ID (optional)"
    ),
    background_music_volume: Optional[float] = Form(
        0.5, description="Volume for background music (0.0 to 1.0)"
    ),
):
    """
    Merge multiple videos into one.
    """
    video_ids = video_ids.split(",") if video_ids else []
    if not video_ids:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "At least one video ID is required."},
        )

    merged_video_id, merged_video_path = storage.create_media_filename_with_id(
        media_type="video", file_extension=".mp4"
    )

    video_paths = []
    for video_id in video_ids:
        if not storage.media_exists(video_id):
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": f"Video with ID {video_id} not found."},
            )
        video_paths.append(storage.get_media_path(video_id))

    if background_music_id and not storage.media_exists(background_music_id):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": f"Background music with ID {background_music_id} not found."
            },
        )
    background_music_path = (
        storage.get_media_path(background_music_id) if background_music_id else None
    )

    utils = MediaUtils()

    temp_file_id = storage.create_tmp_file(merged_video_id)

    def bg_task():
        utils.merge_videos(
            video_paths=video_paths,
            output_path=merged_video_path,
            background_music_path=background_music_path,
            background_music_volume=background_music_volume,
        )
        storage.delete_media(temp_file_id)

    logger.info(f"Adding background task for video merge with ID: {merged_video_id}")
    background_tasks.add_task(bg_task)
    logger.info(f"Background task added for video merge with ID: {merged_video_id}")

    return {"file_id": merged_video_id}


@v1_media_api_router.get('/fonts')
def list_fonts():
    fonts = set()
    for fname in fm.findSystemFonts(fontpaths=None, fontext='ttf'):
        try:
            prop = fm.FontProperties(fname=fname)
            name = prop.get_name()
            fonts.add(name)
        except RuntimeError:
            continue
    return {"fonts": sorted(fonts)}

@v1_media_api_router.post("/video-tools/generate/tts-captioned-video")
def generate_captioned_video(
    background_tasks: BackgroundTasks,
    background_id: str = Form(..., description="Background image ID"),
    text: Optional[str] = Form(None, description="Text to generate video from"),
    width: Optional[int] = Form(1080, description="Width of the video (default: 1080)"),
    height: Optional[int] = Form(
        1920, description="Height of the video (default: 1920)"
    ),
    audio_id: Optional[str] = Form(
        None, description="Audio ID for the video (optional)"
    ),
    kokoro_voice: Optional[str] = Form(
        "af_heart", description="Voice for kokoro TTS (default: af_heart)"
    ),
    kokoro_speed: Optional[float] = Form(
        1.0, description="Speed for kokoro TTS (default: 1.0)"
    ),
    language: Optional[str] = Form(
        None, description="Language code for STT (optional, e.g. 'en', 'fr', 'de'), defaults to None (auto-detect language if audio_id is provided)"
    ),
    
    image_effect: Optional[str] = Form("ken_burns", description="Effect to apply to the background image, options: ken_burns, pan (default: 'ken_burns')"),

    # New parameter for animation style
    caption_animation: Optional[Literal["segment", "word"]] = Form("segment", description="Animation style for captions (default: 'segment', use 'word' for karaoke-style)"),

    # Flattened subtitle configuration options
    caption_config_line_count: Optional[int] = Form(1, description="Number of lines per subtitle segment (default: 1)", ge=1, le=5),
    caption_config_line_max_length: Optional[int] = Form(25, description="Maximum characters per line (default: 25)", ge=1, le=200),
    caption_config_font_size: Optional[int] = Form(120, description="Font size for subtitles (default: 120)", ge=8, le=200),
    caption_config_font_name: Optional[str] = Form("EB Garamond", description="Font family name (default: 'EB Garamond', see the available fonts form the /fonts endpoint)"),
    caption_config_font_bold: Optional[bool] = Form(False, description="Whether to use bold font (default: False)"),
    caption_config_font_italic: Optional[bool] = Form(True, description="Whether to use italic font (default: True)"),
    caption_config_font_color: Optional[str] = Form("#fff", description="Font color in hex format (default: '#fff')"),
    caption_config_subtitle_position: Optional[Literal["top", "center", "bottom"]] = Form("center", description="Vertical position of subtitles (default: 'center')"),
    caption_config_shadow_color: Optional[str] = Form("#000", description="Shadow color in hex format (default: '#000')"),
    caption_config_shadow_transparency: Optional[float] = Form(0.7, description="Shadow transparency from 0.0 to 1.0 (default: 0.7)", ge=0.0, le=1.0),
    caption_config_shadow_blur: Optional[int] = Form(15, description="Shadow blur radius (default: 15)", ge=0, le=20),
    caption_config_stroke_color: Optional[str] = Form(None, description="Stroke/outline color in hex format (default: None)"),
    caption_config_stroke_size: Optional[int] = Form(0, description="Stroke/outline size (default: 0)", ge=0, le=10),
):
    """
    Generate a captioned video from text and background image.

    """
    # Build subtitle options from individual parameters
    parsed_subtitle_options = {}
    
    # Only include non-None values
    if caption_config_line_count is not None:
        parsed_subtitle_options['lines'] = caption_config_line_count
    if caption_config_line_max_length is not None:
        parsed_subtitle_options['max_length'] = caption_config_line_max_length
    if caption_config_font_size is not None:
        parsed_subtitle_options['font_size'] = caption_config_font_size
    if caption_config_font_name is not None:
        parsed_subtitle_options['font_name'] = caption_config_font_name
    if caption_config_font_bold is not None:
        parsed_subtitle_options['font_bold'] = caption_config_font_bold
    if caption_config_font_italic is not None:
        parsed_subtitle_options['font_italic'] = caption_config_font_italic
    if caption_config_font_color is not None:
        parsed_subtitle_options['font_color'] = caption_config_font_color
    if caption_config_subtitle_position is not None:
        parsed_subtitle_options['subtitle_position'] = caption_config_subtitle_position
    if caption_config_shadow_color is not None:
        parsed_subtitle_options['shadow_color'] = caption_config_shadow_color
    if caption_config_shadow_transparency is not None:
        parsed_subtitle_options['shadow_transparency'] = caption_config_shadow_transparency
    if caption_config_shadow_blur is not None:
        parsed_subtitle_options['shadow_blur'] = caption_config_shadow_blur
    if caption_config_stroke_color is not None:
        parsed_subtitle_options['stroke_color'] = caption_config_stroke_color
    if caption_config_stroke_size is not None:
        parsed_subtitle_options['stroke_size'] = caption_config_stroke_size
    
    if audio_id and not storage.media_exists(audio_id):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Audio with ID {audio_id} not found."},
        )
    if not audio_id and kokoro_voice not in tts_manager.valid_kokoro_voices():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Invalid voice: {kokoro_voice}."},
        )
    media_type = storage.get_media_type(background_id)
    if media_type not in ["image"]:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Invalid media type: {media_type}"},
        )
    if not storage.media_exists(background_id):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": f"Background image with ID {background_id} not found."},
        )

    output_id, output_path = storage.create_media_filename_with_id(
        media_type="video", file_extension=".mp4"
    )
    dimensions = (width, height)
    builder = VideoBuilder(
        dimensions=dimensions,
    )
    builder.set_media_utils(MediaUtils())

    tmp_file_id = storage.create_tmp_file(output_id)

    def bg_task(
        tmp_file_id: str = tmp_file_id,
    ):
        tmp_file_ids = [tmp_file_id]

        # set audio, generate captions
        captions = None
        tts_audio_id = audio_id
        from video.tts import LANGUAGE_VOICE_MAP
        lang_config = LANGUAGE_VOICE_MAP.get(kokoro_voice, {})
        international = lang_config.get("international", False)
        
        if tts_audio_id:
            audio_path = storage.get_media_path(tts_audio_id)
            captions, _ = stt.transcribe(audio_path=audio_path, language=language)
            builder.set_audio(audio_path)
        # generate TTS and set audio
        else:
            tts_audio_id, audio_path = storage.create_media_filename_with_id(
                media_type="audio", file_extension=".wav"
            )
            tmp_file_ids.append(tts_audio_id)
            captions, _ = tts_manager.kokoro(
                text=text,
                output_path=audio_path,
                voice=kokoro_voice,
                speed=kokoro_speed,
            )
            if international:
                # use whisper to create captions
                iso_lang_code = lang_config.get("iso639_1")
                captions, _ = stt.transcribe(audio_path=audio_path, language=iso_lang_code)
            
            builder.set_audio(audio_path)

        # create subtitle
        captionsManager = Caption()
        subtitle_id, subtitle_path = storage.create_media_filename_with_id(
            media_type="tmp", file_extension=".ass"
        )
        tmp_file_ids.append(subtitle_id)
        
        # --- MODIFICATION START ---
        # Decide which data to pass to create_subtitle based on animation style
        captions_data_for_renderer = captions
        if caption_animation == "segment":
            # For segment animation, create segments first
            if international:
                captions_data_for_renderer = captionsManager.create_subtitle_segments_international(
                    captions=captions,
                    lines=parsed_subtitle_options.get('lines', 1),
                    max_length=parsed_subtitle_options.get('max_length', 1),
                )
            else:
                captions_data_for_renderer = captionsManager.create_subtitle_segments_english(
                    captions=captions,
                    lines=parsed_subtitle_options.get('lines', 1),
                    max_length=parsed_subtitle_options.get('max_length', 1),
                )
        # For "word" animation, we pass the raw `captions` list directly

        captionsManager.create_subtitle(
            segments=captions_data_for_renderer, # Use the decided data
            output_path=subtitle_path,
            dimensions=dimensions,
            animation_style=caption_animation, # Pass the new style parameter

            # Pass other options
            font_size=parsed_subtitle_options.get('font_size', 120),
            shadow_blur=parsed_subtitle_options.get('shadow_blur', 10),
            stroke_size=parsed_subtitle_options.get('stroke_size', 5),
            shadow_color=parsed_subtitle_options.get('shadow_color', "#000"),
            stroke_color=parsed_subtitle_options.get('stroke_color', "#000"),
            font_name=parsed_subtitle_options.get('font_name', "Arial"),
            font_bold=parsed_subtitle_options.get('font_bold', True),
            font_italic=parsed_subtitle_options.get('font_italic', False),
            subtitle_position=parsed_subtitle_options.get('subtitle_position', "top"),
            font_color=parsed_subtitle_options.get('font_color', "#fff"),
            shadow_transparency=parsed_subtitle_options.get('shadow_transparency', 0.4),
            max_length=parsed_subtitle_options.get('max_length', 25),
            lines=parsed_subtitle_options.get('lines', 1)
        )
        # --- MODIFICATION END ---
        builder.set_captions(
            file_path=subtitle_path,
        )

        # resize background image if needed
        background_path = storage.get_media_path(background_id)
        utils = MediaUtils()
        info = utils.get_video_info(background_path)
        if info.get("width", 0) != width or info.get("height", 0) != height:
            logger.bind(
                image_width=info.get("width", 0),
                image_height=info.get("height", 0),
                target_width=width,
                target_height=height,
            ).debug(
                "Resizing background image to fit video dimensions"
            )
            _, resized_background_path = storage.create_media_filename_with_id(
                media_type="image", file_extension=".jpg"
            )   
            resize_image_cover(
                image_path=background_path,
                output_path=resized_background_path,
                target_width=width,
                target_height=height,
            )
            background_path = resized_background_path

        builder.set_background_image(
            background_path,
            effect_config={
                "effect": image_effect,
            }
        )

        builder.set_output_path(output_path)

        builder.execute()

        for tmp_file_id in tmp_file_ids:
            if storage.media_exists(tmp_file_id):
                storage.delete_media(tmp_file_id)

    logger.info(f"Adding background task for captioned video generation with ID: {output_id}")
    background_tasks.add_task(bg_task, tmp_file_id=tmp_file_id)
    logger.info(f"Background task added for captioned video generation with ID: {output_id}")

    return {
        "file_id": output_id,
    }

# https://ffmpeg.org/ffmpeg-filters.html#colorkey
@v1_media_api_router.post("/video-tools/add-colorkey-overlay")
def add_colorkey_overlay(
    background_tasks: BackgroundTasks,
    video_id: str = Form(..., description="Video ID to overlay"),
    overlay_video_id: str = Form(..., description="Overlay image ID"),
    color: Optional[str] =  Form(
        "black", description="Set the color for which alpha will be set to 0 (full transparency). Use 'black' for vintage dust overlays or hex code (e.g. '#000000')"
    ),
    similarity: Optional[float] = Form(
        0.15, description="Set the radius from the key color within which other colors also have full transparency (Default: 0.15)"
    ),
    blend: Optional[float] = Form(
        0.2, description="Set how the alpha value for pixels that fall outside the similarity radius is computed (default: 0.2)"
    ),
):
    """
    Overlay a video on a video with the specified colorkey and intensity
    """
    
    if not storage.media_exists(video_id):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": f"Video with ID {video_id} not found."},
        )
    if not storage.media_exists(overlay_video_id):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": f"Overlay video with ID {overlay_video_id} not found."},
        )
    
    video_path = storage.get_media_path(video_id)
    overlay_video_path = storage.get_media_path(overlay_video_id)
    
    output_id, output_path = storage.create_media_filename_with_id(
        media_type="video", file_extension=".mp4"
    )
    
    tmp_file_id = storage.create_tmp_file(output_id)
    
    def bg_task():
        utils = MediaUtils()
        utils.colorkey_overlay(
            input_video_path=video_path,
            overlay_video_path=overlay_video_path,
            output_video_path=output_path,
            color=color,
            similarity=similarity,
            blend=blend,
        )
        storage.delete_media(tmp_file_id)
    
    logger.info(f"Adding background task for colorkey overlay with ID: {output_id}")
    background_tasks.add_task(bg_task)
    logger.info(f"Background task added for colorkey overlay with ID: {output_id}")
    
    return {
        "file_id": output_id,
    }

@v1_media_api_router.post("/video-tools/apply-vintage-filter")
def apply_vintage_filter(
    background_tasks: BackgroundTasks,
    video_id: str = Form(..., description="The ID of the video to apply the filter to"),
    grain_strength: Optional[int] = Form(8, description="Strength of the film grain (0-50, default: 8)"),
    vignette_intensity: Optional[float] = Form(0.1, description="Intensity of the vignette effect (0.0-1.0, default: 0.1)"),
):
    """
    Apply a vintage film grain and vignette filter to a video.
    """
    if not storage.media_exists(video_id):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": f"Video with ID {video_id} not found."},
        )

    video_path = storage.get_media_path(video_id)
    output_id, output_path = storage.create_media_filename_with_id(
        media_type="video", file_extension=".mp4"
    )
    tmp_file_id = storage.create_tmp_file(output_id)

    def bg_task():
        utils = MediaUtils()
        utils.apply_vintage_filter(
            input_path=video_path,
            output_path=output_path,
            grain_strength=grain_strength,
            vignette_intensity=vignette_intensity,
        )
        storage.delete_media(tmp_file_id)

    logger.info(f"Adding background task for vintage filter with ID: {output_id}")
    background_tasks.add_task(bg_task)
    logger.info(f"Background task added for vintage filter with ID: {output_id}")

    return {"file_id": output_id}

@v1_media_api_router.get("/video-tools/extract-frame/{video_id}")
def extract_frame(
    video_id: str,
    timestamp: Optional[float] = Query(1.0, description="Timestamp in seconds to extract frame from (default: 1.0)")
):
    """
    Extract a frame from a video at a specified timestamp.
    
    Args:
        video_id: Video ID to extract frame from
        timestamp: Optional timestamp in seconds to extract frame from (default: first frame)
    """
    if not storage.media_exists(video_id):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": f"Video with ID {video_id} not found."},
        )
    
    video_path = storage.get_media_path(video_id)
    
    _, output_path = storage.create_media_filename_with_id(
        media_type="image", file_extension=".jpg"
    )
    
    utils = MediaUtils()
    video_info = utils.get_video_info(video_path)
    if video_info.get("duration", 0) <= float(timestamp):
        timestamp = video_info.get("duration", 0) - 0.3

    success = utils.extract_frame(
        video_path=video_path,
        output_path=output_path,
        time_seconds=timestamp,
    )
    
    if not success:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Failed to extract frame from video."},
        )
    
    # Load file into memory
    with open(output_path, "rb") as file:
        file_data = file.read()
    
    # Remove the output file
    os.remove(output_path)
    
    # Create streaming response with appropriate headers
    from io import BytesIO
    return StreamingResponse(
        BytesIO(file_data),
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f"attachment; filename=frame_{video_id}_{timestamp or 'first'}.jpg"
        },
    )
    
# extract x number of frames from the video, equally spaced
@v1_media_api_router.post('/video-tools/extract-frames')
def extract_frame_from_url(
    url: str = Form(..., description="URL of the video to extract frame from"),
    amount: int = Form(5, description="Number of frames to extract from the video (default: 5)"),
    length_seconds: Optional[float] = Form(None, description="Length of the video in seconds (optional)"),
    stitch: Optional[bool] = Form(False, description="Whether to stitch the frames into a single image (default: False)")
):
    template_id, template_path = storage.create_media_template(
        media_type="image", file_extension=".jpg"
    )
    utils = MediaUtils()
    
    if not length_seconds:
        video_info = utils.get_video_info(url)
        length_seconds = video_info.get("duration", 0)
    
    utils.extract_frames(
        video_path=url,
        length_seconds=length_seconds,
        amount=amount,
        output_template=template_path,
    )
    
    image_ids = []
    for i in range(amount):
        padded_index = str(i + 1).zfill(2)
        
        image_id = template_id.replace("%02d", padded_index)
        image_ids.append(image_id)
    
    return {
        "message": f"Extracted {amount} frames from the video at {url}. The frames are saved in the template directory.",
        "template_id": template_id,
        "template_path": template_path,
        "image_ids": image_ids,
    }


@v1_media_api_router.get("/video-tools/info/{file_id}")
def get_video_info(file_id: str):
    """
    Get information about a video file.
    """
    if not storage.media_exists(file_id):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": f"Video with ID {file_id} not found."},
        )
    
    video_path = storage.get_media_path(file_id)
    
    utils = MediaUtils()
    info = utils.get_video_info(video_path)
    
    return info

@v1_media_api_router.get("/audio-tools/info/{file_id}")
def get_audio_info(file_id: str):
    """
    Get information about an audio file.
    """
    if not storage.media_exists(file_id):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": f"Audio with ID {file_id} not found."},
        )
    
    audio_path = storage.get_media_path(file_id)
    
    utils = MediaUtils()
    info = utils.get_audio_info(audio_path)
    
    return info
