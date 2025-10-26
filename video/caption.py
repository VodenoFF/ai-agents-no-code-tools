import string
from typing import List, Dict, Tuple
from loguru import logger

from typing import Dict, List


class Caption:
    def is_punctuation(self, text):
        return text in string.punctuation

    def create_subtitle_segments_english(
        self, captions: List[Dict], max_length=80, lines=2
    ):
        """
        Breaks up the captions into segments of max_length characters
        on two lines and merge punctuation with the last word
        """

        if not captions:
            return []

        segments = []
        current_segment_texts = ["" for _ in range(lines)]
        current_line = 0
        segment_start_ts = captions[0]["start_ts"]
        segment_end_ts = captions[0]["end_ts"]

        for caption in captions:
            text = caption["text"]
            start_ts = caption["start_ts"]
            end_ts = caption["end_ts"]

            # Update the segment end timestamp
            segment_end_ts = end_ts

            # If the caption is a punctuation, merge it with the current line
            if self.is_punctuation(text):
                if current_line < lines and current_segment_texts[current_line]:
                    current_segment_texts[current_line] += text
                continue

            # If the line is too long, move to the next one
            if (
                current_line < lines
                and len(current_segment_texts[current_line] + text) > max_length
            ):
                current_line += 1

            # If we've filled all lines, save the current segment and start a new one
            if current_line >= lines:
                segments.append(
                    {
                        "text": current_segment_texts,
                        "start_ts": segment_start_ts,
                        "end_ts": segment_end_ts,
                    }
                )

                # Reset for next segment
                current_segment_texts = ["" for _ in range(lines)]
                current_line = 0
                # Add a small gap (0.05s) between segments to prevent overlap
                segment_start_ts = start_ts + 0.05

            # Add the text to the current segment
            if current_line < lines:
                current_segment_texts[current_line] += (
                    " " if current_segment_texts[current_line] else ""
                )
                current_segment_texts[current_line] += text

        # Add the last segment if there's any content
        if any(current_segment_texts):
            segments.append(
                {
                    "text": current_segment_texts,
                    "start_ts": segment_start_ts,
                    "end_ts": segment_end_ts,
                }
            )

        # Post-processing to ensure no overlaps by adjusting end times if needed
        for i in range(len(segments) - 1):
            if segments[i]["end_ts"] >= segments[i + 1]["start_ts"]:
                segments[i]["end_ts"] = segments[i + 1]["start_ts"] - 0.05

        return segments

    def create_subtitle_segments_international(
        self, captions: List[Dict], max_length=80, lines=2
    ):
        """
        Breaks up international captions (full sentences) into smaller segments that fit
        within max_length characters per line, with proper timing distribution.

        Handles both space-delimited languages like English and character-based languages like Chinese.

        Args:
            captions: List of caption dictionaries with text, start_ts, and end_ts
            max_length: Maximum number of characters per line
            lines: Number of lines per segment

        Returns:
            List of subtitle segments
        """
        if not captions:
            return []

        segments = []

        for caption in captions:
            text = caption["text"].strip()
            start_ts = caption["start_ts"]
            end_ts = caption["end_ts"]
            duration = end_ts - start_ts

            # Check if text is using Chinese/Japanese/Korean characters (CJK)
            # For CJK, we'll split by characters rather than words
            is_cjk = any("\u4e00" <= char <= "\u9fff" for char in text)

            parts = []
            if is_cjk:
                # For CJK languages, process character by character
                current_part = ""
                for char in text:
                    if len(current_part + char) > max_length:
                        parts.append(current_part)
                        current_part = char
                    else:
                        current_part += char

                # Add the last part if not empty
                if current_part:
                    parts.append(current_part)
            else:
                # Original word-based splitting for languages with spaces
                words = text.split()
                current_part = ""

                for word in words:
                    # If adding this word would exceed max_length, start a new part
                    if len(current_part + " " + word) > max_length and current_part:
                        parts.append(current_part.strip())
                        current_part = word
                    else:
                        # Add space if not the first word in the part
                        if current_part:
                            current_part += " "
                        current_part += word

                # Add the last part if not empty
                if current_part:
                    parts.append(current_part.strip())

            # Group parts into segments with 'lines' number of lines per segment
            segment_parts = []
            for i in range(0, len(parts), lines):
                segment_parts.append(parts[i : i + lines])

            # Calculate time proportionally based on segment text length
            total_chars = sum(len("".join(part_group)) for part_group in segment_parts)

            current_time = start_ts
            for i, part_group in enumerate(segment_parts):
                # Get character count for this segment group
                segment_chars = len("".join(part_group))

                # Calculate time proportionally, but ensure at least a minimum duration
                if total_chars > 0:
                    segment_duration = (segment_chars / total_chars) * duration
                    segment_duration = max(
                        segment_duration, 0.5
                    )  # Ensure minimum duration of 0.5s
                else:
                    segment_duration = duration / len(segment_parts)

                segment_start = current_time
                segment_end = segment_start + segment_duration

                # Move current time forward for next segment
                current_time = segment_end

                # Create segment with proper text array format for the subtitle renderer
                segment_text = part_group + [""] * (lines - len(part_group))

                segments.append(
                    {
                        "text": segment_text,
                        "start_ts": segment_start,
                        "end_ts": segment_end,
                    }
                )

        # Ensure no overlaps between segments by adjusting end times if needed
        for i in range(len(segments) - 1):
            if segments[i]["end_ts"] >= segments[i + 1]["start_ts"]:
                segments[i]["end_ts"] = segments[i + 1]["start_ts"] - 0.05

        return segments

    @staticmethod
    def hex_to_ass(hex_color: str, alpha: float = 1.0) -> str:
        """
        Convert a hex color + transparency to ASS &HaaBBGGRR& format.

        :param hex_color: CSS-style color string, e.g. "#FFA07A" or "00ff00"
        :param alpha: transparency from 0.0 (opaque) to 1.0 (fully transparent)
        :return: ASS color string, e.g. "&H8014C8FF&"
        """

        # strip leading '#' if present
        hex_color = hex_color.lstrip('#')

        # support 3-digit shorthand like 'f0a'
        if len(hex_color) == 3:
            hex_color = ''.join([c*2 for c in hex_color])

        if len(hex_color) != 6:
            raise ValueError("hex_color must be in 'RRGGBB' or 'RGB' format")

        # parse RGB
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)

        # ASS alpha is inverted: 00=opaque, FF=transparent
        # so we invert the user's alpha (0.0 = opaque)  
        a = int((1.0 - alpha) * 255)
        a = max(0, min(255, a))

        # build BGR and alpha bytes
        aa = f"{a:02X}"
        bb = f"{b:02X}"
        gg = f"{g:02X}"
        rr = f"{r:02X}"

        return f"&H{aa}{bb}{gg}{rr}"

    def create_subtitle(
        self,
        segments,
        dimensions: Tuple[int, int],
        output_path: str,
        font_size=24, 
        font_color="#fff",
        shadow_color="#000",
        shadow_transparency=0.1,
        shadow_blur=0,
        stroke_color="#000",
        stroke_size=0,
        font_name="Arial",
        font_bold=True,
        font_italic=False,
        subtitle_position="center",
    ):
        width, height = dimensions
        bold_value = -1 if font_bold else 0
        italic_value = -1 if font_italic else 0
        
        position_from_top = 0.2
        if subtitle_position == "center":
            position_from_top = 0.45
        if subtitle_position == "bottom":
            position_from_top = 0.75
        
        ass_content = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{font_color},&H000000FF,{stroke_color},&H00000000,{bold},{italic},0,0,100,100,0,0,1,{stroke_size},0,8,20,20,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""".format(
            width=width,
            height=height,
            font_size=font_size,
            font_color=self.hex_to_ass(font_color),
            stroke_color=self.hex_to_ass(stroke_color),
            stroke_size=stroke_size,
            font_name=font_name,
            bold=bold_value,
            italic=italic_value
        )

        pos_x = int(width / 2)
        pos_y = int(height * position_from_top)

        # Process each segment and add to the subtitle file
        for segment in segments:
            start_time = self.format_time(segment["start_ts"])
            end_time = self.format_time(segment["end_ts"])

            # Create text with line breaks
            text_lines = segment["text"]
            formatted_text = ""
            for i, line in enumerate(text_lines):
                if line:  # Only add non-empty lines
                    if i > 0:  # Add line break if not the first line
                        formatted_text += "\\N"
                    formatted_text += line

            # Create shadow if shadow_blur is specified or if we want a drop shadow effect
            if shadow_blur > 0 or shadow_transparency < 1.0:
                # Convert shadow color with transparency
                shadow_color_ass = self.hex_to_ass(shadow_color, shadow_transparency)
                
                # Offset shadow position slightly for drop shadow effect
                shadow_pos_x = pos_x + 2
                shadow_pos_y = pos_y + 2
                
                # For shadow text, use shadow color only for primary color and set proper alpha
                # Only apply shadow color to primary color (\1c) and use alpha for transparency
                shadow_override_tags = f"\\pos({shadow_pos_x},{shadow_pos_y})\\1c{shadow_color_ass}\\bord0"
                
                # Add alpha transparency if needed
                if shadow_transparency > 0:
                    alpha_hex = hex(int((1.0 - shadow_transparency) * 255))[2:].upper().zfill(2)
                    shadow_override_tags += f"\\1a&H{alpha_hex}&"
                
                if shadow_blur > 0:
                    shadow_override_tags += f"\\blur{shadow_blur}"
                
                shadow_formatted_text = f"{{{shadow_override_tags}}}" + formatted_text
                
                # Add shadow dialogue line first (so it appears behind)
                ass_content += f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{shadow_formatted_text}\n"

            # Create main text layer
            main_override_tags = f"\\pos({pos_x},{pos_y})"
            main_formatted_text = f"{{{main_override_tags}}}" + formatted_text
            
            # Add main dialogue line (appears on top)
            ass_content += f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{main_formatted_text}\n"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

        logger.debug("subtitle (ass) was created with drop shadow")

    def format_time(self, seconds):
        """
        Convert seconds to ASS time format (H:MM:SS.cc)
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centisecs = int((seconds % 1) * 100)

        return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"
