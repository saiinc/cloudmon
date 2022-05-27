# Cloudmon
## Cron monitoring service for windows/linux computers or devices with linux based os

Integration is now only available with Telegram.

Click the button below to deploy to Heroku

[![Deploy](https://www.herokucdn.com/deploy/button.png)](https://heroku.com/deploy)


## 0. Attention

Deployment requires registration of a heroku account, an email is required when registering a heroku account (otherwise the verification code cannot be brushed out). 

An email address that can receive verification codes normally (@qq.com, @163.com are not acceptable):
- gmail (Best) 
- Outlook <https://login.live.com/> here.

To keep the service running all the time, add a bank card on the billing page of your heroku account (money will not be withdrawn, but it adds more free dyno hours to your app).

## 1. Telegram bot setup

1.1 Register a new Telegram Bot: send "/newbot" to @BotFather and follow the instructions. The token provided by @BotFather in the final step will be needed for configuring TELEGRAM_TOKEN environment variable.

1.2 Obtain chat ID of the user the bot should send messages to. <br />
Send "/getid" to "@myidbot" in Telegram messenger. This id should be writen to TLG_CHAT_ID environment variable.

1.3 Send "/start" to the bot, created in step 1. If you skip this step, Telegram bot won't be able to send messages to you.

## 2. Configure your nodes

You just need to periodically send json messages that contains node name from NODELIST and password from PASSPHRASE heroku env variables of your heroku-app

#### Windows computers: 

Open notepad and add this: 

curl -H "Content-Type: application/json" -X POST https://app-name.herokuapp.com/send-path -d "{\\"username\\":\\"node_name\\",\\"text\\":\\"all_ok\\",\\"password\\":\\"my-password\\"}"

Save file as pinger.cmd

Make a new file and add this:

Set WshShell = CreateObject("WScript.Shell")<br />
WshShell.Run chr(34) & "C:\pinger.cmd" & Chr(34), 0<br />
Set WshShell = Nothing

Save file as pinger.vbs

Open Windows Power Shell and run this:<br />
$trigger = New-JobTrigger -Once -At "09/12/2013 1:00:00" -RepetitionInterval (New-TimeSpan -Minutes 1.001) -RepetitionDuration ([TimeSpan]::MaxValue)<br />
$action = New-ScheduledTaskAction -Execute 'c:\pinger.vbs' -Argument '-NoProfile -WindowStyle Hidden'<br />
Register-ScheduledTask -Action $action -Trigger $trigger -TaskName "cloudmon-heroku" -Description "cloudmon-heroku"


#### Linux computers:

Create a file with the following content:<br />
curl -d '{"username":"node_name","text":"all_ok","password":"my-password"}' -H "Content-Type: application/json" -X POST https://app-name.herokuapp.com/send-path<br />

Make file executable.

Create a new cron job with a one-minute run time to run this file.
