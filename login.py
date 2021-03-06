# -*- coding: utf-8 -*-
# 14/10/15
# create by: snower

import os
import sys
import time
import json
import hashlib
from cStringIO import StringIO
import argparse
import threading
import requests
import logging
import signal
import Queue
from PIL import Image
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from tornado.ioloop import IOLoop
from tornado.web import Application, RequestHandler
from tornado import gen

def str2bool(v):
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

parser = argparse.ArgumentParser(description='audo login alimama')
parser.add_argument('-u', dest='username', help='alimama username')
parser.add_argument('-p', dest='password', help='alimama password')
parser.add_argument('-c', dest='client_id', default='', help='alimama client_id')
parser.add_argument('-i', dest='index_url', default="http://pub.alimama.com/myunion.htm", help='login index url')
parser.add_argument('-H', dest='bind_host', default='0.0.0.0', help='api bing host (default: 0.0.0.0)')
parser.add_argument('-P', dest='bind_port', default=0, type=int, help='api bing port (default: 0) if port is 0, it will not bind')
parser.add_argument('-s', dest='session_filename', default="cookies.json", help='session cookies save fileame (default: cookies.json)')
parser.add_argument('-o', dest='cookies_fileanme', default='', help='login cookies output fileame (default: stdout)')
parser.add_argument('-D', dest='demon_mod', default=False, type=str2bool, nargs='?', const=True, help='demon')
parser.add_argument('-t', dest='refresh_time', default=900, type=int, help='refresh time (default: 900s)')
parser.add_argument('-O', dest='log_filename', default='', help='log_filename (default: stdout)')

args = parser.parse_args()

username = args.username
password = args.password
success_url = args.index_url
bind_host = args.bind_host
bind_port = args.bind_port
session_filename = os.path.abspath(args.session_filename)
cookies_fileanme = args.cookies_fileanme or ''
demon_mod = args.demon_mod
refresh_time = args.refresh_time
log_filename = args.log_filename
client_id = args.client_id

if isinstance(username, str):
    username = username.decode("utf-8")

if isinstance(password, str):
    password = password.decode("utf-8")

if isinstance(success_url, str):
    success_url = success_url.decode("utf-8")

if cookies_fileanme:
    cookies_fileanme = os.path.abspath(cookies_fileanme)

if log_filename:
    log_filename = os.path.abspath(log_filename)

class QRcode:
    def __init__(self, image, width=33, height=33):
        self.image = image
        self.width = width
        self.height = height
        self.white_block = '\033[0;37;47m   '
        self.black_block = '\033[0;37;40m   '
        self.new_line = '\033[0m\n'

    def show(self):
        img = Image.open(self.image)
        img = img.resize((self.width, self.height), Image.NEAREST)
        img = img.convert('L')
        text = self.white_block * (self.width + 4) + self.new_line
        text += self.white_block * (self.width + 4) + self.new_line
        for w in range(self.width):
            text += self.white_block * 2
            for h in range(self.height):
                res = img.getpixel((h, w))
                text += self.white_block if res >= 128 else self.black_block
            text += self.white_block * 2 + self.new_line
        text += self.white_block * (self.width + 4) + self.new_line
        text += self.white_block * (self.width + 4) + self.new_line
        return text

