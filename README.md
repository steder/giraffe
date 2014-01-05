# Giraffe

Image pipelines are hard; let's go ride bikes!

## WTF?

The names will change.

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
<img src="http://hash.cloudfront.net/profile_pictures/1.jpg?w=100&h=100"
     alt="profile pic" title="user_1" />
```

The request will hit `cloudfront` (at `hash.cloudfront.com`), which will turn around and hit your origin at `images.example.com`.  `giraffe` will check for an image `/profile_pictures/1.jpg`, if that exists it'll then check for the requested size image at `/cache/profile_pictures/1_100_100.jpg` in `s3://media.example.com`.  If it finds it
it will simply return it, otherwise it'll use the original to generate the
`cache` prefixed resized version.

## Supported URL Parameters

### Resizing

 - w, h
 - fit: controls how the output image is fitted to its target dimensions.  Valid values for `fit` include:
  - crop (resize to fill width and height and crop any excess)
  - liquid (resize with liquid rescaling / content-aware resizing / seam carving)
 - crop: controls how the input is aligned when `fit=crop`.  Valid values for `crop` include:
  - <unset>: crop to the center
  - top (TBD)
  - bottom (TBD)
  - left (TBD)
  - right (TBD)
 - flip (flip horizontally `flip=h`, vertically `flip=v` or both `flip=hv`)

## Setup

### Dependencies

At a system level you'll need:
 - `Python` (2.7, 3.3+, or pypy)
 - `ImageMagick` (remember to use `--with-liblqr` if you want to be able to use content-aware resizing)

For deployment with Gunicorn you may also want `libev`.

### Development

```
mkvirtualenv giraffe
pip install -r requirements.txt
```

#### Testing

```
nosetests
OR
tox
```

### Deployment

Check out `install.sh`

## TODO

 - cache-control headers
 - png support

![travis ci builid status](https://travis-ci.org/steder/giraffe.png)
