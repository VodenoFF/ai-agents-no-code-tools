import os
from fastapi import BackgroundTasks, Form, status, APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger
from video.storage import Storage
from youtube_transcript_api import YouTubeTranscriptApi

storage_path = os.getenv("STORAGE_PATH", os.path.join(os.path.abspath(os.getcwd()), "media"))

storage = Storage(
    storage_path=storage_path,
)

v1_utils_router = APIRouter()
ytt_api = YouTubeTranscriptApi()

@v1_utils_router.get("/youtube-transcript")
def get_youtube_transcript(
    video_id: str,
):
    """ 
    Get YouTube video transcript by video ID.
    """
    try:
        fetched_transcript = ytt_api.fetch(video_id)
        return {
            "video_id": video_id,
            "transcript": fetched_transcript
        }
    except Exception as e:
        logger.error(f"Error fetching transcript for video {video_id}: {e}")
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": f"Transcript for video {video_id} not found."},
        )

@v1_utils_router.post("/stitch-images")
def stitch_images(
    image_urls: str = Form(..., description="Comma-separated list of image URLs to stitch together"),
    max_width: int = Form(1920, description="Maximum width of the final stitched image"),
    max_height: int = Form(1080, description="Maximum height of the final stitched image"),
):
    """
    Stitch multiple images into one.
    """
    if not image_urls:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "No image URLs provided."}
        )
    
    image_urls = [url.strip() for url in image_urls.split(",") if url.strip()]
    
    from utils.image import stitch_images as stitch_images_util
    try:
        stitched_image = stitch_images_util(image_urls, max_width, max_height)
        
        # Convert PIL image to JPEG format in memory
        from io import BytesIO
        img_buffer = BytesIO()
        stitched_image.save(img_buffer, format='JPEG', quality=95)
        img_buffer.seek(0)
        
        return StreamingResponse(
            img_buffer,
            media_type="image/jpeg",
            headers={
                "Content-Disposition": f"attachment; filename=stitched.jpg"
            },
        )
    except Exception as e:
        logger.error(f"Error stitching images: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Failed to stitch images."}
        )

@v1_utils_router.post("/make-image-imperfect")
def image_unaize(
    background_tasks: BackgroundTasks,
    image_id: str = Form(..., description="ID of the image to unaize"),
    enhance_color: float = Form(None, description="Strength of the color enhancement (0-2). 0 means black and white, 1 means no change, 2 means full color enhancement"),
    enhance_contrast: float = Form(None, description="Strength of the contrast enhancement (0-2)"),
    noise_strength: int = Form(0, description="Strength of the noise to apply to the image (0-100)"),
):
    """
    Remove AI-generated artifacts from an image.
    """
    if not image_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "No image URL provided."}
        )
    
    image_path = storage.get_media_path(image_id)

    jpg_id, jpg_path = storage.create_media_filename_with_id(
        media_type="image", file_extension=".jpg"
    )
    tmp_file_id = storage.create_tmp_file(jpg_id)
    
    from utils.image import make_image_imperfect
    
    def bg_task():
        try:
            imperfect_image = make_image_imperfect(
                image_path,
                enhance_color=enhance_color,
                enhance_contrast=enhance_contrast,
                noise_strength=noise_strength
            )
            imperfect_image.save(jpg_path, format='JPEG', quality=95)
        except Exception as e:
            logger.error(f"Error making image imperfect: {e}")
        finally:
            storage.delete_media(tmp_file_id)
    
    background_tasks.add_task(bg_task)
    return {
        "file_id": jpg_id,
    }

@v1_utils_router.post("/convert/pcm/wav")
def convert_pcm_to_wav(
    background_tasks: BackgroundTasks,
    pcm_id: str = Form(..., description="ID of the PCM audio file to convert"),
    sample_rate: int = Form(24000, description="Sample rate of the PCM audio"),
    channels: int = Form(1, description="Number of audio channels (1 for mono, 2 for stereo)"),
    target_sample_rate: int = Form(44100, description="Target sample rate for the WAV audio"),
):
    """
    Convert PCM audio to WAV format.
    """
    if not pcm_id or storage.media_exists(pcm_id) is False:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "PCM audio file not found."}
        )
    
    from video.media import MediaUtils
    utils = MediaUtils()
    
    wav_id, wav_path = storage.create_media_filename_with_id(
        media_type="audio", file_extension=".wav"
    )
    tmp_file_id = storage.create_tmp_file(wav_id)
    
    def bg_task():
        try:
            utils.convert_pcm_to_wav(
                input_pcm_path=storage.get_media_path(pcm_id),
                output_wav_path=wav_path,
                sample_rate=sample_rate,
                channels=channels,
                target_sample_rate=target_sample_rate
            )
        except Exception as e:
            logger.error(f"Error converting PCM to WAV: {e}")
        finally:
            storage.delete_media(tmp_file_id)
    
    background_tasks.add_task(bg_task)
    
    return {
        "file_id": wav_id,
    }

