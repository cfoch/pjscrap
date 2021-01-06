# -*- coding: utf-8 -*-
import argparse
import io
import os
import sys
import tempfile
import traceback
from enum import auto
from enum import Enum

import requests
from bs4 import BeautifulSoup
from PIL import Image
from requests.exceptions import RequestException
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from pjscrap import captcha
from pjscrap.utils import check_valid_file
from pjscrap.utils import download_with_driver
from pjscrap.utils import download_with_session
from pjscrap.utils import get_request_session


BASE_URL = "https://cej.pj.gob.pe/cej/"
TARGET_URL = "https://cej.pj.gob.pe/cej/forms/busquedaform.html"
CAPTCHA_URL = "https://cej.pj.gob.pe/cej/Captcha.jpg"
CEJ_FULL_SCREENSHOT_PATH =\
    os.environ.get("CEJ_FULL_SCREENSHOT_PATH") or "/tmp/pj_ce.png"
CEJ_CAPTCHA_SCREENSHOT_PATH =\
    os.environ.get("CEJ_CAPTCHA_SCREENSHOT_PATH") or "/tmp/pj_ce_captcha.png"


class Tab(Enum):
    FILTRO = auto()
    CODIGO = auto()


class CejScraperSimple:
    def __init__(self, session, expediente, debug):
        self.session = session
        self.expediente = expediente
        self.debug = debug
        self.error_message = ""
        self.log = ""

    def run(self, output_dir, force, retries, should_reload=False):
        try:
            return self.__run(output_dir, force, retries, should_reload)
        except Exception:
            self.log += traceback.format_exc()
            traceback.print_exc()
            ret = self._run(output_dir, force, retries - 1, should_reload)
        return ret

    def __run(self, output_dir, force, retries,
              should_reload):
        should_continue, should_reload, retries = self._input_captcha(retries)

        if should_continue:
            if should_reload:
                should_continue, should_reload, retries, n_downloads = \
                    self.__run(output_dir, force, retries, should_reload)
            if should_continue and (not should_reload) and retries > 0:
                n_downloads = self._download_resoluciones(output_dir, force)
                return False, False, retries, n_downloads

        return should_continue, should_reload, retries, n_downloads

    def _input_captcha(self, retries):
        if retries == 0:
            return False, False, 0

        res = self.session.get(CAPTCHA_URL)
        captcha_img = Image.open(io.BytesIO(res.content))
        decoded_captcha = captcha.solve(captcha_img, self.debug)

        base_data = self._get_base_request_data()
        extra_data = {
            "navegador": "Chrome--87",
            "divKcha": "0",
            "sCUJ": "",
            "codigoCaptcha": decoded_captcha,
        }

        data = dict(base_data, **extra_data)
        url = os.path.join(BASE_URL, "forms/ValidarFiltrosCodigo.htm")

        try:
            res = self.session.post(url, data=data)
        except RequestException as ex:
            self.error_message =\
                "Captcha request raised an exception message: %s" % ex
            return False, False, retries - 1

        if res.status_code != 200:
            self.error_message =\
                "Captcha request returned with status code %d" % res.status_code
            self.log += "%s\n" % self.error_message
            return retries != 0, True, retries - 1

        try:
            result = res.content.decode("utf-8")
        except UnicodeError:
            pass

        if result == "-CV":
            front_end_msg = "Captcha enviado incorrecto, REFRESQUE LA PAGINA"
        elif result == "-CM":
            front_end_msg = ("Problemas con el Captcha, de ser reiterativo "
                             "REFRESQUE LA PAGINA")
        elif result == "-C":
            front_end_msg = "Ingrese el Codigo de Captcha Correcto"
        elif result == "2":
            front_end_msg = ("No se encontraron registros con con los datos "
                             "ingresados")
        elif result != "1":
            front_end_msg = "Unknown error"
        else:
            front_end_msg = ""

        if front_end_msg:
            error_msg_tmpl = "Captcha request returned '%s'. It may lead to: %s"
            self.error_message = error_msg_tmpl % (result, front_end_msg)
            self.log += "%s\n" % self.error_message
        else:
            self.error_message = ""

        if result == "-C":
            return self._input_captcha(retries - 1)
        elif result == "2":
            return False, False, retries - 1
        elif result != "1":
            return retries != 0, True, retries - 1

        return retries != 0, False, retries - 1

    def _get_base_request_data(self):
        sub_codes = self.expediente.split("-")
        input_ids = ("cod_expediente", "cod_anio", "cod_incidente",
                     "cod_distprov", "cod_organo", "cod_especialidad",
                     "cod_instancia")
        return dict(zip(input_ids, sub_codes))

    def _download_resoluciones(self, output_dir, force):
        if not force and check_valid_file(output_dir):
            return

        data = self._get_base_request_data()
        headers = {
            "Cookie": "JSESSIONID=%s" % self.session.cookies.get("JSESSIONID"),
        }
        url = os.path.join(BASE_URL, "forms/busquedacodform.html")
        res = self.session.post(url, data=data, headers=headers)

        soup = BeautifulSoup(res.content, "html.parser")
        main_div = soup.find("div", {"id": "divDetalles"})

        nro_registro = None
        for div in main_div:
            b_ = div.find("b")
            if b_ != -1 and b_.text == self.expediente:
                nro_registro = div.find("input").get("value")
                break

        data = {"nroRegistro": int(nro_registro)}
        url = os.path.join(BASE_URL, "forms/detalleform.html")
        res = self.session.post(url, data=data, headers=headers)

        soup = BeautifulSoup(res.content, "html.parser")
        link_tags = soup.findAll("a", {"class": "aDescarg"})

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        for tag in link_tags:
            url = os.path.join(BASE_URL, "forms", tag.get("href"))
            download_with_session(self.session, output_dir, url, force)

        if not link_tags:
            os.rmdir(output_dir)
        return len(link_tags)


