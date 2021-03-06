import datetime
import os
import re
import sys
import click
import pandas as pd
from tabulate import tabulate
import matplotlib.pyplot as plt

ini_file_path = f"{os.path.splitext(os.path.basename(__file__))[0]}.ini"


def print_info(data):
    print(tabulate(data, headers='keys', tablefmt='psql'))


def get_config(currency, datum):
    if os.path.isfile(ini_file_path) and os.stat(ini_file_path).st_size != 0:
        path = os.path.join(os.path.dirname(__file__), ini_file_path)
    else:
        print('Не удалось получить нужные параметры т.к. ini файла не существует.')
        print('Для создания запустите команду "ini" и укажите в созданном файле все требуетмые параметры')
        input('нажмите Enter ... ')
        sys.exit()

    date_to_compare = datetime.datetime.strptime(datum, '%Y-%m-%d').date()

    currency = str(currency).upper()
    data = pd.read_json(path, orient='records', convert_dates=False)
    data['Cur_DateStart'] = pd.to_datetime(data['Cur_DateStart']).apply(lambda x: x.date())
    data['Cur_DateEnd'] = pd.to_datetime(data['Cur_DateEnd']).apply(lambda x: x.date())

    info = data[(data.Cur_Abbreviation == currency) &
                (data.Cur_DateStart <= date_to_compare) &
                (data.Cur_DateEnd >= date_to_compare)]

    if info.empty:
        print(f'Не удалось получить данные по валюте {str(currency).upper()}')
        input('нажмите Enter ... ')
        sys.exit()

    cur_id = info.iloc[0]['Cur_ID']
    return cur_id


def reformat_date(date: str, nbrb: bool = '') -> str:
    """
    Форматирует полученную на входе дату или для сайта nbrb.by, или же дату в нормальном виде с разделителями точка.
    Допустимый ввод данных: 01.01.19 (допустимый разделитель ./), 01.01.2019, 010119, 01012019
    :param date: Дата
    :param nbrb: True - дата форматируется для сайта nbrb.by, False - обычная дата с разделитерями точно
    :return: дата, в зависимости от параметра nbrb
    """

    delimiters = ['.', '/', '-']

    if any(delimiter in date for delimiter in delimiters):
        date = re.sub('[-.:/]', '.', date)
        if nbrb:
            date = datetime.datetime.strptime(date, '%d.%m.%Y').strftime('%Y-%m-%d')
    else:
        length = len(date)
        if length == 6:
            if nbrb:
                date = datetime.datetime.strptime(date, '%d%m%y').strftime('%Y-%m-%d')
            else:
                date = datetime.datetime.strptime(date, '%d%m%y').strftime('%d.%m.%Y')
        elif length == 8:
            if nbrb:
                date = datetime.datetime.strptime(date, '%d%m%Y').strftime('%Y-%m-%d')
            else:
                date = datetime.datetime.strptime(date, '%d%m%Y').strftime('%d.%m.%Y')
        else:
            print('Не правильная дата')
            input('нажмите Enter ... ')
            sys.exit()

    return date


def get_exchange_rate(c, d, to=''):
    if c is not None and c.upper() == 'BYN':
        frame = {"Cur_Abbreviation": "BYN", "Cur_ID": 1, "Cur_Name": "Беларуский рубль", "Cur_OfficialRate": 1,
                 "Cur_Scale": 1, "Date": "2016-07-05T00:00:00"}
        data = pd.DataFrame.from_dict(frame, orient='index')
    else:
        base_url = 'http://www.nbrb.by/API/ExRates/Rates'
        if to:
            # Курсы за определенный период:
            # http://www.nbrb.by/API/ExRates/Rates/Dynamics/298?startDate=2016-7-1&endDate=2016-7-30
            date_from = reformat_date(d, True)
            date_to = reformat_date(to, True)
            currency_code = get_config(c, date_from)
            url = base_url + f"/Dynamics/{currency_code}?startDate={date_from}&endDate={date_to}"
            orient = 'records'
        elif c and d:
            d = reformat_date(d, True)
            currency_code = get_config(c, d)
            # Курс для определеной валюты на дату:
            # http://www.nbrb.by/API/ExRates/Rates/298?onDate=2016-7-5
            url = base_url + f"/{currency_code}?onDate={d}"
            orient = 'index'
        elif c:
            # Курс для определенной валюты сегодня:
            # http://www.nbrb.by/API/ExRates/Rates/USD?ParamMode=2
            url = base_url + f"/{c}?ParamMode=2"
            orient = 'index'
        elif d:
            d = reformat_date(d, True)
            # Все курсы на определенную дату:
            # http://www.nbrb.by/API/ExRates/Rates?onDate=2016-7-6&Periodicity=0
            url = base_url + f"?onDate={d}&Periodicity=0"
            orient = 'records'
        else:
            # Все курсы на сегодня:
            # http://www.nbrb.by/API/ExRates/Rates?Periodicity=0
            url = base_url + '?Periodicity=0'
            orient = 'records'

        data = retrieve_data_from_url(url, orient)
    return data


