import numpy as np
import requests
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw, ImageChops, ImageOps, ImageFont
from io import BytesIO
import math


def stitch_images(
    image_urls: list[str],
    max_width: int = 1920,
    max_height: int = 1080
):
    """
    Stitch multiple images into a single image.
    Downloads images from URLs, arranges them in a grid, and resizes proportionally to fit max dimensions.
    
    Args:
        image_urls: List of image URLs to download and stitch
        max_width: Maximum width of the final stitched image
        max_height: Maximum height of the final stitched image
    
    Returns:
        PIL Image object of the stitched result
    """
    if not image_urls:
        raise ValueError("No image URLs provided")
    
    # Download and open all images
    images = []
    for url in image_urls:
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content))
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')
            images.append(img)
        except Exception as e:
            print(f"Failed to download image from {url}: {e}")
            continue
    
    if not images:
        raise ValueError("No valid images could be downloaded")
    
    # Calculate optimal grid dimensions
    num_images = len(images)
    cols = math.ceil(math.sqrt(num_images))
    rows = math.ceil(num_images / cols)
    
    # Find the maximum dimensions among all images to ensure consistent sizing
    max_img_width = max(img.width for img in images)
    max_img_height = max(img.height for img in images)
    
    # Calculate the size for each cell in the grid
    cell_width = max_img_width
    cell_height = max_img_height
    
    # Create the stitched image canvas
    canvas_width = cols * cell_width
    canvas_height = rows * cell_height
    stitched = Image.new('RGB', (canvas_width, canvas_height), color='white')
    
    # Place images in the grid
    for i, img in enumerate(images):
        row = i // cols
        col = i % cols
        
        # Calculate position for this image
        x = col * cell_width
        y = row * cell_height
        
        # Resize image to fit cell while maintaining aspect ratio
        img_resized = resize_image_to_fit(img, cell_width, cell_height)
        
        # Center the image in the cell
        offset_x = (cell_width - img_resized.width) // 2
        offset_y = (cell_height - img_resized.height) // 2
        
        stitched.paste(img_resized, (x + offset_x, y + offset_y))
    
    # Resize the final stitched image to fit within max dimensions
    final_image = resize_image_to_fit(stitched, max_width, max_height)
    
    return final_image

def resize_image_cover(
    image_path: str, 
    target_width: int, 
    target_height: int,
    output_path: str,
    ) -> Image.Image:
    """
    Resize an image to fill the specified dimensions while maintaining aspect ratio.
    The image is scaled to cover the entire target area and cropped to fit.
    
    Args:
        image: PIL Image object to resize
        target_width: Target width
        target_height: Target height
    
    Returns:
        Resized and cropped PIL Image object
    """
    image = Image.open(image_path)
    # Calculate the scaling factor to cover the entire target area
    width_ratio = target_width / image.width
    height_ratio = target_height / image.height
    scale_factor = max(width_ratio, height_ratio)  # Use max to ensure coverage
    
    # Scale the image
    new_width = int(image.width * scale_factor)
    new_height = int(image.height * scale_factor)
    scaled_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Calculate crop box to center the image
    left = (new_width - target_width) // 2
    top = (new_height - target_height) // 2
    right = left + target_width
    bottom = top + target_height
    
    # Crop the image to the target dimensions
    cropped_image = scaled_image.crop((left, top, right, bottom))

    # Convert to RGB if the image has transparency (RGBA mode)
    if cropped_image.mode == 'RGBA':
        # Create a white background and paste the image on it
        rgb_image = Image.new('RGB', cropped_image.size, (255, 255, 255))
        rgb_image.paste(cropped_image, mask=cropped_image.split()[-1])  # Use alpha channel as mask
        cropped_image = rgb_image
    
    cropped_image.save(output_path)

def resize_image_to_fit(image: Image.Image, max_width: int, max_height: int) -> Image.Image:
    """
    Resize an image to fit within the specified dimensions while maintaining aspect ratio.
    
    Args:
        image: PIL Image object to resize
        max_width: Maximum width
        max_height: Maximum height
    
    Returns:
        Resized PIL Image object
    """
    # Calculate the scaling factor to fit within max dimensions
    width_ratio = max_width / image.width
    height_ratio = max_height / image.height
    scale_factor = min(width_ratio, height_ratio)
    
    # Only resize if the image is larger than max dimensions
    if scale_factor < 1:
        new_width = int(image.width * scale_factor)
        new_height = int(image.height * scale_factor)
        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    return image

