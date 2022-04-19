import os
from datetime import datetime, timedelta
import requests
from flask import Flask, request
from apscheduler.schedulers.background import BackgroundScheduler
from github import Github
import csv


SND_PATH = os.environ['SND_PATH']
STATUS_PATH = os.environ['STATUS_PATH']
LOG_PATH = os.environ['LOG_PATH']
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
TLG_CHAT_ID = os.environ['TLG_CHAT_ID']
PASSPHRASE = os.environ['PASSPHRASE']
GITHUB_TOKEN = os.environ['GITHUB_TOKEN']

app = Flask(__name__)
g = Github(GITHUB_TOKEN)
repo = g.get_repo("cloudmon1/cloudmon")


def save_to_csv(list_nodes):
    with open('names.csv', 'w', newline='') as csvfile:
        fieldnames = ['node_name', 'alert', 'time']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        for item in list_nodes:
            writer.writerow(item)


def get_nodes():
    contents = repo.get_contents(path='temp.db')
    filedb = contents.decoded_content
    f = open('temp.db', 'wb')
    f.write(filedb)
    f.close()
    nodes = ('node_test1', 'home_test', 'home_test1')
    list_nodes = []
    list_csvnodenames = []
    list_csvnodes = []
    with open('names.csv', newline='') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            list_csvnodenames.append(row[0])
            list_csvnodes.append(row)
    print(list_csvnodenames)
    to_delete = list(set(list_csvnodenames) - set(nodes))
    print(to_delete)
    csvnodes_cleared = list(list_csvnodes)
    for row in list_csvnodes:
        if row[0] in to_delete:
            csvnodes_cleared.remove(row)
    print(csvnodes_cleared)
    for row in csvnodes_cleared:
        dict_csvnode = {'node_name': row[0], 'alert': row[1], 'time': datetime.strptime(row[2], "%Y-%m-%d %H:%M:%S.%f")}
        list_nodes.append(dict_csvnode)
    for row in nodes:
        result = next((x for x in list_nodes if x['node_name'] == row), None)
        if result is None:
            dict_node = {'node_name': row, 'alert': False, 'time': datetime.now()}
            list_nodes.append(dict_node)
    print(list_nodes)
    save_to_csv(list_nodes)
    with open('names.csv', 'r') as file:
        content = file.read()
    print(repo.update_file("temp.db", "list_nodes_test", content, contents.sha))
    return list_nodes


dblog = []
nodelist = get_nodes()
#repo = g.get_repo("cloudmon1/cloudmon")
statedir = "state/"
#print(repo.create_file(statedir + "test.txt", "testing", "test", branch="nodb"))


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
            save_to_csv(nodelist)
            print(''.join(["Alert message send to Telegram ", sender_tlg(index, True)]))
            return print('Status ' + message.get('node_name') + ' switched to Alert')
        else:
            return print(' '.join(['Status ' + message.get('node_name') + ' is Alert:', str(datetime.now() - message.get('time'))]))
    else:
        if message.get('alert') is True:
            message.update({'alert': False})
            save_to_csv(nodelist)
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
