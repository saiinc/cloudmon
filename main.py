import os
from datetime import datetime, timedelta
import requests
from flask import Flask, request
from apscheduler.schedulers.background import BackgroundScheduler
from github import Github
import csv
import zipfile


SND_PATH = os.environ['SND_PATH']
STATUS_PATH = os.environ['STATUS_PATH']
LOG_PATH = os.environ['LOG_PATH']
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
TLG_CHAT_ID = os.environ['TLG_CHAT_ID']
PASSPHRASE = os.environ['PASSPHRASE']
GITHUB_TOKEN = os.environ['GITHUB_TOKEN']
#GITHUB_USERNAME = os.environ['GITHUB_USERNAME']
#REPOSITORY_NAME = os.environ['REPOSITORY_NAME']

app = Flask(__name__)
g = Github(GITHUB_TOKEN)
#repo = g.get_repo(GITHUB_USERNAME + '/' + REPOSITORY_NAME)
repo = g.get_repo("cloudmon1/cloudmon")
git_file = 'temp.db'

password = str.encode(PASSPHRASE)


def str2bool(v):
    return v.lower() in ("true", "yes", "t", "1")


def save_to_csv(list_nodes, filename):
    with open(filename, 'w', newline='') as csvfile:
        fieldnames = ['node_name', 'alert', 'time']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        for item in list_nodes:
            writer.writerow(item)
    with zipfile.ZipFile("temp_db.zip", "w") as zf:
        zf.write(filename)

        zf.setpassword(password)


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
        content_to_upload = file.read()
    if "temp_db.zip" in all_repo_files:
        contents = repo.get_contents("temp_db.zip")
        print('content_to_upload: ' + str(content_to_upload))
        print('repo.update_file: ' + str(repo.update_file("temp_db.zip", "committing files", content_to_upload, contents.sha)))
    else:
        print('content_to_upload: ' + str(content_to_upload))
        repo.create_file("temp_db.zip", "committing files", str(content_to_upload.decode()), branch="master")
        #print(repo.update_file(git_file, "committing files", content_to_upload, contents.sha))
        print("temp_db.zip" + ' CREATED')


def get_nodes():
    nodes_str = 'node_test, home_test'
    nodes = tuple(map(str, nodes_str.split(', ')))
    list_nodes = []
    list_csvnodenames = []
    list_csvnodes = []
    all_repo_files = []
    contents = repo.get_contents("")
    while contents:
        file_content = contents.pop(0)
        if file_content.type == "dir":
            contents.extend(repo.get_contents(file_content.path))
        else:
            file = file_content
            all_repo_files.append(str(file).replace('ContentFile(path="', '').replace('")', ''))
    if git_file in all_repo_files:
        content = repo.get_contents(path="temp_db.zip")
        print('decoded_content: ' + str(content.decoded_content))
        filedb = content.decoded_content
        f = open("temp_db.zip", 'wb')
        f.write(filedb)
        f.close()
        with zipfile.ZipFile("temp_db.zip", "r") as zf:
            info = zf.infolist()
            print(info)
            zf.extract(info[0], "", pwd=password)
        with open(git_file, newline='') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                list_csvnodenames.append(row[0])
                list_csvnodes.append(row)
    print('list_csvnodenames: ' + str(list_csvnodenames))
    to_delete = list(set(list_csvnodenames) - set(nodes))
    print(to_delete)
    csvnodes_cleared = list(list_csvnodes)
    for row in list_csvnodes:
        if row[0] in to_delete:
            csvnodes_cleared.remove(row)
    print(csvnodes_cleared)
    for row in csvnodes_cleared:
        dict_csvnode = {'node_name': row[0], 'alert': str2bool(row[1]), 'time': datetime.strptime(row[2], "%Y-%m-%d %H:%M:%S.%f")}
        list_nodes.append(dict_csvnode)
    to_add = list(set(nodes) - set(list_csvnodenames))
    print(to_add)
    for row in to_add:
        dict_node = {'node_name': row, 'alert': 'False', 'time': datetime.now()}
        list_nodes.append(dict_node)
    print(list_nodes)
    if to_delete or to_add:
        save_to_csv(list_nodes, git_file)
        upload_to_github()
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
