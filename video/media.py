import subprocess
import json
import time
from loguru import logger


class MediaUtils:
    def __init__(self, ffmpeg_path="ffmpeg"):
        """
        Initializes the MediaUtils class.

        Args:
            ffmpeg_path: Path to the ffmpeg executable
        """
        self.ffmpeg_path = ffmpeg_path

    def merge_videos(
        self,
        video_paths: list,
        output_path: str,
        background_music_path: str = None,
        background_music_volume: float = 0.5,
    ) -> bool:
        """
        Merges multiple video files into one, optionally with background music.

        Args:
            video_paths: List of paths to video files to merge
            output_path: Path for the merged output video
            background_music: Optional path to background music file
            bg_music_volume: Volume level for background music (0.0 to 1.0, default 0.5)

        Returns:
            bool: True if successful, False otherwise
        """
        if not video_paths:
            logger.error("no video paths provided for merging")
            return False

        start = time.time()
        context_logger = logger.bind(
            number_of_videos=len(video_paths),
            output_path=output_path,
            background_music=bool(background_music_path),
            background_music_volume=background_music_volume,
        )

        try:
            # Get dimensions from the first video
            first_video_info = self.get_video_info(video_paths[0])
            if not first_video_info:
                context_logger.error("failed to get video info from first video")
                return False

            target_width = first_video_info.get("width", 1080)
            target_height = first_video_info.get("height", 1920)
            target_dimensions = f"{target_width}:{target_height}"

            context_logger.bind(
                target_width=target_width, target_height=target_height
            ).debug("using dimensions from first video")

            # Base command
            cmd = [self.ffmpeg_path, "-y"]

            # Add input video files
            for video_path in video_paths:
                cmd.extend(["-i", video_path])

            # Add background music if provided
            music_input_index = None
            if background_music_path:
                cmd.extend(["-stream_loop", "-1", "-i", background_music_path])
                music_input_index = len(video_paths)

            # Create filter complex for concatenating videos with re-encoding
            if len(video_paths) == 1:
                # Single video - re-encode to ensure consistency
                # Check if the video has audio
                audio_info = self.get_audio_info(video_paths[0])
                has_audio = bool(audio_info.get('duration', 0) > 0)
                
                if background_music_path:
                    if has_audio:
                        cmd.extend(
                            [
                                "-filter_complex",
                                f"[0:v]scale={target_dimensions}:force_original_aspect_ratio=decrease,pad={target_dimensions}:(ow-iw)/2:(oh-ih)/2:black,fps=30[v];[{music_input_index}:a]volume={background_music_volume}[bg];[0:a][bg]amix=inputs=2:duration=first[a]",
                                "-map",
                                "[v]",
                                "-map",
                                "[a]",
                            ]
                        )
                    else:
                        # No audio in video, just use background music
                        cmd.extend(
                            [
                                "-filter_complex",
                                f"[0:v]scale={target_dimensions}:force_original_aspect_ratio=decrease,pad={target_dimensions}:(ow-iw)/2:(oh-ih)/2:black,fps=30[v];[{music_input_index}:a]volume={background_music_volume}[a]",
                                "-map",
                                "[v]",
                                "-map",
                                "[a]",
                            ]
                        )
                else:
                    if has_audio:
                        cmd.extend(
                            [
                                "-filter_complex",
                                f"[0:v]scale={target_dimensions}:force_original_aspect_ratio=decrease,pad={target_dimensions}:(ow-iw)/2:(oh-ih)/2:black,fps=30[v]",
                                "-map",
                                "[v]",
                                "-map",
                                "0:a",
                            ]
                        )
                    else:
                        # No audio in video and no background music, create silent audio
                        video_info = self.get_video_info(video_paths[0])
                        video_duration = video_info.get('duration', 10)  # fallback to 10 seconds
                        cmd.extend(
                            [
                                "-filter_complex",
                                f"[0:v]scale={target_dimensions}:force_original_aspect_ratio=decrease,pad={target_dimensions}:(ow-iw)/2:(oh-ih)/2:black,fps=30[v];anullsrc=channel_layout=stereo:sample_rate=48000:duration={video_duration}[a]",
                                "-map",
                                "[v]",
                                "-map",
                                "[a]",
                            ]
                        )
            else:
                # Multiple videos - normalize and concatenate with re-encoding
                # First, check which videos have audio streams
                videos_with_audio = []
                for i, video_path in enumerate(video_paths):
                    video_info = self.get_video_info(video_path)
                    # Check if video has audio by trying to get audio info
                    audio_info = self.get_audio_info(video_path)
                    has_audio = bool(audio_info.get('duration', 0) > 0)
                    videos_with_audio.append(has_audio)
                    context_logger.bind(video_index=i, has_audio=has_audio).debug("checked audio stream")

                # Create normalized video streams for each input
                normalize_filters = []
                for i in range(len(video_paths)):
                    normalize_filters.append(
                        f"[{i}:v]scale={target_dimensions}:force_original_aspect_ratio=decrease,pad={target_dimensions}:(ow-iw)/2:(oh-ih)/2:black,fps=30,format=yuv420p[v{i}n]"
                    )

                # Create audio streams for videos without audio (silent audio)
                audio_filters = []
                for i in range(len(video_paths)):
                    if not videos_with_audio[i]:
                        # Get video duration for silent audio generation
                        video_info = self.get_video_info(video_paths[i])
                        video_duration = video_info.get('duration', 10)  # fallback to 10 seconds
                        audio_filters.append(f"anullsrc=channel_layout=stereo:sample_rate=48000:duration={video_duration}[a{i}n]")
                    else:
                        audio_filters.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo[a{i}n]")

                # Create the concat filter using normalized streams
                concat_inputs = ""
                for i in range(len(video_paths)):
                    concat_inputs += f"[v{i}n][a{i}n]"

                # Combine all filters
                all_filters = normalize_filters + audio_filters
                filter_complex = (
                    ";".join(all_filters)
                    + f";{concat_inputs}concat=n={len(video_paths)}:v=1:a=1[v][a]"
                )

                if background_music_path:
                    # Mix the concatenated audio with background music
                    filter_complex += f";[{music_input_index}:a]volume={background_music_volume}[bg];[a][bg]amix=inputs=2:duration=first[final_a]"
                    cmd.extend(
                        [
                            "-filter_complex",
                            filter_complex,
                            "-map",
                            "[v]",
                            "-map",
                            "[final_a]",
                        ]
                    )
                else:
                    cmd.extend(
                        [
                            "-filter_complex",
                            filter_complex,
                            "-map",
                            "[v]",
                            "-map",
                            "[a]",
                        ]
                    )

            # Video codec settings
            cmd.extend(
                [
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "23",
                ]
            )

            # Audio codec settings
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])

            # Other settings
            cmd.extend(["-pix_fmt", "yuv420p", output_path])

            # Execute the command using the new method

            # calculate expected duration for progress tracking
            expected_duration = 0
            for video_path in video_paths:
                video_info = self.get_video_info(video_path)
                expected_duration += video_info.get("duration", 0)

            success = self.execute_ffmpeg_command(
                cmd,
                "merge videos",
                expected_duration=expected_duration,
                show_progress=True,
            )

            if success:
                context_logger.bind(execution_time=time.time() - start).debug(
                    "videos merged successfully",
                )
                return True
            else:
                context_logger.error("ffmpeg failed to merge videos")
                return False

        except Exception as e:
            context_logger.bind(error=str(e)).error(
                "error merging videos",
            )
            return False

    def get_video_info(self, file_path: str) -> dict:
        """
        Retrieves video information such as duration, width, height, codec, fps, etc.

        Args:
            file_path: Path to the video file

        Returns:
            Dictionary containing video information
        """
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                "-select_streams",
                "v:0",  # Select first video stream
                file_path,
            ]

            success, stdout, stderr = self.execute_ffprobe_command(
                cmd, "get video info"
            )

            if not success:
                raise Exception(f"ffprobe failed: {stderr}")

            probe_data = json.loads(stdout)

            # Extract format information
            format_info = probe_data.get("format", {})
            streams = probe_data.get("streams", [])

            if not streams:
                raise Exception("No video stream found in file")

            video_stream = streams[0]

            video_info = {
                "duration": float(format_info.get("duration", 0)),
                "width": video_stream.get("width"),
                "height": video_stream.get("height"),
                "fps": video_stream.get("avg_frame_rate", "0/1").split("/")[0],
                "aspect_ratio": video_stream.get("display_aspect_ratio", "1:1"),
                "codec": video_stream.get("codec_name"),
            }

            return video_info

        except Exception as e:
            logger.bind(file_path=file_path, error=str(e)).error(
                "error getting video info"
            )
            return {}

    def get_audio_info(self, file_path: str) -> dict:
        """
        Retrieves audio information such as duration, codec, bitrate, sample rate, channels, etc.

        Args:
            file_path: Path to the audio file

        Returns:
            Dictionary containing audio information
        """
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                "-select_streams",
                "a:0",  # Select first audio stream
                file_path,
            ]

            success, stdout, stderr = self.execute_ffprobe_command(
                cmd, "get audio info"
            )

            if not success:
                raise Exception(f"ffprobe failed: {stderr}")

            probe_data = json.loads(stdout)

            # Extract format information
            format_info = probe_data.get("format", {})
            streams = probe_data.get("streams", [])

            if not streams:
                raise Exception("No audio stream found in file")

            audio_stream = streams[0]

            audio_info = {
                "duration": float(format_info.get("duration", 0)),
                "channels": audio_stream.get("channels", 0),
                "sample_rate": audio_stream.get("sample_rate", "0"),
                "codec": audio_stream.get("codec_name", ""),
                "bitrate": audio_stream.get("bit_rate", "0"),
            }

            return audio_info

        except Exception as e:
            logger.bind(file_path=file_path, error=str(e)).error(
                "Error getting audio info"
            )
            return {}

    def extract_frame(
        self,
        video_path: str,
        output_path: str,
        time_seconds: float = 0.0,
    ) -> bool:
        """
        Extracts a frame from a video at a specified time.

        Args:
            video_path: Path to the input video file
            output_path: Path for the extracted frame image
            time_seconds: Time in seconds to extract the frame (default: 0.0)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Base command
            cmd = [self.ffmpeg_path, "-y"]

            # Add input video file
            cmd.extend(["-i", video_path])

            # Seek to the specified time and extract one frame
            cmd.extend(
                [
                    "-ss",
                    str(time_seconds),  # Seek to time
                    "-vframes",
                    "1",  # Extract only one frame
                    "-q:v",
                    "2",  # High quality (scale 1-31, lower is better)
                    output_path,
                ]
            )

            # Execute the command using the new method
            success = self.execute_ffmpeg_command(
                cmd,
                "extract frame",
                show_progress=False,  # No progress tracking for single frame extraction
            )

            if success:
                logger.bind(video_path=video_path, time_seconds=time_seconds).debug(
                    "frame extracted successfully"
                )
                return True
            else:
                logger.bind(video_path=video_path, time_seconds=time_seconds).error(
                    "failed to extract frame from video"
                )
                return False

        except Exception as e:
            logger.bind(error=str(e)).error("Error extracting frame from video")
            return False

    def extract_frames(
        self,
        video_path: str,
        output_template: str,
        amount: int = 5,
        length_seconds: float = None,
    ) -> bool:
        """
        Args:
            video_path: Path to the input video file
            output_template: Template for output image files (e.g., "frame-%03d.jpg")
            amount: Number of frames to extract (default: 5)
            length_seconds: Length of the video in seconds (optional, if not provided will be calculated)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get video duration if not provided
            if length_seconds is None:
                video_info = self.get_video_info(video_path)
                length_seconds = video_info.get("duration", 0)

            if length_seconds <= 0:
                logger.error("invalid video duration for frame extraction")
                return False

            # Calculate frame interval (time between frames)
            # This gives us the correct fps rate to extract exactly 'amount' frames
            # evenly distributed across the video duration
            frame_interval = length_seconds / amount

            # Base command - using the corrected fps calculation
            # fps=1/frame_interval extracts one frame every frame_interval seconds
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-i",
                video_path,
                "-vf",
                f"fps=1/{frame_interval}",
                "-vframes",
                str(amount),
                "-qscale:v",
                "2",  # High quality
                output_template,
            ]

            # Execute the command using the new method
            success = self.execute_ffmpeg_command(
                cmd,
                "extract frames",
                expected_duration=length_seconds,
                show_progress=True,
            )

            if success:
                logger.bind(video_path=video_path, amount=amount).debug(
                    "frames extracted successfully"
                )
                return True
            else:
                logger.bind(video_path=video_path, amount=amount).error(
                    "failed to extract frames from video"
                )
                return False

        except Exception as e:
            logger.bind(error=str(e)).error("Error extracting frames from video")
            return False

    def format_time(self, seconds: float) -> str:
        """
        Format seconds into HH:MM:SS format.

        Args:
            seconds: Time in seconds

        Returns:
            Formatted time string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def execute_ffmpeg_command(
        self,
        cmd: list,
        operation_name: str,
        expected_duration: float = None,
        show_progress: bool = True,
    ) -> bool:
        """
        Execute an ffmpeg command with proper logging and progress tracking.

        Args:
            cmd: The ffmpeg command as a list
            operation_name: Name of the operation for logging
            expected_duration: Expected duration for progress calculation
            show_progress: Whether to show progress information

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.bind(command=" ".join(cmd), operation=operation_name).debug(
                f"executing ffmpeg command for {operation_name}"
            )

            process = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                text=True,
            )

            # Process the output line by line as it becomes available
            for line in process.stderr:
                # Extract time information for progress tracking
                if (
                    show_progress
                    and expected_duration
                    and "time=" in line
                    and "speed=" in line
                ):
                    try:
                        # Extract the time information
                        time_str = line.split("time=")[1].split(" ")[0]
                        # Convert HH:MM:SS.MS format to seconds
                        h, m, s = time_str.split(":")
                        seconds = float(h) * 3600 + float(m) * 60 + float(s)

                        # Calculate progress percentage
                        progress = min(100, (seconds / expected_duration) * 100)
                        logger.info(
                            f"{operation_name}: {progress:.2f}% complete (Time: {time_str} / Total: {self.format_time(expected_duration)})"
                        )
                    except (ValueError, IndexError):
                        # If parsing fails, continue silently
                        pass
                elif any(
                    keyword in line
                    for keyword in [
                        # Skip initialization information
                        "ffmpeg version",
                        "built with",
                        "configuration:",
                        "libav",
                        "Input #",
                        "Metadata:",
                        "Duration:",
                        "Stream #",
                        "Press [q]",
                        "Output #",
                        "Stream mapping:",
                        # Skip processing details
                        "frame=",
                        "fps=",
                        "[libx264",
                        "kb/s:",
                        "Qavg:",
                        "video:",
                        "audio:",
                        "subtitle:",
                        "frame I:",
                        "frame P:",
                        "mb I",
                        "mb P",
                        "coded y,",
                        "i16 v,h,dc,p:",
                        "i8c dc,h,v,p:",
                        "compatible_brands:",
                        "encoder",
                        "Side data:",
                        "libswscale",
                        "libswresample",
                        "libpostproc",
                        # Additional patterns to filter
                        "ffmpeg: libswscale",
                        "ffmpeg: libswresample",
                        "ffmpeg: libpostproc",
                    ]
                ):
                    # Skip all technical output lines
                    pass
                else:
                    # Only print important messages (like errors and warnings)
                    # that don't match any of the filtered patterns
                    if not line.strip() or line.strip().startswith("["):
                        continue

                    # Skip header lines that describe inputs
                    if ":" in line and any(
                        header in line
                        for header in [
                            "major_brand",
                            "minor_version",
                            "creation_time",
                            "handler_name",
                            "vendor_id",
                            "Duration",
                            "bitrate",
                        ]
                    ):
                        continue

                    logger.debug(f"ffmpeg: {line.strip()}")

            # Wait for the process to complete and check the return code
            return_code = process.wait()
            if return_code != 0:
                logger.bind(return_code=return_code, operation=operation_name).error(
                    f"ffmpeg exited with code: {return_code} for {operation_name}"
                )
                return False

            logger.bind(operation=operation_name).debug(
                f"{operation_name} completed successfully"
            )
            return True

        except Exception as e:
            logger.bind(error=str(e), operation=operation_name).error(
                f"error executing ffmpeg command for {operation_name}"
            )
            return False

    def execute_ffprobe_command(
        self, cmd: list, operation_name: str
    ) -> tuple[bool, str, str]:
        """
        Execute an ffprobe command with proper logging.

        Args:
            cmd: The ffprobe command as a list
            operation_name: Name of the operation for logging

        Returns:
            tuple: (success, stdout, stderr)
        """
        try:
            logger.bind(command=" ".join(cmd), operation=operation_name).debug(
                f"executing ffprobe command for {operation_name}"
            )

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = process.communicate()

            if process.returncode != 0:
                logger.bind(stderr=stderr, operation=operation_name).error(
                    f"ffprobe failed for {operation_name}"
                )
                return False, stdout, stderr

            logger.bind(operation=operation_name).debug(
                f"{operation_name} completed successfully"
            )
            return True, stdout, stderr

        except Exception as e:
            logger.bind(error=str(e), operation=operation_name).error(
                f"error executing ffprobe command for {operation_name}"
            )
            return False, "", str(e)

    @staticmethod
    def is_hex_color(color: str) -> bool:
        """
        Checks if the given color string is a valid hex color.

        Args:
            color: Color string to check

        Returns:
            bool: True if it's a hex color, False otherwise
        """
        return all(
            c in "0123456789abcdefABCDEF" for c in color[1:]
        )

    def colorkey_overlay(
        self,
        input_video_path: str,
        overlay_video_path: str,
        output_video_path: str,
        color: str = "black",
        similarity: float = 0.15,
        blend: float = 0.2,
    ):
        """
        Applies a colorkey overlay to a video using FFmpeg.
        Loops the overlay to match the duration of the main video.
        Perfect for vintage dust/scratch overlays.
        """
        start = time.time()
        info = self.get_video_info(input_video_path)
        video_duration = info.get("duration", 0)

        if not video_duration:
            logger.error("Failed to get video duration from input video")
            return False

        # Enhanced color handling for vintage effects
        color = color.lstrip("#")
        if color.lower() == "black":
            color = "0x000000"
        elif self.is_hex_color(color):
            color = f"0x{color.upper()}"
        elif not color.startswith("0x"):
            # Handle named colors
            color_map = {
                "green": "0x00FF00",
                "blue": "0x0000FF",
                "red": "0xFF0000",
                "white": "0xFFFFFF"
            }
            color = color_map.get(color.lower(), "0x000000")
        
        context_logger = logger.bind(
            input_video_path=input_video_path,
            overlay_video_path=overlay_video_path,
            output_video_path=output_video_path,
            video_duration=video_duration,
            color=color,
            similarity=similarity,
            blend=blend,
        )
        context_logger.debug("Starting enhanced colorkey overlay process for vintage effect")

        # Enhanced FFmpeg command for better vintage texture overlay
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", input_video_path,
            "-stream_loop", "-1",  # Loop the overlay video indefinitely
            "-i", overlay_video_path,
            "-filter_complex", f"[1:v]colorkey={color}:{similarity}:{blend}[ckout];[0:v][ckout]overlay=shortest=1:eof_action=repeat[v]",
            "-map", "[v]",
            "-map", "0:a?",  # Use the audio from the input video if it exists
            "-c:v", "libx264",
            "-preset", "fast",  # Better quality than ultrafast
            "-crf", "22",  # Slightly higher quality
            "-c:a", "copy",
            "-t", str(video_duration),
            output_video_path,
        ]

        try:
            success = self.execute_ffmpeg_command(
                cmd,
                "add colorkey overlay to video",
                expected_duration=video_duration,
                show_progress=True,
            )

            if success:
                context_logger.bind(execution_time=time.time() - start).debug(
                    "colorkey overlay added successfully",
                )
                return True
            else:
                context_logger.error("ffmpeg failed to create colorkey overlay")
                return False

        except Exception as e:
            context_logger.bind(error=str(e)).error(
                "error adding colorkey overlay to video",
            )
            return False

    def apply_vintage_filter(
        self,
        input_path: str,
        output_path: str,
        grain_strength: int = 8,
        vignette_intensity: float = 0.1,
    ) -> bool:
        """
        Applies a vintage filter with film grain and a vignette to a video.
        """
        start = time.time()
        video_info = self.get_video_info(input_path)
        expected_duration = video_info.get("duration", 0)

        # The vignette filter in FFmpeg uses an expression. 'PI/60' is a subtle start.
        # A higher divisor means a more subtle vignette. We can link it to intensity.
        vignette_angle = f"PI/{max(2, 60 * (1 - vignette_intensity))}"

        context_logger = logger.bind(
            input_path=input_path,
            output_path=output_path,
            grain_strength=grain_strength,
            vignette_angle=vignette_angle,
        )
        context_logger.debug("Applying vintage filter")

        cmd = [
            self.ffmpeg_path, "-y",
            "-i", input_path,
            "-vf", f"noise=alls={grain_strength}:allf=t+u,vignette='{vignette_angle}'",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "copy",
            output_path,
        ]

        success = self.execute_ffmpeg_command(
            cmd,
            "apply vintage filter",
            expected_duration=expected_duration,
            show_progress=True,
        )

        if success:
            context_logger.bind(execution_time=time.time() - start).info(
                "Vintage filter applied successfully"
            )
            return True
        else:
            context_logger.error("Failed to apply vintage filter")
            return False
        
    def convert_pcm_to_wav(
        self,
        input_pcm_path: str,
        output_wav_path: str,
        sample_rate: int = 24000,
        channels: int = 1,
        target_sample_rate: int = 44100,
    ) -> bool:
        """
        ffmpeg -f s16le -ar 24000 -ac 1 -i out.pcm -ar 44100 -ac 2 out_44k_stereo.wav
        """
        start = time.time()
        context_logger = logger.bind(
            input_pcm_path=input_pcm_path,
            output_wav_path=output_wav_path,
            sample_rate=sample_rate,
            channels=channels,
            target_sample_rate=target_sample_rate,
        )
        context_logger.debug("Starting PCM to WAV conversion")

        cmd = [
            self.ffmpeg_path, "-y",
            "-f", "s16le",
            "-ar", str(sample_rate),
            "-ac", str(channels),
            "-i", input_pcm_path,
            "-ar", str(target_sample_rate),
            "-ac", "2",  # Convert to stereo
            output_wav_path,
        ]

        try:
            success = self.execute_ffmpeg_command(
                cmd,
                "convert PCM to WAV",
                show_progress=False,
            )

            if success:
                context_logger.bind(execution_time=time.time() - start).debug(
                    "PCM to WAV conversion successful",
                )
                return True
            else:
                context_logger.error("ffmpeg failed to convert PCM to WAV")
                return False

        except Exception as e:
            context_logger.bind(error=str(e)).error(
                "error converting PCM to WAV",
            )
            return False
