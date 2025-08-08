import re
import time
import warnings
from typing import List
from kokoro import KPipeline
import numpy as np
import soundfile as sf
from loguru import logger
import torchaudio as ta
from chatterbox.tts import ChatterboxTTS
from video.config import device

# Suppress PyTorch warnings
warnings.filterwarnings("ignore")

LANGUAGE_CONFIG = {
    "en-us": {
        "lang_code": "a",
        "international": False,
        "iso639_1": "en",
    },
    "en": {
        "lang_code": "a",
        "international": False,
        "iso639_1": "en",
    },
    "en-gb": {
        "lang_code": "b",
        "international": False,
        "iso639_1": "en",
    },
    "es": {"lang_code": "e", "international": True, "iso639_1": "es"},
    "fr": {"lang_code": "f", "international": True, "iso639_1": "fr"},
    "hi": {"lang_code": "h", "international": True, "iso639_1": "hi"},
    "it": {"lang_code": "i", "international": True, "iso639_1": "it"},
    "pt": {"lang_code": "p", "international": True, "iso639_1": "pt"},
    "ja": {"lang_code": "j", "international": True, "iso639_1": "ja"},
    "zh": {"lang_code": "z", "international": True, "iso639_1": "zh"},
}
LANGUAGE_VOICE_CONFIG = {
    "en-us": [
        "af_heart",
        "af_alloy",
        "af_aoede",
        "af_bella",
        "af_jessica",
        "af_kore",
        "af_nicole",
        "af_nova",
        "af_river",
        "af_sarah",
        "af_sky",
        "am_adam",
        "am_echo",
        "am_eric",
        "am_fenrir",
        "am_liam",
        "am_michael",
        "am_onyx",
        "am_puck",
        "am_santa",
    ],
    "en-gb": [
        "bf_alice",
        "bf_emma",
        "bf_isabella",
        "bf_lily",
        "bm_daniel",
        "bm_fable",
        "bm_george",
        "bm_lewis",
    ],
    "zh": [
        "zf_xiaobei",
        "zf_xiaoni",
        "zf_xiaoxiao",
        "zf_xiaoyi",
        "zm_yunjian",
        "zm_yunxi",
        "zm_yunxia",
        "zm_yunyang",
    ],
    "es": ["ef_dora", "em_alex", "em_santa"],
    "fr": ["ff_siwis"],
    "it": ["if_sara", "im_nicola"],
    "pt": ["pf_dora", "pm_alex", "pm_santa"],
    "hi": ["hf_alpha", "hf_beta", "hm_omega", "hm_psi"],
}

LANGUAGE_VOICE_MAP = {}
for lang, voices in LANGUAGE_VOICE_CONFIG.items():
    for voice in voices:
        if lang in LANGUAGE_CONFIG:
            LANGUAGE_VOICE_MAP[voice] = LANGUAGE_CONFIG[lang]
        else:
            print(f"Warning: Language {lang} not found in LANGUAGE_CONFIG")


