import os
from datetime import datetime, timedelta
import requests
from flask import Flask, request
from apscheduler.schedulers.background import BackgroundScheduler
from github import Github


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


def get_nodes():
    nodes = (('node_test',),)
    list_nodes = []
    for row in range(len(nodes)):
        node = nodes[row][0]
        #print(repo.create_file("state/test.txt", "testing", "test", branch="nodb"))
        contents = repo.get_contents("state", ref="nodb")
        print(contents)
        dict_node = {'node_name': node, 'alert': False,
                     'ok_msg': False, 'time': datetime.now()}
        list_nodes.append(dict_node)
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
            #execute_query(connection, update_post_zbx_mon_alert + str(index + 1))
            print(''.join(["Alert message send to Telegram ", sender_tlg(index, True)]))
            return print('Status ' + message.get('node_name') + ' switched to Alert')
        else:
            return print(' '.join(['Status ' + message.get('node_name') + ' is Alert:', str(datetime.now() - message.get('time'))]))
    else:
        if message.get('ok_msg') is True and message.get('alert') is True:
            message.update({'alert': False})
            #execute_query(connection, update_post_zbx_mon_ok + str(index + 1))
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
        nodelist[index]['ok_msg'] = True
        nodelist[index]['time'] = datetime.now()
        return {"ok": True}
    else:
        return {"ok": False}


port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)