#!/usr/bin/env python3

import base64
import hashlib
import json
import threading

import requests


# t=ДатаТВремя -> str. формат: year[0:3], month[4:5], day[6:7], [8] == 'T', hour[9:10], minute[11:12]
# s=СуммаСКопейками -> float. 2 знака
# fn=НомерФискальногоНакопителяККТ -> int as FN
# i=НомерФискальногоДокументаЧека -> int as FD
# fp=УникальныйыФискальныйПризнакЧека -> int as FPD
# n=X -> 0 - ОСН, 1 - УСН


def __f(d):
    return '{0:.2f}'.format(d / 100) if d // 100 != d / 100 else str(d // 100)


def pretty_items(items: list) -> list:
    c_list = []
    i_list = []
    for item in items:
        code, name = item['name'].split(' ', 1)
        if not (code and code.isnumeric() and name):
            name = item['name']
            code = None
        name = ' '.join([x for x in name.split(' ') if x])
        try:
            idx = c_list.index(code)
            target = i_list[idx]
        except ValueError:
            target = {}
            c_list.append(code if code else name)
            i_list.append(target)
        if code:
            target['code'] = code
        target['name'] = name
        target['price'] = item.get('price', -1)
        target['quantity'] = target.get('quantity', 0) + item.get('quantity', -1)
        target['sum'] = target.get('sum', 0) + item.get('sum', -1)
    for item in i_list:
        item['price'] = __f(item['price'])
        item['sum'] = __f(item['sum'])
    return i_list


def pretty_print(data: dict):
    d = data.get('document', {}).get('receipt')
    if not d:
        return 'Section \'receipt\' missing'
    pretty = {
        'НДС': __f(d.get('nds10', 0) + d.get('nds18', 0)),
        'Оператор': d.get('operator'),
        'ИТОГ': __f(d.get('totalSum', 0)),
        'Дата': d.get('dateTime'),
        'Покупки': 'Section \'items\' missing'
    }
    items = d.get('items')
    if items:
        pretty['Покупки'] = pretty_items(items)
    return pretty


class Request(threading.Thread):
    HEADERS = {
        'Authorization': 'Basic {}',
        'Device-Id': '{}',
        'Device-OS': 'Adnroid 5.1',
        'Version': '2',
        'ClientVersion': '1.4.4.1',
        'Connection': 'Keep-Alive',
        'Accept-Encoding': 'gzip',
        'User-Agent': 'okhttp/3.0.1'
    }
    GET = {
        'fiscalSign': '{FPD}',
        'sendToEmail': 'no'
    }
    URL = 'https://proverkacheka.nalog.ru:9999/v1/inns/*/kkts/*/fss/{FN}/tickets/{FD}'

    def __init__(self, phone, pwd, fn, fd, fpd):
        """

        :param phone: Номер телефона, начинается с + и состоит только из цифр
        :param pwd: Пароль который пришел смской
        :param fn: fn из кода
        :param fd: i из кода
        :param fpd: fp из кода
        """
        super().__init__()
        self._code = 0
        self._result = None
        self._err = ''
        self._wait = threading.Event()
        self.__auth = base64.b64encode('{}:{}'.format(phone, pwd).encode()).decode()
        self._data = dict(FN=fn, FD=fd, FPD=fpd)
        self.start()

    @property
    def err(self):
        self.wait()
        return self._code, self._err

    @property
    def data(self):
        self.wait()
        return self._result

    def wait(self):
        self._wait.wait()

    def run(self):
        try:
            self._run()
        finally:
            self._wait.set()

    def _set_err(self, code, msg, txt=''):
        self._code = code
        self._err = '{}: {}'.format(msg, txt)[:200] if txt else msg

    def _run(self):
        headers = self.HEADERS.copy()
        headers['Authorization'] = headers['Authorization'].format(self.__auth)
        headers['Device-Id'] = hashlib.sha1(self.__auth.encode()).hexdigest()[2:-2]

        url = self.URL.format(**self._data)
        get = self.GET.copy()
        get['fiscalSign'] = self._data['FPD']
        try:
            response = requests.get(url, params=get, headers=headers)
        except (requests.exceptions.HTTPError, requests.exceptions.RequestException) as e:
            return self._set_err(e.errno, e.strerror)

        if response.status_code != 200:
            return self._set_err(response.status_code, response.reason)

        if not response.text:
            return self._set_err(1, 'Empty response')

        if not response.text.startswith('{') or not response.text.endswith('}'):
            return self._set_err(2, response.text)

        try:
            self._result = json.loads(response.text)
        except json.JSONDecodeError as e:
            return self._set_err(3, 'JSONDecodeError {}'.format(e), response.text)
        except TypeError as e:
            return self._set_err(4, 'TypeError {}'.format(e), response.text)


def main():
    with open('request.data') as fp:
        for line in fp.readlines():
            data = line.strip().split()
            if len(data) != 5:
                print('Line must be contain: phone password fn i fp. Get: {}'.format(line))
                continue
            inst = Request(*data)
            if not inst.data:
                print('ERROR! {}: {}'.format(*inst.err))
            else:
                print(json.dumps(pretty_print(inst.data), indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == '__main__':
    main()
