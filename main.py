import os
from datetime import datetime, timedelta
import requests
from flask import Flask, request
from apscheduler.schedulers.background import BackgroundScheduler
import psycopg2
from psycopg2 import OperationalError
from psycopg2 import Error

DATABASE_URL = os.environ['DATABASE_URL']
# NODELIST = os.environ['NODELIST']
SND_PATH = os.environ['SND_PATH']
STATUS_PATH = os.environ['STATUS_PATH']
LOG_PATH = os.environ['LOG_PATH']
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
TLG_CHAT_ID = os.environ['TLG_CHAT_ID']
PASSPHRASE = os.environ['PASSPHRASE']

# Подключиться к существующей базе данных
psycopg2.connect(DATABASE_URL)
connection = psycopg2.connect(DATABASE_URL, sslmode='require')
# Создайте курсор для выполнения операций с базой данных
cursor = connection.cursor()
try:
    # SQL-запрос для создания новой таблицы
    create_table_query = '''CREATE TABLE nodelist
                          (node_name     TEXT                NOT NULL   UNIQUE,
                          state         BOOLEAN             NOT NULL,
                          time          TIMESTAMP           NOT NULL); '''
    # Выполнение команды: это создает новую таблицу
    cursor.execute(create_table_query)
    connection.commit()
    print("Таблица успешно создана в PostgreSQL")

except (Exception, Error) as error:
    print("Ошибка при работе с PostgreSQL", error)
finally:
    if connection:
        cursor.close()
        connection.close()
        print("Соединение с PostgreSQL закрыто")

app = Flask(__name__)
psycopg2.connect(DATABASE_URL)
connection = psycopg2.connect(DATABASE_URL, sslmode='require')
git_file = 'temp.db'

password = str.encode(PASSPHRASE)


def execute_query(connection_db, query, params):
    cursor = connection_db.cursor()
    try:
        cursor.execute(query, params)
        connection_db.commit()
        dblog.append(datetime.now().strftime('%Y/%m/%d %H:%M:%S') + ' ' + query + ', result: success')
        print("Query executed successfully")
    except OperationalError as e:
        dblog.append(datetime.now().strftime('%Y/%m/%d %H:%M:%S') + ' ' + query + ', error: ' + str(e))
        print(f"The error '{e}' occurred")


def execute_read_query(connection_db, query):
    cursor = connection_db.cursor()
    try:
        cursor.execute(query)
        result = cursor.fetchall()
        dblog.append(datetime.now().strftime('%Y/%m/%d %H:%M:%S') + ' ' + query + ', result: success')
        return result
    except OperationalError as e:
        dblog.append(datetime.now().strftime('%Y/%m/%d %H:%M:%S') + ' ' + query + ', error: ' + str(e))
        print(f"The error '{e}' occurred")


def get_nodes():
    nodes_str = 'node_test, home_test'
    nodes = tuple(map(str, nodes_str.split(', ')))
    db_nodes = execute_read_query(connection, "SELECT node_name, state, time "
                                              "FROM nodelist")
    list_nodes = []
    list_dbnodenames = []
    list_dbnodes = []
    for row in db_nodes:
        list_dbnodenames.append(row[0])
        list_dbnodes.append(row)
    print('list_dbnodenames: ' + str(list_dbnodenames))
    to_delete = list(set(list_dbnodenames) - set(nodes))
    print('to_delete: ' + str(to_delete))
    dbnodes_cleared = list(list_dbnodes)
    for row in list_dbnodes:
        if row[0] in to_delete:
            dbnodes_cleared.remove(row)
    print('dbnodes_cleared: ' + str(dbnodes_cleared))
    for row in dbnodes_cleared:
        dict_dbnode = {'node_name': row[0], 'alert': row[1], 'time': row[2]}
        list_nodes.append(dict_dbnode)
    to_add = list(set(nodes) - set(list_dbnodenames))
    print('to_add: ' + str(to_add))
    if to_add:
        cursor = connection.cursor()
        for row in to_add:
            cursor.execute("INSERT INTO nodelist (node_name, state, time) VALUES (%s, %s, %s)",
                           (row, False, datetime.now()))
            dict_node = {'node_name': row, 'alert': False, 'time': datetime.now()}
            list_nodes.append(dict_node)
        connection.commit()
    print('final list_nodes: ' + str(list_nodes))
    if to_delete:
        cursor = connection.cursor()
        for row in to_delete:
            cursor.execute("DELETE FROM nodelist WHERE node_name = %s", (row,))
        connection.commit()
    return list_nodes


