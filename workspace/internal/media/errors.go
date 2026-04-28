package media

import "errors"

var (
	ErrFileTooLarge       = errors.New("media: file exceeds maximum allowed size")
	ErrUnsupportedFormat  = errors.New("media: unsupported image format")
	ErrNoPhotos           = errors.New("media: no photos provided")
	ErrPhotoNotFound      = errors.New("media: photo not found")
)
