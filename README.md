# Giraffe

Image pipelines are hard; let's go ride bikes!

This is partly a reaction to looking at the imgix service, which is "not just imagemagick on ec2", and saying that "imagemagick on ec2" sounds an awful lot like something I actually want.

More specifically, this started out as something to help out the design team and ended up replacing a venerable set of cronjobs that copied images from all over, resized them, and uploaded dozens of variants to S3.

Instead, we moved to uploading original images to S3 and letting the resizing, overlays, etc happen dynamically in Giraffe.

![travis ci build status](https://travis-ci.org/steder/giraffe.png)

## Why call it Giraffe?

I wanted a name with a soft G sound and I didn't have any better ideas.  

## About

`giraffe` is an image processing proxy with the immediate
goal of being placed between an S3 bucket and a cloudfront distribution.

`giraffe` allows you to store your high-quality original images on S3 and
do any resizing, cropping, filters, etc on demand by simply adding query
parameters to the URL for the original image.

### Overview of architecture:

You store original images in an s3 bucket.  Something like:

```
s3://media.example.com/profile_pictures/1.jpg
```

You set up `giraffe` in `ec2` behind an `elb`, point dns (e.g.: `images.example.com`) at it, and configure it to point to your bucket.

Finally set up a new `cloudfront` distribution (e.g.: `hash.cloudfront.net`) to sit
in front of `images.example.com` and be sure to set it to forward query strings
to origin.

### Example

Assuming your image `1.jpg` above is a 1080p image and you'd really like to just display a 100x100 thumbnail next to `user_1`'s comments you can do so easily by simply including the following in your markup:

```
<img src="http://hash.cloudfront.net/media.example.com/profile_pictures/1.jpg?w=100&h=100"
     alt="profile pic" title="user_1" />
```

The request will hit `cloudfront` (at `hash.cloudfront.com`), which will turn around and hit your origin at `images.example.com`.  `giraffe` will check for an image `/profile_pictures/1.jpg`, if that exists it'll then check for the requested size image at `/cache/profile_pictures/1_100_100.jpg` in `s3://media.example.com`.  If it finds it
it will simply return it, otherwise it'll use the original to generate the
`cache` prefixed resized version.

## Supported URLs / Resources

 - Test UI: `/`
 - Generate and retrieve a placeholder image: `/placeholders/<placeholder name>`
 - Proxy a remote image ala atmos: `/proxy/<HMAC>?url=<URL>`
 - Retrieve an image with resizing: `/<bucket>/<path>`
 
### Placeholder Images
 
Generates an image with simple placeholder text.  Typically a simple box with the image size (e.g.: `WxH`) as text inside it.

Supported params:

 - bg: set the background color with an RGB value (defaults to 'fff' for white backgrounds)

### Resizing

`/<bucket>/path?w=1024&h=768`

Supported params:

 - w, h: width and height
 - fit: controls how the output image is fitted to its target dimensions.  Valid values for `fit` include:
  - crop (resize to fill width and height and crop any excess)
  - liquid (resize with liquid rescaling / content-aware resizing / seam carving)
 - crop: controls how the input is aligned when `fit=crop`.  Valid values for `crop` include:
   * <unset>: crop to the center
   * top (TBD)
   * bottom (TBD)
   * left (TBD)
   * right (TBD)
 - flip (flip horizontally `flip=h`, vertically `flip=v` or both `flip=hv`)
 - rot (rotate, 1-359 degrees)
 - q: decimal percent quality setting, defaults to 75 (aka 75%)
 - overlay: path to a file in the current s3 bucket to use as an overlay
 - ox: offset to the X position of the overlay
 - oy: offset to the Y position of the overlay
 - ow: width to scale the overlay to before compositing it with your base image
 - oh: ditto above but for height
 - bg: background color to use when overlaying images (useful for grayscale images with transparency)

## Setup

### Dependencies

At a system level you'll need:
 - `Python` (3.7+, or pypy3)
 - `ImageMagick` (remember to use `--with-liblqr` if you want to be able to use content-aware resizing)

For deployment with Gunicorn you may also want `libev`.

### Configuration

You need to set the following environment variables for giraffe to work properly:

 - AWS_ACCESS_KEY_ID
 - AWS_SECRET_ACCESS_KEY

### Development

```
mkvirtualenv giraffe
pip install -r requirements.txt
```

#### Testing

```
pytest
```

### Deployment

Check out `install.sh`

## Docker

You can now use docker to build and deploy.  Simply do:

    docker run -d -p 9876:9876 -e AWS_ACCESS_KEY_ID=<your access key> -e AWS_SECRET_ACCESS_KEY=<your secret access key> steder/giraffe

## TODO

 - documentation of camo functionality (proxying insecure image URLs like [atmos/camo](https://github.com/atmos/camo)
 - documentation of placeholder functionality
 - support more imgix functionality
 - better caching: memcache caching of images is problematic; memcache complains about caching values over 1MB and it is sadly quite easy to do.

## Sites

 - Threadless.com
 - Typetees.com