class CejScraper:
    def __init__(self, firefox_driver, debug):
        self.driver = firefox_driver
        self.debug = debug
        self.error_message = ""
        self.log = ""

    def run(self, expediente, output_dir, force, retries, should_reload=False):
        self.error_message = ""
        self.log = ""
        return self._run(expediente, output_dir, force, retries, should_reload)

    def _run(self, expediente, output_dir, force, retries, should_reload):
        try:
            ret = self.__run(expediente, output_dir, force, retries,
                             should_reload)
        except Exception:
            self.log += traceback.format_exc()
            traceback.print_exc()
            ret = self._run(expediente, output_dir, force, retries - 1,
                            should_reload)
        return ret

    def __run(self, expediente, output_dir, force, retries, should_reload):
        self._log_retries(retries)
        if retries == 0:
            return False, False, 0, 0

        self.driver.delete_all_cookies()
        if not should_reload:
            self.driver.get(TARGET_URL)
        else:
            self.driver.refresh()

        self._click_tab(Tab.CODIGO)
        self._input_codigo_expediente(expediente)
        should_continue, should_reload, retries = self._input_captcha(retries)

        if should_continue:
            if should_reload:
                should_continue, should_reload, retries, _ = \
                    self.__run(expediente, output_dir, force, retries,
                               should_reload)
            if should_continue and (not should_reload) and retries > 0:
                self._click_lupa(expediente)
                n_downloads = self._download_resoluciones(output_dir, force)
                return False, False, retries, n_downloads

        return should_continue, should_reload, retries, 0

    def _log_retries(self, retries):
        self.log += "Retry: %d\n" % retries

    def _click_tab(self, tab):
        if tab != Tab.CODIGO:
            raise NotImplementedError()

        elm = self.driver.find_element_by_id("myTab")
        elm.click()

    def _input_codigo_expediente(self, cod_exp):
        sub_codes = cod_exp.split("-")
        input_ids = ("cod_expediente", "cod_anio", "cod_incidente",
                     "cod_distprov", "cod_organo", "cod_especialidad",
                     "cod_instancia")

        for input_id, sub_cod in zip(input_ids, sub_codes):
            elm = self.driver.find_element_by_id(input_id)
            elm.send_keys(sub_cod)

    def _extract_captcha_to_filename(self, elm, captcha_output):
        x, y = elm.location['x'], elm.location['y']
        w, h = elm.size['width'], elm.size['height']

        self.driver.execute_script("window.scrollTo(0, 0)")
        self.driver.save_screenshot(CEJ_FULL_SCREENSHOT_PATH)

        img = Image.open(CEJ_FULL_SCREENSHOT_PATH)
        img = img.crop((int(x), int(y), int(x + w), int(y + h)))
        img.save(captcha_output)

    def _input_captcha(self, retries):
        if retries == 0:
            return False, False, 0

        self.driver.execute_script("window.scrollTo(0, 0)")

        WebDriverWait(self.driver, 3).until(
            EC.visibility_of_element_located((By.ID, "captcha_image")))
        elm = self.driver.find_element_by_id("captcha_image")

        self.driver.save_screenshot(CEJ_FULL_SCREENSHOT_PATH)

        x, y = elm.location['x'], elm.location['y']
        w, h = elm.size['width'], elm.size['height']

        img = Image.open(CEJ_FULL_SCREENSHOT_PATH)
        img = img.crop((int(x), int(y), int(x + w), int(y + h)))
        img.save(CEJ_CAPTCHA_SCREENSHOT_PATH)

        decoded_captcha = captcha.solve(CEJ_CAPTCHA_SCREENSHOT_PATH, self.debug)
        elm = self.driver.find_element_by_id("codigoCaptcha")
        elm.send_keys(decoded_captcha)

        elm = self.driver.find_element_by_id("consultarExpedientes")
        elm.click()

        os.remove(CEJ_FULL_SCREENSHOT_PATH)
        os.remove(CEJ_CAPTCHA_SCREENSHOT_PATH)

        try:
            selector = "#codCaptchaError, #mensajeNoExisteExpedientes"
            WebDriverWait(self.driver, 1).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, selector)))
        except TimeoutException:
            pass

        elm = None
        for id_ in ("codCaptchaError", "mensajeNoExisteExpedientes"):
            try:
                _e = self.driver.find_element_by_id(id_)
                if _e and _e.is_displayed():
                    elm = _e
                    break
            except NoSuchElementException:
                pass

        if elm is not None:
            self.error_message = elm.text.strip()
            if self.error_message:
                self.log += "%s\n" % self.error_message

            if "REFRESQUE LA PAGINA" in self.error_message:
                return retries != 0, True, retries - 1

            if "No se encontraron registros con" in self.error_message:
                return False, False, retries - 1
            else:
                self._log_retries(retries - 1)
                return self._input_captcha(retries - 1)

        self.error_message = ""
        return retries != 0, False, retries - 1

    def _click_lupa(self, cod_exp):
        WebDriverWait(self.driver, 3).until(
            EC.presence_of_element_located((By.ID, "divDetalles")))
        main_div = self.driver.find_element_by_id("divDetalles")
        children_divs = main_div.find_elements_by_xpath("div")

        target_class = None
        for child_div in children_divs:
            cod_exp_text = child_div.find_element_by_tag_name("b").text
            if cod_exp_text == cod_exp:
                target_class = child_div.get_attribute("class").split()[0]
                break

        if target_class is None:
            raise Exception

        target_div = \
            self.driver.find_elements_by_css_selector(".%s" % target_class)[0]
        target_button = target_div.find_elements_by_tag_name("button")[0]
        target_button.click()

    def _download_resoluciones(self, output_dir, force):
        if not force and check_valid_file(output_dir):
            return

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        download_buttons = self.driver.find_elements_by_class_name("aDescarg")
        for download_button in download_buttons:
            url = download_button.get_attribute("href")
            download_with_driver(self.driver, output_dir, url, force)

        if not download_buttons:
            os.rmdir(output_dir)

        return len(download_buttons)