def retrieve_data_from_url(url, orient):
    data = pd.read_json(url, orient=orient)
    return data


@click.group()
def cli():
    """ Скрипт для получения данных с сайта нац. банка РБ """


@cli.command('ini')
def ini():
    """ Создание конфигурационного ini файла, где сопоставляются ISO коды валют (USD) с внутренними кодами нац. банка"""

    url = 'http://www.nbrb.by/API/ExRates/Currencies'
    orient = 'records'
    json_ini = retrieve_data_from_url(url, orient)
    json_ini.to_json(ini_file_path, 'records')


@cli.command('rate')
@click.argument('currency', required=False)
@click.option('-d', help='Дата, на которую хотим получить курс. Используется совместо с указаниева валюты,\
 для которой хотим получить курс')
@click.option('-all', is_flag=True, help='Получить курсы за перид')
@click.option('-g', is_flag=True, help='Отрисовать график колебания курсов')
def rate(currency='', d='', all='', g=''):
    """
    Курсы валют

    Опционный параметр:
    currency: Валюта, для которой хотим получить курс.
    """

    if all:
        date_from = input('Введите дату "С": ')
        date_to = input('Введите дату "По": ')
        # http://www.nbrb.by/API/ExRates/Rates/Dynamics/298?startDate=2016-7-1&endDate=2016-7-30
        rate_info = get_exchange_rate(currency, date_from, date_to)
        rate_info['Date'] = pd.to_datetime(rate_info['Date']).dt.strftime('%d.%m.%Y')
        data = rate_info.loc[:, 'Date':'Cur_OfficialRate']
        data.columns = ['Дата', f'Курс {str(currency).upper()}']
    else:
        rate_info = get_exchange_rate(currency, d)
        rate_info.loc['Date'] = pd.to_datetime(rate_info.loc['Date']).dt.strftime('%d.%m.%Y')
        info = [
            {'Дата': rate_info.loc['Date'][0], f'Курс {str(currency).upper()}': rate_info.loc['Cur_OfficialRate'][0]}]
        data = pd.DataFrame(info)

    print_info(data)

    if all and g:
        ax = plt.gca()
        data.plot(kind='line', x=data.columns[0], y=data.columns[1], ax=ax)
        plt.show()

    input('нажмите Enter ...')


@cli.command('ref')
@click.option('-d', help='Получить ставку на указанную дату')
@click.option('-all', is_flag=True, help='Показать динамику изменений ставки')
@click.option('-g', is_flag=True, help='Отрисовать график колебания курсов')
def ref(d, all, g):
    """ Ставка рефинансирования """

    base_url = 'http://www.nbrb.by/API/RefinancingRate'

    if d:
        d = reformat_date(d, True)
        url = base_url + f"?onDate={d}"
    elif all:
        url = base_url
    else:
        today = datetime.datetime.today()
        url = base_url + f"?onDate={today:%Y-%m-%d}"

    orient = 'records'
    data = retrieve_data_from_url(url, orient)
    data['Date'] = pd.to_datetime(data['Date']).dt.strftime('%d.%m.%Y')
    data.columns = ['Дата', 'Ставка Реф.']
    print_info(data)

    if all and g:
        ax = plt.gca()
        data.plot(kind='line', x=data.columns[0], y=data.columns[1], ax=ax)
        plt.show()

    input('нажмите Enter ...')


@cli.command('conv')
@click.argument('amount')
@click.argument('cur_from')
@click.argument('cur_to')
@click.option('-d', help='Дата')
def conv(amount, cur_from, cur_to, d=''):
    """
    Перерасчет валют \n
    Обязательные параметры: \n
    amount: Сумма, из которой делаем перерасчет, например: 100 \n
    cur_from: Валюта, из которой делаем перерасчет, например: USD \n
    cur_to: Валюта, в которую нужно сделать перерасчет, например, EUR \n
    Пример командной строки: 100 usd eur
    """

    # TODO: добавить флаг -all, чтобы перерасчитывать исходную валюту во все (возможно основные).

    data_from = get_exchange_rate(cur_from, d)
    data_to = get_exchange_rate(cur_to, d)

    amount = float(amount)
    rate_from = float(data_from.loc['Cur_OfficialRate'][0])
    rate_to = float(data_to.loc['Cur_OfficialRate'][0])
    scale_from = float(data_from.loc['Cur_Scale'][0])
    scale_to = float(data_to.loc['Cur_Scale'][0])

    amount_calc = amount * (rate_from * scale_to) / (rate_to * scale_from)

    info = [{'Сумма из': amount, 'Валюта из': str(cur_from).upper(), '=': '=', 'Сумма в': amount_calc,
             'Валюта в': str(cur_to).upper()}]
    data = pd.DataFrame(info)
    data.set_index('Сумма из')
    print_info(data)

    input('нажмите Enter ...')


if __name__ == '__main__':
    cli()