class TTS:
    def break_text_into_sentences(self, text, lang_code) -> List[str]:
        """
        Advanced sentence splitting with better handling of abbreviations and edge cases.
        """
        if not text or not text.strip():
            return []

        # Language-specific sentence boundary patterns
        patterns = {
            "a": r"(?<=[.!?])\s+(?=[A-Z_])",  # English
            "e": r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑÜ¿¡_])",  # Spanish - allow inverted punctuation after boundaries
            "f": r"(?<=[.!?])\s+(?=[A-ZÁÀÂÄÇÉÈÊËÏÎÔÖÙÛÜŸ_])",  # French
            "h": r"(?<=[।!?])\s+",  # Hindi: Split after devanagari danda
            "i": r"(?<=[.!?])\s+(?=[A-ZÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞß_])",  # Italian
            "p": r"(?<=[.!?])\s+(?=[A-ZÀÁÂÃÄÅÇÈÉÊËÌÍÎÏÑÒÓÔÕÖÙÚÛÜÝ_])",  # Portuguese
            "z": r"(?<=[。！？])",  # Chinese: Split after Chinese punctuation
        }

        # Common abbreviations that shouldn't trigger sentence breaks
        abbreviations = {
            "a": {
                "Mr.",
                "Mrs.",
                "Ms.",
                "Dr.",
                "Prof.",
                "Sr.",
                "Jr.",
                "Inc.",
                "Corp.",
                "Ltd.",
                "Co.",
                "etc.",
                "vs.",
                "eg.",
                "i.e.",
                "e.g.",
                "Vol.",
                "Ch.",
                "Fig.",
                "No.",
                "p.",
                "pp.",
            },  # English
            "e": {
                "Sr.",
                "Sra.",
                "Dr.",
                "Dra.",
                "Prof.",
                "etc.",
                "pág.",
                "art.",
                "núm.",
                "cap.",
                "vol.",
            },  # Spanish
            "f": {
                "M.",
                "Mme.",
                "Dr.",
                "Prof.",
                "etc.",
                "art.",
                "p.",
                "vol.",
                "ch.",
                "fig.",
                "n°",
            },  # French
            "h": {"श्री", "श्रीमती", "डॉ.", "प्रो.", "etc.", "पृ.", "अध."},  # Hindi
            "i": {
                "Sig.",
                "Sig.ra",
                "Dr.",
                "Prof.",
                "ecc.",
                "pag.",
                "art.",
                "n.",
                "vol.",
                "cap.",
                "fig.",
            },  # Italian
            "p": {
                "Sr.",
                "Sra.",
                "Dr.",
                "Dra.",
                "Prof.",
                "etc.",
                "pág.",
                "art.",
                "n.º",
                "vol.",
                "cap.",
            },  # Portuguese
            "z": {"先生", "女士", "博士", "教授", "等等", "第", "页", "章"},  # Chinese
        }

        abbrevs = abbreviations.get(lang_code, set())

        # Protect abbreviations by temporarily replacing them
        protected_text = text
        replacements = {}
        for i, abbrev in enumerate(abbrevs):
            placeholder = f"__ABBREV_{i}__"
            protected_text = protected_text.replace(abbrev, placeholder)
            replacements[placeholder] = abbrev

        # Apply the regex splitting
        pattern = patterns.get(lang_code, patterns["a"])
        sentences = re.split(pattern, protected_text.strip())

        # Restore abbreviations and clean up
        restored_sentences = []
        for sentence in sentences:
            for placeholder, original in replacements.items():
                sentence = sentence.replace(placeholder, original)
            sentence = sentence.strip()
            if sentence:
                restored_sentences.append(sentence)

        return restored_sentences if restored_sentences else [text.strip()]

    def kokoro_international(
        self, text: str, output_path: str, voice: str, lang_code: str, speed=1
    ) -> tuple[str, List[dict], float]:
        if not text or not text.strip():
            raise ValueError("Text cannot be empty or whitespace")
        lang_code = LANGUAGE_VOICE_MAP.get(voice, {}).get("lang_code")
        if not lang_code:
            raise ValueError(f"Voice '{voice}' not found in LANGUAGE_VOICE_MAP")
        start = time.time()
        context_logger = logger.bind(
            voice=voice,
            speed=speed,
            text_length=len(text),
        )
        context_logger.debug("Starting TTS generation (international) with kokoro")
        sentences = self.break_text_into_sentences(text, lang_code)
        context_logger.debug(
            "Text split into sentences",
            sentences=sentences,
            num_sentences=len(sentences),
        )

        # generate the audio for each sentence
        audio_data = []
        captions = []
        full_audio_length = 0
        pipeline = KPipeline(lang_code=lang_code, repo_id="hexgrad/Kokoro-82M", device=device)
        for sentence in sentences:
            context_logger.debug(
                "Processing sentence",
                sentence=sentence,
                voice=voice,
                speed=speed,
            )
            generator = pipeline(sentence, voice=voice, speed=speed)

            for i, result in enumerate(generator):
                context_logger.debug(
                    "Generated audio for sentence",
                )
                data = result.audio
                audio_length = len(data) / 24000
                audio_data.append(data)
                # since there are no tokens, we can just use the sentence as the text
                captions.append(
                    {
                        "text": sentence,
                        "start_ts": full_audio_length,
                        "end_ts": full_audio_length + audio_length,
                    }
                )
                full_audio_length += audio_length

        context_logger = context_logger.bind(
            execution_time=time.time() - start,
            audio_length=full_audio_length,
            speedup=full_audio_length / (time.time() - start),
        )
        context_logger.debug(
            "TTS generation (international) completed with kokoro",
        )

        audio_data = np.concatenate(audio_data)
        audio_data = np.column_stack((audio_data, audio_data))
        sf.write(output_path, audio_data, 24000, format="WAV")
        return captions, full_audio_length

    def kokoro_english(
        self, text: str, output_path: str, voice="af_heart", speed=1
    ) -> tuple[str, List[dict], float]:
        if not text or not text.strip():
            raise ValueError("Text cannot be empty or whitespace")
        lang_code = LANGUAGE_VOICE_MAP.get(voice, {}).get("lang_code")
        if not lang_code:
            raise ValueError(f"Voice '{voice}' not found in LANGUAGE_VOICE_MAP")
        if lang_code != "a":
            raise NotImplementedError(
                f"TTS for language code '{lang_code}' is not implemented."
            )
        start = time.time()

        context_logger = logger.bind(
            voice=voice,
            speed=speed,
            text_length=len(text),
            device=device.type,
        )

        context_logger.debug("Starting TTS generation with kokoro")
        if not text or not text.strip():
            raise ValueError("Text cannot be empty or whitespace")
        pipeline = KPipeline(lang_code=lang_code, repo_id="hexgrad/Kokoro-82M", device=device.type)

        generator = pipeline(text, voice=voice, speed=speed)

        captions = []
        audio_data = []
        full_audio_length = 0
        for _, result in enumerate(generator):
            data = result.audio
            audio_length = len(data) / 24000
            audio_data.append(data)
            if result.tokens:
                tokens = result.tokens
                for t in tokens:
                    if t.start_ts is None or t.end_ts is None:
                        if captions:
                            captions[-1]["text"] += t.text
                            captions[-1]["end_ts"] = full_audio_length + audio_length
                        continue
                    try:
                        captions.append(
                            {
                                "text": t.text,
                                "start_ts": full_audio_length + t.start_ts,
                                "end_ts": full_audio_length + t.end_ts,
                            }
                        )
                    except Exception as e:
                        logger.error(
                            "Error processing token: {}, Error: {}",
                            t,
                            e,
                        )
                        raise ValueError(f"Error processing token: {t}, Error: {e}")
            full_audio_length += audio_length

        audio_data = np.concatenate(audio_data)
        audio_data = np.column_stack((audio_data, audio_data))
        sf.write(output_path, audio_data, 24000, format="WAV")
        context_logger.bind(
            execution_time=time.time() - start,
            audio_length=full_audio_length,
            speedup=full_audio_length / (time.time() - start),
            youtube_channel="https://www.youtube.com/@aiagentsaz"
        ).debug(
            "TTS generation completed with kokoro",
        )
        return captions, full_audio_length

    def kokoro(
        self, text: str, output_path: str, voice="af_heart", speed=1
    ) -> tuple[str, List[dict], float]:
        if not text or not text.strip():
            raise ValueError("Text cannot be empty or whitespace")
        lang_code = LANGUAGE_VOICE_MAP.get(voice, {}).get("lang_code")
        if not lang_code:
            raise ValueError(f"Voice '{voice}' not found in LANGUAGE_VOICE_MAP")
        if lang_code == "a":
            return self.kokoro_english(text, output_path, voice, speed)
        else:
            return self.kokoro_international(text, output_path, voice, lang_code, speed)

    def chatterbox(
        self,
        text: str,
        output_path: str,
        sample_audio_path: str = None,
        exaggeration=0.5,
        cfg_weight=0.5,
        temperature=0.8,
    ):
        start = time.time()
        context_logger = logger.bind(
            text_length=len(text),
            sample_audio_path=sample_audio_path,
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
            temperature=temperature,
            model="ChatterboxTTS",
            language="en-US",
            device=device.type,
        )
        context_logger.debug("starting TTS generation with Chatterbox")
        model = ChatterboxTTS.from_pretrained(device=device.type)

        if sample_audio_path:
            wav = model.generate(
                text,
                audio_prompt_path=sample_audio_path,
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
                temperature=temperature,
            )
        else:
            wav = model.generate(
                text,
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
                temperature=temperature,
            )

        if wav.dim() == 2 and wav.shape[0] == 1:
            wav = wav.repeat(2, 1)
        elif wav.dim() == 1:
            wav = wav.unsqueeze(0).repeat(2, 1)

        audio_length = wav.shape[1] / model.sr
        ta.save(output_path, wav, model.sr)
        context_logger.bind(
            execution_time=time.time() - start,
            audio_length=audio_length,
            speedup=audio_length / (time.time() - start),
            youtube_channel="https://www.youtube.com/@aiagentsaz"
        ).debug(
            "TTS generation with Chatterbox completed",
        )

    def valid_kokoro_voices(self, lang_code = None) -> List[str]:
        """
        Returns a list of valid voices for the given language code.
        If no language code is provided, returns all voices.
        """
        if lang_code:
            return LANGUAGE_VOICE_CONFIG.get(lang_code, [])
        else:
            return [
                voice for voices in LANGUAGE_VOICE_CONFIG.values() for voice in voices
            ]
