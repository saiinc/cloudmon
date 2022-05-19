import os
from datetime import datetime, timedelta
import requests
from flask import Flask, request
from apscheduler.schedulers.background import BackgroundScheduler
import psycopg2
from psycopg2 import OperationalError
from psycopg2 import Error

from github import Github
import csv
import zipfile
import base64
import pyminizip


DATABASE_URL = os.environ['DATABASE_URL']
#NODELIST = os.environ['NODELIST']
SND_PATH = os.environ['SND_PATH']
STATUS_PATH = os.environ['STATUS_PATH']
LOG_PATH = os.environ['LOG_PATH']
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
TLG_CHAT_ID = os.environ['TLG_CHAT_ID']
PASSPHRASE = os.environ['PASSPHRASE']
GITHUB_TOKEN = os.environ['GITHUB_TOKEN']
#GITHUB_USERNAME = os.environ['GITHUB_USERNAME']
#REPOSITORY_NAME = os.environ['REPOSITORY_NAME']


try:
    # Подключиться к существующей базе данных
    psycopg2.connect(DATABASE_URL)
    connection = psycopg2.connect(DATABASE_URL, sslmode='require')

    # Создайте курсор для выполнения операций с базой данных
    cursor = connection.cursor()
    # SQL-запрос для создания новой таблицы
    create_table_query = '''CREATE TABLE nodelist
                          (node_name     TEXT                NOT NULL,
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
g = Github(GITHUB_TOKEN)
#repo = g.get_repo(GITHUB_USERNAME + '/' + REPOSITORY_NAME)
repo = g.get_repo("cloudmon1/cloudmon")
git_file = 'temp.db'

password = str.encode(PASSPHRASE)


def execute_query(connection_db, query):
    cursor = connection_db.cursor()
    try:
        cursor.execute(query)
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


def str2bool(v):
    return v.lower() in ("true", "yes", "t", "1")


def save_to_csv(list_nodes, filename):
    with open(filename, 'w', newline='') as csvfile:
        fieldnames = ['node_name', 'alert', 'time']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        for item in list_nodes:
            writer.writerow(item)
    pyminizip.compress(filename, "", "temp_db.zip", password, 1)


def upload_to_github():
    all_repo_files = []
    contents = repo.get_contents("")
    while contents:
        file_content = contents.pop(0)
        if file_content.type == "dir":
            contents.extend(repo.get_contents(file_content.path))
        else:
            file = file_content
            all_repo_files.append(str(file).replace('ContentFile(path="', '').replace('")', ''))

    with open("temp_db.zip", 'rb') as file:
        content_to_upload = base64.b64encode(file.read())
    if "temp_db.zip" in all_repo_files:
        contents = repo.get_contents("temp_db.zip")
        print('content_to_upload: ' + str(content_to_upload))
        print('repo.update_file: ' + str(repo.update_file("temp_db.zip", "committing files", content_to_upload, contents.sha)))
    else:
        print('content_to_upload: ' + str(content_to_upload))
        repo.create_file("temp_db.zip", "committing files", str(content_to_upload.decode()), branch="master")
        print("temp_db.zip" + ' CREATED')


def get_nodes():
    nodes_str = 'node_test, home_test, 123qwe123'
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
    db_to_add = []
    for row in to_add:
        dict_node = {'node_name': row, 'alert': False, 'time': datetime.now()}
        list_nodes.append(dict_node)
        list_node = [row, False, datetime.now()]
        db_to_add.append(list_node)
    print('final list_nodes: ' + str(list_nodes))
    if to_add:
        cursor = connection.cursor()
        for row in db_to_add:
            cursor.execute("INSERT INTO nodelist (node_name, state, time) VALUES (%s, %s, %s)", (row[0], row[1], row[2]))
        connection.commit()
    #if to_delete:
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
            save_to_csv(nodelist, git_file)
            upload_to_github()
            print(''.join(["Alert message send to Telegram ", sender_tlg(index, True)]))
            return print('Status ' + message.get('node_name') + ' switched to Alert')
        else:
            return print(' '.join(['Status ' + message.get('node_name') + ' is Alert:', str(datetime.now() - message.get('time'))]))
    else:
        if message.get('alert') is True:
            message.update({'alert': False})
            save_to_csv(nodelist, git_file)
            upload_to_github()
            print(''.join(["Alive message send to Telegram ", sender_tlg(index, False)]))
            return print('Status ' + message.get('node_name') + ' switched to OK')
        else:
            return print(' '.join(['Status ' + message.get('node_name') + ' is OK,', "time now:", str(datetime.now()), "  ",
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