dblog = []
nodelist = get_nodes()


def worker():
    try:
        item_index = 0
        for item in nodelist:
            state_checker(item, item_index)
            item_index = item_index + 1
    except Exception as ex:
        dblog.append(datetime.now().strftime('%Y/%m/%d %H:%M:%S') + ' ' + str(ex))
        requests.post("https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage",
                      data={"chat_id": TLG_CHAT_ID,
                            "text": " Проблема в главном цикле! " + str(ex)})


def state_checker(message, index):
    if datetime.now() - message.get('time') > timedelta(minutes=4):
        if message.get('alert') is False:
            message.update({'alert': True})
            print(' '.join(["Status Alert:", str(datetime.now() - message.get('time'))]))
            execute_query(connection, "UPDATE nodelist SET state = %s, time = %s WHERE node_name = %s",
                          (message.get('alert'), message.get('time'), message.get('node_name')))
            print(''.join(["Alert message send to Telegram ", sender_tlg(index, True)]))
            return print('Status ' + message.get('node_name') + ' switched to Alert')
        else:
            return print(' '.join(
                ['Status ' + message.get('node_name') + ' is Alert:', str(datetime.now() - message.get('time'))]))
    else:
        if message.get('alert') is True:
            message.update({'alert': False})
            execute_query(connection, "UPDATE nodelist SET state = %s, time = %s WHERE node_name = %s",
                          (message.get('alert'), message.get('time'), message.get('node_name')))
            print(''.join(["Alive message send to Telegram ", sender_tlg(index, False)]))
            return print('Status ' + message.get('node_name') + ' switched to OK')
        else:
            return print(
                ' '.join(['Status ' + message.get('node_name') + ' is OK,', "time now:", str(datetime.now()), "  ",
                          "time msg:", str(message.get('time'))]))


def sender_tlg(number, state):
    if state:
        response = requests.post("https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage",
                                 data={"chat_id": TLG_CHAT_ID, "text": nodelist[number]['node_name'] + " замолчал!"})
        return ''.join(["(response: ", str(response.status_code), ')'])
    else:
        response = requests.post("https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage",
                                 data={"chat_id": TLG_CHAT_ID, "text": nodelist[number]['node_name'] + " ожил!"})
        return ''.join(["(response: ", str(response.status_code), ')'])


scheduler = BackgroundScheduler()
scheduler.add_job(worker, 'interval', minutes=1)
scheduler.start()


@app.route("/")
def hello():
    return "Hello, World!"


@app.route(STATUS_PATH)
def status():
    msg_time = nodelist[0]['time']
    return {
        'alert': nodelist[0]['alert'],
        'time_now': datetime.now().strftime('%Y/%m/%d %H:%M:%S'),
        'ok_msg:': nodelist[0]['ok_msg'],
        'time_msg': msg_time.strftime('%Y/%m/%d %H:%M:%S')
    }


@app.route(LOG_PATH)
def logs():
    logpage = '<br>'.join(dblog)
    return logpage


@app.route(SND_PATH, methods=['POST'])
def receive_msg():
    data = request.json  # JSON -> dict
    index = next((i for i, item in enumerate(nodelist) if item['node_name'] == data['username']), None)
    if index is not None and data['text'] == 'all_ok' and data['password'] == PASSPHRASE:
        nodelist[index]['time'] = datetime.now()
        return {"ok": True}
    else:
        return {"ok": False}


port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)
