"""
FastAPI version of Giraffe - Image processing service

You'll need to set these environment variables:

 - AWS_ACCESS_KEY_ID
 - AWS_SECRET_ACCESS_KEY

I'd recommend setting them in your ``app.sh`` file.

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from collections import namedtuple
from collections import OrderedDict
from contextlib import asynccontextmanager
from io import BytesIO
import gzip
import hashlib
import hmac
import os
import re
from typing import Optional
from urllib import parse

# List of allowed domains for proxying
ALLOWED_DOMAINS = {"example.com", "images.example.com"}

# FastAPI imports
from fastapi import FastAPI, Request, HTTPException, Query, Path
from fastapi.responses import Response, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# Keep existing imports
from PIL import Image as PillowImage
from requests.exceptions import HTTPError, ConnectionError
import requests
import tinys3
import wand
from wand.color import Color
from wand.font import Font
from wand.image import Image

FORMAT_MAP = {
    'png': {
        'extension': 'png',
        'format': {'format': 'png'},
    },
    'jpg': {
        'extension': 'jpg',
        'format': {'format': 'jpeg'},
    },
    'eps': {
        'extension': 'eps',
        'format': {'format': 'eps'},
    },
}

FORMAT_MAP['jpeg'] = FORMAT_MAP['jpg']

# Application lifespan events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application lifespan events"""
    # Startup
    connect_s3()
    yield
    # Shutdown
    pass

# FastAPI app initialization
app = FastAPI(
    title="Giraffe Image Processing Service",
    description="Image processing proxy with S3 integration",
    version="2.0.0",
    lifespan=lifespan
)

# Template configuration
templates = Jinja2Templates(directory="templates")

# Environment configuration
ENV = os.environ.get("ENV", "development").lower()
DEBUG = ENV not in ("production", "staging")
CACHE_URLS = os.environ.get("MEMCACHED").split(";") if os.environ.get("MEMCACHED") else []

SECRET = os.environ.get("GIRAFFE_SECRET", "0x24FEEDFACEDEADBEEFCAFE")

s3 = None
CACHE_DIR = os.environ.get("GIRAFFE_CACHE_DIR", 'giraffe')
CACHE_CONTROL = "max-age=2592000"
DEFAULT_QUALITY = 75
MAX_WIDTH = 7680
MAX_HEIGHT = 4320
MAX_PIXELS = MAX_WIDTH * MAX_HEIGHT # 8K resolution is pretty damn big
MAX_EXTENSION_LENGTH = 10  # Maximum allowed extension length


def get_image_size(bytes):
    img = PillowImage.open(BytesIO(bytes))
    width, height = img.size
    return width, height


def connect_s3():
    global s3
    if not s3:
        s3 = tinys3.Connection(os.environ.get("AWS_ACCESS_KEY_ID"),
                               os.environ.get("AWS_SECRET_ACCESS_KEY"),
                               )
    return s3


connect_s3()


ImageOp = namedtuple("ImageOp", 'function params')


# Lookup table for JPEG extensions (more secure than regex)
JPEG_EXTENSIONS = {'jpe', 'jpg', 'jpeg'}


def sanitize_extension(ext):
    """
    Sanitize extension input to prevent security issues.
    Only allow alphanumeric characters and limit length.
    """
    if not ext:
        return ""
    # Remove leading dot and convert to lowercase
    ext = ext.lower().strip(".")
    # Only allow alphanumeric characters and limit to reasonable length
    if not ext.isalnum() or len(ext) > MAX_EXTENSION_LENGTH:
        return ""
    return ext


def extension_to_format(ext):
    """
    Punch possible extensions into a common format string

     e.g.:

      .jpg -> jpg
      .JPG -> jpg
      jpe  -> jpg
      JPE  -> jpg
      JPEG -> jpg

    """
    sanitized_ext = sanitize_extension(ext)
    if not sanitized_ext:
        raise ValueError(f"Invalid extension: '{ext}'")
    if sanitized_ext in JPEG_EXTENSIONS:
        return "jpg"
    return sanitized_ext