def cup_of_coffee_tone(img):
    sepia = ImageOps.colorize(img.convert("L"), "#704214", "#C0A080")
    return Image.blend(img, sepia, alpha=0.2)  # tweak alpha

def chromatic_aberration(img, shift=2):
    r, g, b = img.split()
    # Use transform with AFFINE to shift the channels
    r = r.transform(img.size, Image.AFFINE, (1, 0, -shift, 0, 1, 0))
    b = b.transform(img.size, Image.AFFINE, (1, 0, shift, 0, 1, 0))
    return Image.merge("RGB", (r, g, b))

def make_image_imperfect(
    image_path: str,
    enhance_color: float = None,
    enhance_contrast: float = None,
    noise_strength: int = 15
) -> Image.Image:
    """
    Remove AI-generated artifacts from an image.
    This is a placeholder function. Actual implementation would depend on the specific algorithm used.
    
    Args:
        image_url: URL of the image to process
    
    Returns:
        PIL Image object of the processed result
    """
    try:
        img = Image.open(image_path)
        
        if enhance_color is not None:
            img = ImageEnhance.Color(img).enhance(enhance_color)
        if enhance_contrast is not None:
            img = ImageEnhance.Contrast(img).enhance(enhance_contrast)
        
        img = img.filter(ImageFilter.SHARPEN)
        img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
        
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img_array = np.array(img)
        h, w, c = img_array.shape
        grayscale_noise = np.random.randint(-noise_strength, noise_strength + 1, (h, w), dtype='int16')
        noise = np.stack([grayscale_noise] * c, axis=2)
        noisy_array = img_array.astype('int16') + noise
        noisy_array = np.clip(noisy_array, 0, 255).astype('uint8')
        img = Image.fromarray(noisy_array)
        
        img = cup_of_coffee_tone(img)
        img = chromatic_aberration(img, shift=1)
        
        return img
        
    except Exception as e:
        print(f"Failed to process image from {image_path}: {e}")
        raise ValueError("Failed to unaize image") from e

def create_text_image(
    text: str,
    size: tuple[int, int] = (1920, 1080),
    font_size: int = 120,
    font_color: str = "white",
    font_path: str = None
) -> Image.Image:
    """
    Create an image with centered text.
    
    Args:
        text: Text to display on the image
        width: Width of the image
        height: Height of the image
        font_size: Size of the font
        font_color: Color of the text
    
    Returns:
        PIL Image object with the text centered
    """
    img = Image.new('RGB', size, color='black')
    draw = ImageDraw.Draw(img)
    
    font = ImageFont.load_default(size=font_size)
    if font_path:
        font = ImageFont.truetype(font_path, font_size)
    font_bbox = font.getbbox(text)
    text_width = font_bbox[2] - font_bbox[0]
    text_height = font_bbox[3] - font_bbox[1]
    x = (size[0] - text_width) // 2
    y = (size[1] - text_height) // 2
    draw.text((x, y), text, fill=font_color, font=font)
    
    return img

