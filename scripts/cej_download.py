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


def print_skip_summary(expediente, output_file=sys.stderr):
    print("Expediente: %s. Skip.", file=output_file)


def print_error_summary(expediente, cej_scraper, retries, n_downloads,
                        output_file=sys.stderr):
    if cej_scraper.error_message:
        msg = "Expediente: %s. Retries: %d. Error: %s"
        msg %= (expediente, retries, cej_scraper.error_message)
    else:
        msg = "Expediente: %s. Retries: %d. Success. Downloads: %d"
        msg %= (expediente, retries, n_downloads)

    print(msg, file=output_file)


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
    parser.add_argument("--skip-existing-dir",
                        action="store_true",
                        required=False)
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
        log_path = os.path.join(args.log_dir, "%s.log" % expediente)
        if args.skip_existing_dir and os.path.exists(output_dir):
            if not args.silent:
                print_skip_summary(expediente)
            if args.log_dir:
                with open(log_path, "w") as log_file:
                    print_skip_summary(expediente, log_file)

        _, _, retries, n_downloads =\
            cej_scraper.run(expediente, output_dir, args.force, args.retries)

        if not args.silent:
            print_error_summary(expediente, cej_scraper, retries, n_downloads)

        if args.log_dir:
            with open(log_path, "w") as log_file:
                print_error_summary(expediente, cej_scraper, retries,
                                    n_downloads, log_file)
                if cej_scraper.log:
                    print(cej_scraper.log, file=log_file)

    driver.quit()
