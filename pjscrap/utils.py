# -*- coding: utf-8 -*-
import cgi
import os

import magic
import requests
import urllib3


def get_request_session(driver):
    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'])

    return session


def setup_ssl():
    requests.packages.urllib3.disable_warnings()
    requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS += ':HIGH:!DH:!aNULL'
    try:
        settings = requests.packages.urllib3.contrib.pyopenssl.util.ssl_
        settings.DEFAULT_CIPHERS += ':HIGH:!DH:!aNULL'
    except AttributeError:
        # no pyopenssl support used / needed / available
        pass


def download(driver, output_dir, url, force, chunk_size=2048):
    session = get_request_session(driver)
    r = session.get(url, stream=True)

    _, params = cgi.parse_header(r.headers["Content-disposition"])
    output_filename = os.path.join(output_dir, params["filename"])

    with open(output_filename, "wb") as f:
        for chunk in r.iter_content(chunk_size):
            f.write(chunk)


def check_valid_file(path):
    if not os.path.exists(path) or not os.path.isfile(path):
        return False

    mime = magic.Magic(mime=True)
    mimetype = mime.from_file(path)
    if mimetype == "application/pdf":
        import PyPDF2
        with open(path, "rb") as f:
            try:
                PyPDF2.PdfFileReader(f)
            except PyPDF2.utils.PdfReadError:
                return False
    elif mimetype == "application/msword":
        import docx
        try:
            docx.Document(path)
        except docx.opc.exceptions.PackageNotFoundError:
            return False
    return True
