# -*- coding: utf-8 -*-
# pylint: disable=missing-module-docstring
import cv2
import numpy as np
import pytesseract
from PIL import Image


def solve(path, show_process=False):
    def _try_display():
        if show_process:
            cv2.imshow('img', img)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

    img = cv2.imread(path)
    img = img[0:, 10:]
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _try_display()

    _, img = cv2.threshold(img, 150, 255, cv2.THRESH_BINARY)
    _try_display()

    img = cv2.bitwise_not(img)
    _try_display()

    kernel = np.ones((4, 4), np.uint8)
    img = cv2.erode(img, kernel, iterations=1)
    _try_display()

    img = cv2.copyMakeBorder(img, 10, 10, 10, 10, cv2.BORDER_CONSTANT,
                             value=[255, 0, 0])
    _try_display()

    img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_GRAY2RGB))

    config_args = " ".join([
        "--psm", "13",
        "--oem", "2",
        "-c", "tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNPQRTUVWXYZ"
    ])
    text = pytesseract.image_to_string(img, config=config_args).upper()

    return text.strip()