class Spider(object):
    def __init__(self):
        self.web_options = webdriver.ChromeOptions()
        self.web_options.add_argument('--headless')
        self.web_options.add_argument('--disable-gpu')
        self.web = webdriver.Chrome(chrome_options=self.web_options)
        self.web.set_window_size(1920, 980)
        self.cookies = ''
        self.login_succed = False
        self.session = {}
        self.last_J_QRCodeImg_url = ''

    def get_user_id(self):
        return hashlib.md5(username.encode("utf-8")).hexdigest()

    def load_cookies(self):
        try:
            with open(session_filename) as fp:
                session = json.load(fp)
                user_id = self.get_user_id()
                if user_id in session:
                    cookies = session[user_id]
                    self.web.get("https://my.taobao.com/my_taobao.htm")
                    for cookie in cookies["login.taobao.com"]:
                        self.web.add_cookie(cookie)
                    self.web.get("http://pub.alimama.com/")
                    for cookie in cookies["pub.alimama.com"]:
                        self.web.add_cookie(cookie)
                    logging.info('load cookies')
        except Exception as e:
            logging.info('load cookies error %s', e)

    def save_cookies(self):
        user_id = self.get_user_id()

        session = {}
        try:
            with open(session_filename) as fp:
                session = json.load(fp)
                if not dict(session):
                    session = {}
        except Exception as e:
            pass

        cookies = {}
        self.web.get("https://my.taobao.com/my_taobao.htm")
        cookies["login.taobao.com"] = self.web.get_cookies()
        self.web.get("http://pub.alimama.com/")
        cookies["pub.alimama.com"] = self.web.get_cookies()

        session[user_id] = cookies
        with open(session_filename, "w") as fp:
            json.dump(session, fp)

        fcookies = []
        for cookie in cookies["pub.alimama.com"]:
            fcookies.append("%s=%s" % (cookie["name"], cookie["value"]))
        self.cookies = ";".join(fcookies)

        if not cookies_fileanme:
            logging.info('\n\n' + '*' * 8 + "COOKIES" + "*" * 8 + '\n' + self.cookies + '\n' + '*' * 8 + "COOKIES" + "*" * 8 + "\n\n")
        else:
            try:
                with open(cookies_fileanme, "w") as fp:
                    fp.write(self.cookies.encode("utf-8"))
            except Exception as e:
                logging.info("output error %s", e)
        logging.info('save cookies')

    def show_qrcode(self):
        logging.info('checking login qrcode displayed')
        J_QRCodeImg = self.web.find_element_by_id('J_QRCodeImg')
        while not J_QRCodeImg.is_displayed():
            time.sleep(0.05)

        logging.info('checking login qrcode image loaded')
        J_QRCodeImg_url = ''
        while not J_QRCodeImg_url:
            J_QRCodeImg = J_QRCodeImg.find_element_by_tag_name("img")
            while not J_QRCodeImg.is_displayed():
                time.sleep(0.05)
            J_QRCodeImg_url = J_QRCodeImg.get_attribute("src")
            if not J_QRCodeImg_url or J_QRCodeImg_url == self.last_J_QRCodeImg_url:
                time.sleep(0.05)
        self.last_J_QRCodeImg_url = J_QRCodeImg_url
        logging.info('login qrcode %s', J_QRCodeImg_url)

        cookies = self.web.get_cookies()
        fcookies = []
        for cookie in cookies:
            fcookies.append("%s=%s" % (cookie["name"], cookie["value"]))
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/61.0.3163.100 Safari/537.36",
            "Cookie": ";".join(fcookies)
        }
        res = requests.get(J_QRCodeImg_url, headers = headers)
        if res.ok:
            img = StringIO(res.content)
            qrcode = QRcode(img, 46, 46)
            logging.info('show qrcode')
            logging.info('\n' + qrcode.show())

    def login(self):
        self.web.get("http://pub.alimama.com/")
        self.load_cookies()
        url = success_url
        logging.info("load %s", url)
        self.web.get(url)
        if self.web.current_url == success_url:
            my_taobao_url = "https://my.taobao.com/my_taobao.htm"
            self.web.get(my_taobao_url)
            if self.web.current_url == my_taobao_url:
                logging.info('login success')
                self.login_succed = True
                self.save_cookies()
        elif self.web.current_url != url:
            logging.info("redirect login %s", self.web.current_url)
            taobaoLoginIfr = self.web.find_elements_by_name("taobaoLoginIfr")
            if taobaoLoginIfr:
                url = taobaoLoginIfr[0].get_attribute("src")
                logging.info('load %s', url)
                self.web.get(url)

                J_Quick2Static = self.web.find_element_by_class_name('J_Quick2Static')
                if J_Quick2Static.is_displayed():
                    logging.info('display login form')
                    J_Quick2Static.click()

                logging.info('checking username displayed')
                TPL_username_1 = self.web.find_element_by_id('TPL_username_1')
                while not TPL_username_1.is_displayed():
                    time.sleep(0.05)
                    TPL_username_1 = self.web.find_element_by_id('TPL_username_1')
                logging.info('username send_keys')
                TPL_username_1.send_keys(username)

                logging.info('checking username displayed')
                TPL_password_1 = self.web.find_element_by_id('TPL_password_1')
                while not TPL_password_1.is_displayed():
                    time.sleep(0.05)
                    TPL_password_1 = self.web.find_element_by_id('TPL_password_1')
                logging.info('password send_keys')
                TPL_password_1.send_keys(password)

                logging.info('checking username send_keys')
                TPL_username_1 = self.web.find_element_by_id('TPL_username_1')
                while TPL_username_1.get_attribute("value") != username:
                    time.sleep(0.05)
                    TPL_username_1 = self.web.find_element_by_id('TPL_username_1')

                logging.info('checking password send_keys')
                TPL_password_1 = self.web.find_element_by_id('TPL_password_1')
                while TPL_password_1.get_attribute("value") != password:
                    time.sleep(0.05)
                    TPL_password_1 = self.web.find_element_by_id('TPL_password_1')

                login_url = self.web.current_url
                logging.info('login %s', login_url)
                self.web.find_element_by_id('J_SubmitStatic').click()
                while login_url == self.web.current_url:
                    time.sleep(0.05)

                if self.web.current_url.startswith('https://login.taobao.com/member/login.jhtml'):
                    logging.info("start qrcode login %s", self.web.current_url)
                    J_Static2Quick = self.web.find_element_by_id('J_Static2Quick')
                    if J_Static2Quick.is_displayed():
                        J_Static2Quick.click()

                    self.show_qrcode()
                    while True:
                        if self.web.current_url == success_url:
                            logging.info('login success')
                            self.login_succed = True
                            self.save_cookies()
                            break
                        J_QRCodeRefresh = self.web.find_element_by_class_name('J_QRCodeRefresh')
                        if J_QRCodeRefresh.is_displayed():
                            J_QRCodeRefresh.click()
                            self.show_qrcode()
                        time.sleep(1)

    def get_session(self, force_refresh = False):
        if not force_refresh and self.session and time.time() - int(self.session.get('ts', 0)) < int(self.session.get('expires_in', 0)) / 2.0:
            return

        self.web.get("https://login.taobao.com/")
        self.load_cookies()
        url = 'https://oauth.taobao.com/authorize?response_type=token&client_id=' + client_id + '&state=xql_tkb&view=web'
        logging.info("load %s", url)
        self.web.get(url)
        start_time = time.time()
        while True:
            if self.web.current_url == url:
                try:
                    sub = self.web.find_element_by_id('sub')
                except NoSuchElementException:
                    self.web.find_element_by_id('J_loginIframe')
                    logging.info("session fail %s", self.web.current_url)
                    break

                logging.info('checking sub displayed')
                while not sub.is_displayed():
                    time.sleep(0.05)
                    sub = self.web.find_element_by_id('sub')
                logging.info('confirm %s', self.web.current_url)
                sub.click()

            elif self.web.current_url.startswith("https://oauth.taobao.com/oauth2"):
                url = self.web.current_url
                data = url.split("#")
                if data and len(data) == 2:
                    data = data[1]
                    result = {}
                    for param in data.split('&'):
                        param = param.split("=")
                        if param and len(param) == 2:
                            result[param[0]] = param[1]
                    if result:
                        self.session = result
                        self.session["ts"] = time.time()
                logging.info("session success %s", url)
                break

            if time.time() - start_time > 30:
                break
            time.sleep(1)

    def quit(self):
        self.web.quit()