def make_image_wobbly(
    image: Image.Image,
    wobble_amount: float = 3.0
) -> Image.Image:
    """
    Apply a subtle wobble/distortion effect to an image, like viewing through water or a warped mirror.
    
    Args:
        image: PIL Image object to distort
        wobble_amount: Strength of the wobble effect (0.5-10.0, higher = more distortion)
    
    Returns:
        PIL Image object with wobble effect applied
    """
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    width, height = image.size
    img_array = np.array(image)
    
    # Create coordinate grids
    x_coords = np.arange(width)
    y_coords = np.arange(height)
    x_grid, y_grid = np.meshgrid(x_coords, y_coords)
    
    # Create random wave patterns optimized for text
    # Generate random parameters for each wave to ensure variety
    
    # Random wave frequencies and phases for horizontal waves
    freq1_h = np.random.uniform(2, 5)  # Random frequency between 2-5
    freq2_h = np.random.uniform(5, 10)  # Random frequency between 5-10
    phase1_h = np.random.uniform(0, 2 * np.pi)  # Random phase
    phase2_h = np.random.uniform(0, 2 * np.pi)  # Random phase
    
    wave_x1 = wobble_amount * 0.3 * np.sin(2 * np.pi * y_grid / (height / freq1_h) + phase1_h)
    wave_x2 = wobble_amount * 0.1 * np.sin(2 * np.pi * y_grid / (height / freq2_h) + phase2_h)
    
    # Random wave frequencies and phases for vertical waves
    freq1_v = np.random.uniform(2, 6)  # Random frequency between 2-6
    freq2_v = np.random.uniform(6, 12)  # Random frequency between 6-12
    phase1_v = np.random.uniform(0, 2 * np.pi)  # Random phase
    phase2_v = np.random.uniform(0, 2 * np.pi)  # Random phase
    
    wave_y1 = wobble_amount * 0.3 * np.sin(2 * np.pi * x_grid / (width / freq1_v) + phase1_v)
    wave_y2 = wobble_amount * 0.1 * np.sin(2 * np.pi * x_grid / (width / freq2_v) + phase2_v)
    
    # Random circular ripples with random centers and frequencies
    center_x = width // 2 + np.random.randint(-width//4, width//4)
    center_y = height // 2 + np.random.randint(-height//4, height//4)
    ripple_freq = np.random.uniform(80, 120)  # Random ripple frequency
    ripple_phase = np.random.uniform(0, 2 * np.pi)  # Random ripple phase
    
    distance = np.sqrt((x_grid - center_x)**2 + (y_grid - center_y)**2)
    ripple_x = wobble_amount * 0.15 * np.sin(2 * np.pi * distance / ripple_freq + ripple_phase)
    ripple_y = wobble_amount * 0.15 * np.cos(2 * np.pi * distance / ripple_freq + ripple_phase)
    
    # Random noise for text preservation - NO FIXED SEED
    noise_x = np.random.normal(0, wobble_amount * 0.05, (height, width))
    noise_y = np.random.normal(0, wobble_amount * 0.05, (height, width))
    
    # Combine all distortions
    total_x_offset = wave_x1 + wave_x2 + ripple_x + noise_x
    total_y_offset = wave_y1 + wave_y2 + ripple_y + noise_y
    
    # Apply the distortion with proper boundary handling
    new_x_coords = x_grid + total_x_offset
    new_y_coords = y_grid + total_y_offset
    
    # Use scipy.ndimage.map_coordinates for efficient interpolation
    try:
        from scipy.ndimage import map_coordinates
        
        # Create coordinate arrays for map_coordinates (expects [y, x] order)
        coords = np.array([new_y_coords, new_x_coords])
        
        # Apply the transformation to each color channel with adaptive interpolation
        # Use progressively smoother interpolation for higher wobble amounts
        distorted_array = np.zeros_like(img_array)
        
        # Choose interpolation method based on wobble amount for smoothest results
        if wobble_amount <= 1.5:
            # For very subtle wobbles, use nearest neighbor to preserve text sharpness
            interpolation_order = 0
        elif wobble_amount <= 3.0:
            # For moderate wobbles, use linear interpolation
            interpolation_order = 1
        else:
            # For strong wobbles, use cubic interpolation for smoothest edges
            interpolation_order = 3
        
        for channel in range(img_array.shape[2]):
            distorted_array[:, :, channel] = map_coordinates(
                img_array[:, :, channel],
                coords,
                order=interpolation_order,
                mode='reflect',  # Mirror edges instead of clipping
                prefilter=True if interpolation_order > 1 else False  # Use prefilter for cubic
            )
        
        result_img = Image.fromarray(distorted_array.astype(np.uint8))
        
        # Post-process for smoother edges at higher wobble amounts
        if wobble_amount > 2.0:
            # Apply a very subtle Gaussian blur to smooth any remaining artifacts
            result_img = result_img.filter(ImageFilter.GaussianBlur(radius=0.3))
            # Then apply gentle sharpening to maintain text readability
            result_img = result_img.filter(ImageFilter.UnsharpMask(radius=0.8, percent=60, threshold=1))
        elif wobble_amount > 1.5:
            # For moderate wobbles, just apply gentle sharpening
            result_img = result_img.filter(ImageFilter.UnsharpMask(radius=0.5, percent=40, threshold=0))
        
        return result_img
        
        return Image.fromarray(distorted_array.astype(np.uint8))
    
    except ImportError:
        # Fallback to PIL's transform if scipy is not available
        # This is much faster than the pixel-by-pixel approach
        from PIL.Image import AFFINE
        
        # For a simple approximation, apply a slight transform
        # This won't be as sophisticated but will be much faster
        transformed = image.transform(
            image.size,
            AFFINE,
            (1, 0.02 * wobble_amount/10, 0.02 * wobble_amount/10, 1, 0, 0),
            resample=Image.BILINEAR
        )
        
        # Apply a slight rotation for additional wobble with random angle
        angle = wobble_amount * 0.3 * np.random.uniform(-1, 1)  # Random rotation
        rotated = transformed.rotate(angle, resample=Image.BILINEAR, expand=False)
        
        return rotated
    
    