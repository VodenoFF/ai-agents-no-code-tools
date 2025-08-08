from faster_whisper import WhisperModel
from loguru import logger
from video.config import device, whisper_model, whisper_compute_type


class STT:
    def __init__(self):
        self.model = WhisperModel(
            model_size_or_path=whisper_model, 
            compute_type=whisper_compute_type
        )

    def transcribe(self, audio_path, language = None, beam_size=5):
        logger.bind(
            device=device.type,
            model_size=whisper_model,
            compute_type=whisper_compute_type,
            audio_path=audio_path,
            language=language,
        ).debug(
            "transcribing audio with Whisper model",
        )
        segments, info = self.model.transcribe(
            audio_path,
            beam_size=beam_size,
            word_timestamps=True,
            language=language,
        )

        duration = info.duration
        captions = []
        for segment in segments:
            for word in segment.words:
                captions.append(
                    {
                        "text": word.word,
                        "start_ts": word.start,
                        "end_ts": word.end,
                    }
                )
        return captions, duration