def normalize_mimetype(ext):
    """
    Punch possible extensions into a common format string

     e.g.:

      .jpg -> jpeg
      .JPG -> jpeg
      jpe  -> jpeg
      JPE  -> jpeg
      JPEG -> jpeg

    """
    sanitized_ext = sanitize_extension(ext)
    if not sanitized_ext:
        raise ValueError(f"Invalid extension: '{ext}'")
    if sanitized_ext in JPEG_EXTENSIONS:
        return "jpeg"
    return sanitized_ext


def path_to_format(path):
    name, ext = os.path.splitext(os.path.basename(path))
    return extension_to_format(ext)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main index page"""
    return templates.TemplateResponse(request, "index.html")


@app.get("/placeholders/{filename}")
async def placeholder_it(
    filename: str,
    bg: str = Query(default="fff", description="Background color (hex without #)"),
    message: Optional[str] = Query(default=None, description="Custom message text")
):
    """Generate placeholder images"""
    try:
        bg = '#' + bg
        filename = filename.lower()
        basename, ext = os.path.splitext(filename)
        ext = ext.strip(".")
        
        # Parse dimensions from filename (e.g., "300x200.jpg")
        try:
            width, height = map(int, basename.split("x"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid filename format. Use WIDTHxHEIGHT.ext")
        
        content_type = f'image/{normalize_mimetype(ext)}'

        if ext in ('jpg', 'jpeg'):
            fmt = 'jpg'
        elif ext == 'png':
            fmt = 'png'
        else:
            raise HTTPException(status_code=404, detail=f"I don't know how to handle format .{ext} files")

        text = message if message else f'{width}x{height}'
        min_font_ratio = width / (len(text) * 12.0)
        size = max(16 * (height / 100), 16 * min_font_ratio)

        font = Font(path='fonts/Inconsolata-dz-Powerline.otf', size=size)
        c = Color(bg) if fmt == "jpg" else None
        
        with Image(width=width, height=height, background=c) as image:
            image.caption(text, left=0, top=0, font=font, gravity="center")
            buff = image_to_buffer(image, fmt=ext, compress=False)
            buff.seek(0)
            
            return Response(
                content=buff.read(),
                media_type=content_type,
                headers={"Cache-Control": CACHE_CONTROL}
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def generate_hmac(url):
    return hmac.new(SECRET.encode(), url.encode(), hashlib.sha1).hexdigest()


@app.get("/proxy/{image_hmac}")
async def proxy_that_stuff(
    image_hmac: str,
    url: str = Query(..., description="URL of the image to proxy")
):
    """
    Proxy external images with HMAC validation
    
    How do we handle non-ssl content image urls in the forums?
    The same way github does! Rewrite the img tags in the forums from:
        <img src="http://example.com/image.jpg">
    To:
        <img src="https://<giraffe>.cloudfront.net/proxy/<HMAC>?url=http://example.com/image.jpg">
    
    HMAC is a hash of a shared secret and the URL using SHA1.
    """
    if not url:
        raise HTTPException(status_code=404, detail="Oh noes, you didn't give me a url")
    
    # Verify HMAC
    expected_hmac = generate_hmac(url)
    if expected_hmac != image_hmac:
        raise HTTPException(status_code=404, detail="Oh noes, your key doesn't match!")

    # Validate the URL
    parsed_url = parse.urlparse(url)
    if parsed_url.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Invalid URL scheme. Only HTTP and HTTPS are allowed.")
    if parsed_url.hostname not in ALLOWED_DOMAINS:
        raise HTTPException(status_code=400, detail="URL domain is not allowed.")

    try:
        resp = requests.get(url)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(status_code=400, detail=f"Error fetching image: {str(e)}")
    
    content_type = resp.headers.get('content-type', 'image/jpeg')
    return Response(
        content=resp.content,
        media_type=content_type,
        headers={"Cache-Control": CACHE_CONTROL}
    )


@app.get("/{bucket}/{path:path}")
async def image_route(
    bucket: str,
    path: str,
    # Query parameters for image processing
    w: Optional[int] = Query(None, description="Width"),
    h: Optional[int] = Query(None, description="Height"),
    fit: Optional[str] = Query(None, description="Fit mode: crop, liquid"),
    flip: Optional[str] = Query(None, description="Flip: h, v, hv"),
    rot: Optional[int] = Query(None, description="Rotation in degrees"),
    fm: Optional[str] = Query(None, description="Format: jpg, png, eps"),
    q: Optional[int] = Query(None, description="Quality (1-100)"),
    bg: Optional[str] = Query(None, description="Background color"),
    overlay: Optional[str] = Query(None, description="Overlay path"),
    ox: Optional[int] = Query(None, description="Overlay X offset"),
    oy: Optional[int] = Query(None, description="Overlay Y offset"),
    ow: Optional[int] = Query(None, description="Overlay width"),
    oh: Optional[int] = Query(None, description="Overlay height"),
    force: Optional[bool] = Query(False, description="Force regeneration")
):
    """Main image processing route"""
    dirname = os.path.dirname(path)
    name = os.path.basename(path)
    
    try:
        base, ext = name.split(".")
    except ValueError:
        raise HTTPException(status_code=404, detail="no extension specified")

    # Build image processing arguments
    args = get_image_args({
        'w': w, 'h': h, 'fit': fit, 'flip': flip, 'rot': rot,
        'fm': fm, 'q': q, 'bg': bg, 'overlay': overlay,
        'ox': ox, 'oy': oy, 'ow': ow, 'oh': oh
    })
    
    if any(args.values()):
        param_name = calculate_new_path(dirname, base, ext, args)
        return await get_file_with_params_or_404(bucket, path, param_name, args, force)
    else:
        return await get_file_or_404(bucket, path)


def calculate_new_path(dirname, base, ext, args):
    stuff = [base,]
    for key, val in args.items():
        if key == "fm":
            continue
        if val is not None:
            if isinstance(val, str):
                # escape special characters in URLs for overlay / mask arguments
                val = parse.quote_plus(val)
            stuff.append("{}{}".format(key, val))

    fmt = args.get('fm')
    if fmt:
        ext = FORMAT_MAP[fmt]['extension']

    filename_with_args = "_".join(str(x) for x in stuff) + "." + ext
    # if we enable compression we may want to modify the filename here to include *.gz
    param_name = os.path.join(CACHE_DIR, dirname, filename_with_args)
    return param_name


def positive_int_or_none(value):
    try:
        value = int(value)
        if value >= 0:
            return value
        else:
            return None
    except ValueError:
        return None
    except TypeError:
        return None


def get_image_args(request_args):
    """Extract and validate image processing arguments"""
    image_args = OrderedDict()
    
    # Process each argument
    for key, value in request_args.items():
        if value is None:
            continue
            
        if key in ['w', 'h', 'rot', 'q', 'ox', 'oy', 'ow', 'oh']:
            processed_value = positive_int_or_none(value)
            if processed_value is not None:
                image_args[key] = processed_value
        elif key in ['fit', 'flip', 'fm', 'bg', 'overlay']:
            if value:
                image_args[key] = value
    
    return image_args


def get_object_or_none(bucket, path):
    try:
        obj = s3.get(path, bucket=bucket)
    except HTTPError as error:
        if error.response.status_code == 404:
            return None
        else:
            raise
    return obj


async def get_file_or_404(bucket, path):
    """Get file from S3 or raise 404"""
    key = get_object_or_none(bucket, path)
    if key:
        content_type = key.headers.get('content-type', 'image/jpeg')
        return Response(
            content=key.content,
            media_type=content_type,
            headers={"Cache-Control": CACHE_CONTROL}
        )
    else:
        raise HTTPException(status_code=404, detail=f"404: file '{path}' doesn't exist")


def overlay_that(img, bucket=None, path=None, overlay=None, bg=None, w=None, h=None, x=None, y=None):
    if bucket:
        key = get_object_or_none(bucket, path)
        overlay_content = key.content
    else:
        try:
            resp = requests.get(overlay)
        except (ConnectionError) as e:
            print(e)
            raise
        else:
            overlay_content = resp.content

    if overlay_content:
        if w is not None and h is not None and x is not None and y is not None:
            pass
        else:
            w, h, x, y = 294, 336, 489, 173

        image_orientation = 'square'
        overlay_orientation = 'square'

        if img.width > img.height:
            image_orientation = 'landscape'
        elif img.width < img.height:
            image_orientation = 'portrait'

        overlay_img = stubbornly_load_image(overlay_content, None, None)

        if overlay_img.width > overlay_img.height:
            overlay_orientation = 'landscape'
        elif overlay_img.width < overlay_img.height:
            overlay_orientation = 'portrait'

        overlay_width, overlay_height = overlay_img.width, overlay_img.height
        width, height = w, h
        size = f"{width}x{height}^"
        img.transform(resize=size)
        c = Color('#' + bg)
        background = Image(width=overlay_width, height=overlay_height, background=c)
        background.composite(img, x, y)
        img = background
        img.composite(overlay_img, 0, 0)
    else:
        raise Exception(f"Couldn't find an overlay file for bucket '{bucket}' and path '{path}' (overlay='{overlay}')")
    return img


def process_image(img, operations):
    for op in operations:
        if callable(op.function):
            img = op.function(img, **op.params)
        elif op.function == 'resize':
            if not op.params.get('width'):
                if img.animation:
                    width, height = img.size
                    img.resize(width, op.params['height'])
                else:
                    size = f"x{op.params['height']}"
                    img.transform(resize=size)
            elif not op.params.get('height'):
                if img.animation:
                    width, height = img.size
                    img.resize(op.params['width'], height)
                else:
                    size = f"{op.params['width']}"
                    img.transform(resize=size)
            else:
                if img.animation:
                    img.resize(op.params['width'], op.params['height'])
                else:
                    size = f"{op.params['width']}x{op.params['height']}^"
                    crop_size = f"{op.params['width']}x{op.params['height']}!"
                    img.transform(resize=size)
                    w_offset = max((img.width - op.params['width']) / 2, 0)
                    h_offset = max((img.height - op.params['height']) / 2, 0)
                    geometry = f"{crop_size}+{w_offset}+{h_offset}"
                    img.transform(crop=geometry)
        elif op.function == 'liquid':
            img.liquid_rescale(**op.params)
        elif op.function == 'flip':
            img.flip()
        elif op.function == 'flop':
            img.flop()
        elif op.function == 'format':
            img.format = op.params['format']
        elif op.function == 'rotate':
            img.rotate(op.params['degrees'])

    return img


def fit_crop(img, width=None, height=None, anchor=None):
    offset = ''
    if anchor == 'top':
        offset = ''
    crop = f"{width}x{height}{offset}"
    resize = ''
    img.transform(crop, resize)
    return img


def build_pipeline(params):
    pipeline = []
    if 'h' in params and 'w' in params:
        fit = params.get('fit')

        if fit == 'crop':
            anchor = params.get('crop', 'center').lower()
            pipeline.append(
                ImageOp(fit_crop, {
                        'width': params['w'],
                        'height': params['h'],
                        'anchor': anchor,
                        }
                )
            )
        elif fit == 'liquid':
            pipeline.append(
                ImageOp('liquid', {'width': params['w'],
                                   'height': params['h'],}
                        )
            )
        else:
            pipeline.append(
                ImageOp('resize', {'width': params['w'],
                                   'height': params['h'],}
                        )
            )
    elif 'h' in params:
        pipeline.append(
            ImageOp('resize', {'height': params["h"]})
        )
    elif 'w' in params:
        pipeline.append(
            ImageOp('resize', {'width': params["w"]})
        )

    flip = params.get('flip')
    if flip:
        if 'h' in flip:
            pipeline.append(
                ImageOp('flop', {})
            )
        if 'v' in flip:
            pipeline.append(
                ImageOp('flip', {})
            )

    rot = params.get('rot')
    if rot:
        rot = positive_int_or_none(rot)
        if rot is None or rot >= 360:
            raise HTTPException(status_code=400, detail=f'"{rot}" is not a valid rotation value')
        pipeline.append(ImageOp('rotate', {'degrees': int(rot)}))

    fm = params.get('fm')
    if fm:
        pipeline.append(ImageOp('format', FORMAT_MAP[fm]['format']))

    overlay = params.get('overlay')
    if overlay:
        bg = params.get('bg', '0FFF')
        segments = overlay.split("/")
        bucket = segments[1]
        path = "/" + "/".join(segments[2:])
        
        pipeline.insert(0, ImageOp(overlay_that, {
            'overlay': overlay,
            'bucket': bucket,
            'path': path,
            'bg': bg,
            'x': params.get('ox'),
            'y': params.get('oy'),
            'w': params.get('ow'),
            'h': params.get('oh'),
        }))
    return pipeline


def image_to_buffer(img, fmt='JPEG', compress=False):
    buff = BytesIO()
    img.format = fmt
    if compress:
        filename, mode, compresslevel, mtime = '', 'wb', 9, None
        gz = gzip.GzipFile(filename, mode, compresslevel, buff, mtime)
        img.save(file=gz)
    else:
        img.save(file=buff)
    return buff


def image_to_binary(img, fmt='JPEG'):
    return img.make_blob(fmt)

def stubbornly_load_image(content, headers, path):
    try:
        return Image(blob=BytesIO(content))
    except wand.exceptions.MissingDelegateError as orig_e:
        try:
            return Image(blob=BytesIO(content), format='ico')
        except wand.exceptions.MissingDelegateError:
            raise orig_e


async def get_file_with_params_or_404(bucket, path, param_name, args, force):
    """Get processed file or generate it"""
    key = get_object_or_none(bucket, path)
    if not key:
        raise HTTPException(status_code=404, detail=f"404: original file '{path}' doesn't exist")
    
    # Check for cached version unless force is True
    if not force:
        custom_key = get_object_or_none(bucket, param_name)
        if custom_key:
            content_type = custom_key.headers.get('content-type', "image/jpeg")
            return Response(
                content=custom_key.content,
                media_type=content_type,
                headers={"Cache-Control": CACHE_CONTROL}
            )
    
    # Generate new image
    width, height = get_image_size(key.content)
    
    # Check if original is too large
    if (width * height) > MAX_PIXELS:
        width = min(args.get('w', width), width)
        height = min(args.get('h', height), height)
        return await placeholder_it(f"{width}x{height}.jpg", bg="fff", message="TOO BIG")
    
    # Check if requested size is too large
    size = args.get('w', width), args.get('h', height)
    if (size[0] * size[1]) > MAX_PIXELS:
        return await placeholder_it("640x640.jpg", bg="fff", message="TOO BIG")
    
    # Process the image
    img = stubbornly_load_image(key.content, key.headers, path)
    fmt = img.format.lower()
    default_format = path_to_format(path)
    
    content_type = f"image/{normalize_mimetype(fmt)}"
    desired_format = args.get('fm', default_format)
    
    pipeline = build_pipeline(args)
    
    # Check if processing is needed
    if (size != (img.width, img.height) or 
        desired_format != fmt or 
        args.get('q') is not None or 
        len(pipeline) > 0):
        
        # Process image
        img.compression_quality = args.get('q', DEFAULT_QUALITY)
        processed_image = process_image(img, pipeline)
        fmt = processed_image.format.lower()
        content_type = f"image/{normalize_mimetype(desired_format)}"
        
        # Save to buffer
        temp_handle = image_to_buffer(processed_image, fmt=desired_format, compress=False)
        
        # Upload to S3 cache
        s3.upload(param_name, temp_handle, bucket=bucket, 
                 content_type=content_type, rewind=True, public=True)
        
        temp_handle.seek(0)
        return Response(
            content=temp_handle.read(),
            media_type=content_type,
            headers={"Cache-Control": CACHE_CONTROL}
        )
    else:
        # Return original
        return Response(
            content=key.content,
            media_type=content_type,
            headers={"Cache-Control": CACHE_CONTROL}
        )





# Development server
if __name__ == "__main__":
    import uvicorn
    if DEBUG:
        # Use import string for reload to work properly
        uvicorn.run("giraffe:app", host="0.0.0.0", port=9876, reload=True, log_level="debug")
    else:
        # Use app object directly for production
        uvicorn.run(app, host="0.0.0.0", port=9876, log_level="info")

