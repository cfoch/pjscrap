# -*- coding: utf-8 -*-
import argparse
import mimetypes
import os
import sys
import tempfile
from enum import auto
from enum import Enum

import magic
from PIL import Image
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def print_log_summary(expediente, retries, n_downloads, error_message,
                      output_file=sys.stderr):
    if error_message:
        print("Expediente: %s. Retries: %d. Error: %s" %
              (expediente, retries, error_message), file=output_file)
    else:
        print("Expediente: %s. Retries: %d. Success. Downloads: %d" %
              (expediente, retries, n_downloads), file=output_file)


if __name__ == "__main__":

    if "pjscrap" not in sys.modules:
        root_dir = \
            os.path.abspath(os.path.join(os.path.os.getcwd(), os.pardir))
        sys.path.append(root_dir)
        from pjscrap.utils import setup_ssl
        from pjscrap.cej import CejScraper

    parser = argparse.ArgumentParser()

    parser.add_argument("--headless",
                        action="store_true",
                        required=False)
    parser.add_argument("-i", "--input",
                        type=argparse.FileType("r"),
                        help="Archivo con lista de códigos de expediente",
                        required=True)
    parser.add_argument("-r", "--retries",
                        type=int,
                        default=10,
                        help="Output folder path",
                        required=False)
    parser.add_argument("-o", "--output",
                        help="Output folder path",
                        required=True)
    parser.add_argument("-f", "--force",
                        action="store_true",
                        required=False)
    parser.add_argument("-d", "--debug",
                        action="store_true",
                        required=False)
    parser.add_argument("-s", "--silent",
                        action="store_true",
                        required=False)
    parser.add_argument("--log-dir",
                        required=False)

    args = parser.parse_args()

    setup_ssl()

    options = Options()
    options.headless = args.headless
    driver = webdriver.Firefox(options=options)

    cej_scraper = CejScraper(driver, args.debug)

    for line in args.input.readlines():
        expediente = line.strip()
        if not expediente:
            continue

        output_dir = os.path.abspath(os.path.join(args.output, expediente))
        _, _, retries, n_downloads =\
            cej_scraper.run(expediente, output_dir, args.force, args.retries)

        if not args.silent:
            print_log_summary(expediente, retries, n_downloads,
                              cej_scraper.error_message)

        if args.log_dir:
            log_path = os.path.join(args.log_dir, "%s.log" % expediente)
            with open(log_path, "w") as log_file:
                print_log_summary(expediente, retries, n_downloads,
                                  cej_scraper.error_message, log_file)
                print(cej_scraper.log, file=log_file)

    driver.quit()
