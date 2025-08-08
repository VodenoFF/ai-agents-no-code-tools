import os
import time
import traceback
import warnings
from loguru import logger
import torchaudio as ta
from chatterbox.tts import ChatterboxTTS
from video.config import device
import nltk
import torch
from typing import List, Optional

# Suppress PyTorch warnings
warnings.filterwarnings("ignore")

class TTSChatterbox:
    def __init__(self):
        """Initialize ChatterboxTTS and ensure NLTK data is available."""
        self.ensure_nltk_data()
        logger.debug("ChatterboxTTS initialized")

    def ensure_nltk_data(self):
        """Ensure NLTK punkt tokenizer is available."""
        try:
            nltk.data.find('tokenizers/punkt')
            nltk.data.find('tokenizers/punkt_tab')
            logger.debug("NLTK punkt tokenizer found")
        except LookupError:
            logger.debug("Downloading NLTK punkt tokenizer...")
            try:
                nltk.download('punkt', quiet=True)
                nltk.download('punkt_tab', quiet=True)
                logger.debug("NLTK punkt tokenizer downloaded successfully")
            except Exception as e:
                logger.error(f"Failed to download NLTK punkt tokenizer: {e}")
                raise        

    def split_text_into_chunks(self, text: str, max_chars_per_chunk: int = 300) -> List[str]:
        """Split text into chunks respecting sentence boundaries without breaking sentences."""
        try:
            sentences = nltk.sent_tokenize(text)
            # Filter out empty sentences and strip whitespace
            sentences = [sentence.strip() for sentence in sentences if sentence.strip()]
            
            chunks = []
            current_chunk = ""
            
            for sentence in sentences:
                # If adding this sentence would exceed the limit, finalize current chunk
                if current_chunk and len(current_chunk) + len(sentence) + 1 > max_chars_per_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = sentence
                else:
                    # Add sentence to current chunk
                    if current_chunk:
                        current_chunk += " " + sentence
                    else:
                        current_chunk = sentence
            
            # Add the last chunk if it's not empty
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            
            logger.debug(f"Text split into {len(chunks)} chunks (max {max_chars_per_chunk} chars each, preserving sentences)")
            return chunks
        except Exception as e:
            logger.error(f"Error splitting text: {e}")
            # Fallback: return original text as single chunk
            return [text]

    def generate_audio_chunk(
        self,
        text_chunk: str,
        model: ChatterboxTTS,
        audio_prompt_path: Optional[str] = None,
        temperature: float = 0.8,
        cfg_weight: float = 0.5,
        exaggeration: float = 0.5
    ) -> Optional[torch.Tensor]:
        """Generate audio tensor for a single text chunk."""
        try:
            logger.debug(f"Generating audio for chunk: {text_chunk[:50]}...")

            
            # Check if audio prompt exists
            effective_prompt_path = None
            if audio_prompt_path and os.path.exists(audio_prompt_path):
                effective_prompt_path = audio_prompt_path
            elif audio_prompt_path:
                logger.warning(f"Audio prompt path not found: {audio_prompt_path}")
            
            # Generate audio
            wav_tensor = model.generate(
                text_chunk,
                audio_prompt_path=effective_prompt_path,
                temperature=temperature,
                cfg_weight=cfg_weight,
                exaggeration=exaggeration
            )
            
            # Ensure tensor is on CPU and properly shaped
            wav_tensor_cpu = wav_tensor.cpu().float()
            
            # Ensure tensor is 2D: [channels, samples]
            if wav_tensor_cpu.ndim == 1:
                wav_tensor_cpu = wav_tensor_cpu.unsqueeze(0)
            elif wav_tensor_cpu.ndim > 2:
                logger.warning(f"Unexpected tensor shape {wav_tensor_cpu.shape}, attempting to fix")
                wav_tensor_cpu = wav_tensor_cpu.squeeze()
                if wav_tensor_cpu.ndim == 1:
                    wav_tensor_cpu = wav_tensor_cpu.unsqueeze(0)
                elif wav_tensor_cpu.ndim != 2 or wav_tensor_cpu.shape[0] != 1:
                    logger.error(f"Could not reshape tensor {wav_tensor.shape} to [1, N]")
                    return None
            
            return wav_tensor_cpu
            
        except Exception as e:
            logger.error(f"Error generating audio chunk: {e}")
            logger.error(traceback.format_exc())
            return None

    def text_to_speech_pipeline(
        self,
        text: str,
        model: ChatterboxTTS,
        max_chars_per_chunk: int = 1024,
        inter_chunk_silence_ms: int = 350,
        audio_prompt_path: Optional[str] = None,
        temperature: float = 0.8,
        cfg_weight: float = 0.5,
        exaggeration: float = 0.5
    ) -> Optional[torch.Tensor]:
        """Convert text to speech with chunking support."""
        try:
            # Split text into chunks
            text_chunks = self.split_text_into_chunks(text, max_chars_per_chunk)
            
            if not text_chunks:
                logger.error("No text chunks to process")
                return None
            
            all_audio_tensors = []
            sample_rate = model.sr
            
            logger.debug(f"Processing {len(text_chunks)} chunks at {sample_rate} Hz")
            
            for i, chunk_text in enumerate(text_chunks):
                logger.debug(f"Processing chunk {i+1}/{len(text_chunks)}")
                
                chunk_tensor = self.generate_audio_chunk(
                    chunk_text,
                    model,
                    audio_prompt_path,
                    temperature,
                    cfg_weight,
                    exaggeration
                )
                
                if chunk_tensor is None:
                    logger.warning(f"Skipping chunk {i+1} due to generation error")
                    continue
                
                all_audio_tensors.append(chunk_tensor)
                
                # Add silence between chunks (except after the last chunk)
                if i < len(text_chunks) - 1 and inter_chunk_silence_ms > 0:
                    silence_samples = int(sample_rate * inter_chunk_silence_ms / 1000.0)
                    silence_tensor = torch.zeros(
                        (1, silence_samples),
                        dtype=chunk_tensor.dtype,
                        device=chunk_tensor.device
                    )
                    all_audio_tensors.append(silence_tensor)
            
            if not all_audio_tensors:
                logger.error("No audio tensors generated")
                return None
            
            # Concatenate all audio tensors
            logger.debug("Concatenating audio tensors...")
            final_audio_tensor = torch.cat(all_audio_tensors, dim=1)
            
            logger.debug(f"Final audio shape: {final_audio_tensor.shape}")
            return final_audio_tensor
            
        except Exception as e:
            logger.error(f"Error in text-to-speech pipeline: {e}")
            logger.error(traceback.format_exc())
            return None

    
    def chatterbox(
        self,
        text: str,
        output_path: str,
        sample_audio_path: str = None,
        exaggeration=0.5,
        cfg_weight=0.5,
        temperature=0.8,
        chunk_chars: int = 1024,
        chunk_silence_ms: int = 350,
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
            wav = self.text_to_speech_pipeline(
                text,
                model,
                audio_prompt_path=sample_audio_path,
                temperature=temperature,
                cfg_weight=cfg_weight,
                exaggeration=exaggeration,
                max_chars_per_chunk=chunk_chars,
                inter_chunk_silence_ms=chunk_silence_ms
            )
        else:
            wav = self.text_to_speech_pipeline(
                text,
                model,
                temperature=temperature,
                cfg_weight=cfg_weight,
                exaggeration=exaggeration,
                max_chars_per_chunk=chunk_chars,
                inter_chunk_silence_ms=chunk_silence_ms
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


