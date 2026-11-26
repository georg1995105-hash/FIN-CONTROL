"""One real-image diagnostic, not a validated object counter."""
import cv2
import hashlib
import json
import numpy as np
from skimage import data, __version__ as skimage_version


def detect(image, sensitivity):
    circles = cv2.HoughCircles(cv2.medianBlur(image, 5), cv2.HOUGH_GRADIENT,
                              1, 25, param1=100, param2=sensitivity,
                              minRadius=12, maxRadius=34)
    return 0 if circles is None else len(circles[0])


def main():
    original = data.coins()
    variants = {
        "original": original,
        "blur": cv2.GaussianBlur(original, (5, 5), 1.3),
        "dark": np.uint8(original.astype(np.float32) * 0.65),
        "contrast": np.uint8(np.clip((original.astype(np.float32) - 128) * 0.65 + 128, 0, 255)),
    }
    result = {"opencv": cv2.__version__, "skimage": skimage_version,
              "image_sha256": hashlib.sha256(original.tobytes()).hexdigest(),
              "shape": list(original.shape), "reference_count": 24,
              "independent_images": 1,
              "counts": {name: {str(p): detect(image, p) for p in (20, 25, 30, 35, 40)}
                         for name, image in variants.items()}}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