class CookiesRequestHandler(RequestHandler):
    @gen.coroutine
    def get(self):
        force_refresh = self.get_query_argument("force_refresh", 0)
        if force_refresh:
            future = gen.Future()
            tasks.put((future, spider.login, (), {}))
            yield future
        self.write(spider.cookies.encode("utf-8"))

class SessionRequestHandler(RequestHandler):
    @gen.coroutine
    def get(self):
        name = self.get_query_argument("name", "")
        force_refresh = self.get_query_argument("force_refresh", 0)
        if force_refresh:
            future = gen.Future()
            tasks.put((future, spider.get_session, (True,), {}))
            yield future

        if name:
            self.write(spider.session.get(name, "").encode("utf-8"))
        else:
            self.write(("&".join(["%s=%s" % (key, value) for key, value in spider.session.iteritems()])).encode("utf-8"))

def start_server():
    global is_stoped
    try:
        app = Application([
            (r"/cookies", CookiesRequestHandler),
            (r"/session", SessionRequestHandler),
        ])
        app.listen(bind_port, bind_host)
        IOLoop.current().start()
    except:
        is_stoped = True

def exit_handler(*args, **kwargs):
    global is_stoped
    is_stoped = True

if __name__ == '__main__':
    signal.signal(signal.SIGHUP, exit_handler)
    signal.signal(signal.SIGINT, exit_handler)
    signal.signal(signal.SIGTERM, exit_handler)
    if log_filename:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)1.1s %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S', filemode='a+', filename=log_filename)
    else:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)1.1s %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S', filemode='a+', stream = sys.stdout)

    tasks = Queue.Queue()
    if bind_port:
        server_thread = threading.Thread(target=start_server)
        server_thread.setDaemon(True)
        server_thread.start()

    is_stoped = False
    spider = Spider()
    spider.login()
    if client_id:
        spider.get_session()
        
    if demon_mod:
        last_refresh_time = time.time()
        while not is_stoped:
            try:
                task = tasks.get(True, 1)
                future, callback, args, kwargs = task
                result = None
                try:
                    try:
                        result = callback(*args, **kwargs)
                    finally:
                        spider.web.get("http://connect.rom.miui.com/generate_204")
                finally:
                    IOLoop.current().add_callback(future.set_result, result)
            except Queue.Empty:
                pass

            if time.time() - last_refresh_time >= refresh_time:
                logging.info("start refresh")
                try:
                    spider.login()
                    if client_id:
                        spider.get_session()
                finally:
                    spider.web.get("http://connect.rom.miui.com/generate_204")
                logging.info("end refresh")
                last_refresh_time = time.time()
        spider.quit()
    else:
        spider.quit()
