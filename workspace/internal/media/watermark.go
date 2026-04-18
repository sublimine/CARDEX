package media

import (
	"fmt"
	"image"
	"image/color"
	"image/draw"
	"image/jpeg"
	"image/png"
	"os"
	"path/filepath"
	"strings"

	"github.com/disintegration/imaging"
)

const defaultOpacity = 0.40

// Watermarker holds a dealer logo and applies it to the web variant.
type Watermarker struct {
	logo    image.Image
	opacity float64 // 0.0–1.0
}

// NewWatermarker creates a Watermarker with the given logo and opacity.
func NewWatermarker(logo image.Image, opacity float64) *Watermarker {
	return &Watermarker{logo: logo, opacity: opacity}
}

// LoadFromFile loads a PNG or JPEG logo file and returns a Watermarker with
// default opacity. If the file does not exist, nil is returned without error so
// callers can skip watermarking gracefully.
func LoadFromFile(path string) (*Watermarker, error) {
	if _, err := os.Stat(path); os.IsNotExist(err) {
		return nil, nil
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("watermark open: %w", err)
	}
	defer f.Close()

	var logo image.Image
	ext := strings.ToLower(filepath.Ext(path))
	switch ext {
	case ".png":
		logo, err = png.Decode(f)
	case ".jpg", ".jpeg":
		logo, err = jpeg.Decode(f)
	default:
		logo, err = imaging.Decode(f)
	}
	if err != nil {
		return nil, fmt.Errorf("watermark decode: %w", err)
	}
	return NewWatermarker(logo, defaultOpacity), nil
}

// Apply composites the logo onto the bottom-right corner of img at the
// configured opacity and returns the result. If w is nil the original image is
// returned unchanged.
func (w *Watermarker) Apply(img image.Image) image.Image {
	if w == nil || w.logo == nil {
		return img
	}

	bounds := img.Bounds()
	logoB := w.logo.Bounds()

	// Scale the logo to ≤25% of image width.
	maxLogoW := bounds.Dx() / 4
	scaled := w.logo
	if logoB.Dx() > maxLogoW {
		scaled = imaging.Resize(w.logo, maxLogoW, 0, imaging.Lanczos)
		logoB = scaled.Bounds()
	}

	// Position: bottom-right with 16 px padding.
	const pad = 16
	dx := bounds.Max.X - logoB.Dx() - pad
	dy := bounds.Max.Y - logoB.Dy() - pad
	offset := image.Pt(dx, dy)

	// Composite with per-pixel alpha mask.
	dst := image.NewNRGBA(bounds)
	draw.Draw(dst, bounds, img, bounds.Min, draw.Src)
	draw.DrawMask(dst, logoB.Add(offset), scaled, logoB.Min,
		&alphaMask{alpha: uint8(w.opacity * 255)}, image.Point{}, draw.Over)

	return dst
}

// alphaMask is a uniform alpha mask that scales the alpha channel of every
// pixel by a constant factor, implementing the image.Image interface.
type alphaMask struct {
	alpha uint8
}

func (m *alphaMask) ColorModel() color.Model { return color.AlphaModel }
func (m *alphaMask) Bounds() image.Rectangle { return image.Rectangle{Max: image.Pt(1<<15, 1<<15)} }
func (m *alphaMask) At(_, _ int) color.Color  { return color.Alpha{A: m.alpha} }
