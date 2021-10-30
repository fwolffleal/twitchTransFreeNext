#!/usr/bin/env python
# -*- coding: utf-8 -*-

import random

import twitchio
from google_trans_new import google_translator

from gtts import gTTS
from playsound import playsound
from datetime import datetime
import threading
import queue
import time
import shutil
import re
import glob
import os
from shutil import rmtree

from twitchio.ext import commands

import sys
import signal

import requests

version = '2.1.3'
'''
v2.1.3  : 関連モジュールアップデート、バグフィクス
v2.1.2  : _MEI関連
v2.1.1  : googletrans -> google_trans_new へ置き換え
v2.1.0  : config.py の導入
v2.0.11 : gTTSアップデート＆twitch接続モジュール変更＆色々修正
v2.0.10 : python コードの文字コードをUTF-8と指定
v2.0.10 : オプション gTTS を gTTS_In, gTTS_Out に分割
v2.0.8  : オプション「無視する言語」「Show_ByName」「Show_ByLang」追加`
v2.0.7  : チャット内の別ルームを指定して，そこに翻訳結果を書く
v2.0.6  : テキストの色変更
v2.0.5  : 裏技「翻訳先言語選択機能」実装 
v2.0.4  : 
v2.0.3  : いろいろ実装した
'''

# 設定 ###############################


#####################################
# 初期設定 ###########################
# translator = Translator()
translator = google_translator(timeout=5)

gTTS_queue = queue.Queue()
sound_queue = queue.Queue()

# configure for Google TTS & play
TMP_DIR = './tmp/'

TargetLangs = ["af", "sq", "am", "ar", "hy", "az", "eu", "be", "bn", "bs", "bg", "ca", "ceb", "ny", "zh-CN", "zh-TW",
               "co",
               "hr", "cs", "da", "nl", "en", "eo", "et", "tl", "fi", "fr", "fy", "gl", "ka", "de", "el", "gu", "ht",
               "ha",
               "haw", "iw", "hi", "hmn", "hu", "is", "ig", "id", "ga", "it", "ja", "jw", "kn", "kk", "km", "ko", "ku",
               "ky",
               "lo", "la", "lv", "lt", "lb", "mk", "mg", "ms", "ml", "mt", "mi", "mr", "mn", "my", "ne", "no", "ps",
               "fa",
               "pl", "pt", "ma", "ro", "ru", "sm", "gd", "sr", "st", "sn", "sd", "si", "sk", "sl", "so", "es", "su",
               "sw",
               "sv", "tg", "ta", "te", "th", "tr", "uk", "ur", "uz", "vi", "cy", "xh", "yi", "yo", "zu"]

##########################################
# load config text #######################
import importlib

try:
    sys.path.append(os.path.join(os.path.dirname(__file__), '.'))
    config = importlib.import_module('config')
except Exception as e:
    print(e)
    print('Please make [config.py] and put it with twitchTransFN')
    input()  # stop for error!!

###################################
# fix some config errors ##########
# lowercase channel and username ------
config.Twitch_Channel = config.Twitch_Channel.lower()
config.Trans_Username = config.Trans_Username.lower()

# remove "#" mark ------
if config.Twitch_Channel.startswith('#'):
    # print("Find # mark at channel name! I remove '#' from 'config:Twitch_Channel'")
    config.Twitch_Channel = config.Twitch_Channel[1:]

# remove "oauth:" mark ------
if config.Trans_OAUTH.startswith('oauth:'):
    # print("Find 'oauth:' at OAUTH text! I remove 'oauth:' from 'config:Trans_OAUTH'")
    config.Trans_OAUTH = config.Trans_OAUTH[6:]

# 無視言語リストの準備 ################
Ignore_Lang = [x.strip() for x in config.Ignore_Lang]

# 無視ユーザリストの準備 ################
Ignore_Users = [x.strip() for x in config.Ignore_Users]

# 無視ユーザリストのユーザ名を全部小文字にする
Ignore_Users = [str.lower() for str in Ignore_Users]

# 無視テキストリストの準備 ################
Ignore_Line = [x.strip() for x in config.Ignore_Line]

# 無視単語リストの準備 ################
Delete_Words = [x.strip() for x in config.Delete_Words]

Replace_Words = [x for x in config.Replace_Words]

####################################################
#####################################
# Simple echo bot.
bot = commands.Bot(
    irc_token="oauth:" + config.Trans_OAUTH,
    client_id="",
    nick=config.Trans_Username,
    prefix="!",
    initial_channels=[config.Twitch_Channel]
)


##########################################
# メイン動作 ##############################
##########################################


# dictionary
commands_cooldown = {}
tts = {
   "on": True
}

# 起動時 ####################
@bot.event
async def event_ready():
    'Called once when the bot goes online.'
    print(f"{config.Trans_Username} is online!")
    ws = bot._ws  # this is only needed to send messages within event_ready
    await ws.send_privmsg(config.Twitch_Channel, f"/color {config.Trans_TextColor}")
    await ws.send_privmsg(config.Twitch_Channel, f"/me has landed!")


# メッセージを受信したら ####################
@bot.event
async def event_message(ctx):
    'Runs every time a message is sent in chat.'

    # コマンド処理 -----------------------
    await bot.handle_commands(ctx)

    if ctx.content.startswith('!'):
        return

    # 変数入れ替え ------------------------
    message = ctx.content
    user = ctx.author.name.lower()

    # # bot自身の投稿は無視 -----------------
    if config.Debug: print(f'echo: {ctx.echo}, {ctx.content}')
    if ctx.echo:
        return

    # 無視ユーザリストチェック -------------
    print('USER:{}'.format(user))
    if user in Ignore_Users:
        return

    # 無視テキストリストチェック -----------
    for w in Ignore_Line:
        if w in message:
            return

    # 削除単語リストチェック --------------
    for w in Delete_Words:
        message = message.replace(w, '')

    if len(message) == 0:
        return

    # 入力 --------------------------
    in_text = message
    print(in_text)

    lang_dest = ''
    # 翻訳先言語が文中で指定されてたら変更 -------
    m = in_text.split(':')
    if len(m) >= 2:
        if m[0] in TargetLangs:
            lang_dest = m[0]
            in_text = ':'.join(m[1:])

    # 言語検出 -----------------------
    lang_detect = lang_dest if lang_dest != '' else ''
    if lang_detect == '':
        try:
            lang_detect = translator.detect(in_text)[0]
        except Exception as e:
            if config.Debug:
                print(e)

    if config.Debug:
        print(f"lang_detected:{lang_detect} in_text:{in_text}")

    if lang_detect in config.lang_HomeToOthers:
        lang_dest = config.lang_TransToHome

        translated_text = await translate_text_to_lang_dest(ctx, in_text, lang_dest, lang_detect, user)

        if tts.get("on", False) and config.gTTS_Out and translated_text != '' and is_valid_message(translated_text):
            tts_text = replace_bad_words(translated_text)
            gTTS_queue.put([tts_text, lang_dest])

        time.sleep(1)
        dest_langs = [x for x in config.lang_HomeToOthers]
        dest_langs.remove(lang_detect)
        for lang in dest_langs:
            if lang is None:
                continue
            await translate_text_to_lang_dest(ctx, in_text, lang, lang_detect, user)
            time.sleep(1)

    else:
        if tts.get("on", False) and config.gTTS_In and in_text != '' and is_valid_message(in_text):
            tts_text = replace_bad_words(in_text)
            gTTS_queue.put([tts_text, config.lang_TransToHome])

        for lang in config.lang_HomeToOthers:
            await translate_text_to_lang_dest(ctx, in_text, lang, config.lang_TransToHome, user)
            time.sleep(1)

    print()


def replace_bad_words(text):
    result_text = text
    for bad_word, good_word in Replace_Words:
        result_text = re.sub(rf'\W{bad_word}\W', good_word, result_text)
    return result_text


def is_valid_message(message):
    split_by_spaces = message.split(' ')

    print(split_by_spaces)
    if len(split_by_spaces) < 1:
        return False
    elif len(split_by_spaces) == 1:
        line = str(split_by_spaces[0])
        return len(line) <= 15
    elif "@" in message and "@ecsaicow" not in message:
        # Ignore mentions to other users
        return False
    else:
        return True


async def translate_text_to_lang_dest(ctx, in_text, lang_tgt, lang_src, user):
    try:
        translated_text = translator.translate(text=in_text, lang_tgt=lang_tgt, lang_src=lang_src)
    except Exception as e:
        if config.Debug:
            print(e)
        return ''
    else:
        out_text = translated_text

        if config.Show_ByName:
            out_text = '{} [by {}]'.format(out_text, user)

        if config.Show_ByLang:
            out_text = '{} ({} > {})'.format(out_text, lang_src, lang_tgt)

        await ctx.channel.send("/me " + out_text)

        print(out_text)
        return translated_text


def is_user_entitled(user: twitchio.User) -> bool:
    is_mod = user.is_mod
    is_subscriber = bool(user.is_subscriber)

    badges = user.tags.get('badges', '').split(',')
    is_vip = False
    is_founder = False
    for badge in badges:
        keys = badge.split('/', 1)
        if keys[0] == 'vip':
            is_vip = True
        elif keys[0] == 'founder':
            is_founder = True
    return is_mod or is_subscriber or is_founder or is_vip


def set_cooldown(command_name, username):
    if commands_cooldown.get(command_name) is None:
        commands_cooldown[command_name] = {}
    commands_cooldown[command_name][username] = datetime.now()


def is_cooldown(command_name, username, cooldown_time_in_min):
    now = datetime.now()
    comm = commands_cooldown.get(command_name)
    if comm is None:
        return True
    timestamp = comm.get(username)
    if timestamp is None:
        return True
    difference = now - timestamp
    difference = difference.total_seconds() / 60
    return difference > cooldown_time_in_min


##############################
# コマンド ####################
@bot.command(name='ver')
async def ver(ctx):
    await ctx.send('this is tTFN. ver: ' + version)


@bot.command(name='commands')
async def command_list(ctx):
    await ctx.send('\nGuitar sound: !peropeun \nBass sound: !pecopeun \nSend energy: !energia \nDiscord invite: !discord \nGet songs list: !sl\nMeasure your pp: !pipi')


@bot.command(name='sound')
async def sound(ctx):
    user = ctx.author
    if is_user_entitled(user):
        sound_name = ctx.content.strip().split(" ")[1]
        sound_queue.put(sound_name)


@bot.command(name='peropeun')
async def peropeun(ctx):
    user = ctx.author
    if is_user_entitled(user):
        sound_queue.put("peropeun")


@bot.command(name='pecopeun')
async def pecopeun(ctx):
    user = ctx.author
    if is_user_entitled(user):
        sound_queue.put("pecopeun")


@bot.command(name='discord')
async def discord(ctx):
    await ctx.send(f'Entre no mosh do Ecsaicow {config.discord_invite or ", peça o link para um dos moderadores!"}')


@bot.command(name='energia')
async def energy(ctx):
    await ctx.send('༼ つ ◕◕ ༽つ ecsaicow take my energy ༼ つ ◕◕ ༽つ')


@bot.command(name='pipi')
async def peepee_size(ctx):
    username = ctx.author.name
    if not is_cooldown('pipi', username, 5):
        return
    size = random.uniform(0, 2)
    await ctx.send(f'O pipi de @{username} tem {format(size, ".3f").replace(".",",")}cm.')
    set_cooldown('pipi', username)


@bot.command(name='tts')
async def set_tts(ctx):
    user = ctx.author
    value = ctx.content.strip().split(" ", maxsplit=1)
    values = ["on", "off"]
    if user.is_mod and len(value) == 2 and value[1] in values:
        tts["on"] = value[1] == "on"
        await ctx.send(f'tts {"ligado" if tts.get("on", False) else "desligado"}')


## remove own song request
@bot.command(name='rsr')
async def remove_song_request(ctx):
    user = ctx.author
    values = ctx.content.strip().split(" ", maxsplit=1)
    if user.is_mod:
        index = int(values[1]) - 1 if len(values) == 2 and int(values[1]) > 0 else 0
        suffix = f"?index={index}"
        req = requests.delete(f"https://rs-song-request-server.herokuapp.com/ecsaicow/songs/requests{suffix}")
        print(req.url, req.status_code)


## enable/disable song requests
@bot.command(name='rstatus')
async def set_song_request_status(ctx):
    user = ctx.author
    values = ctx.content.strip().split(" ", maxsplit=1)
    status = ["all", "bass", "guitar", "off"]
    arrangements = ["Lead", "Rhythm", "Bass"]
    if not user.is_mod or len(values) < 2 or values[1] not in status:
        return

    arrangement = values[1]
    if arrangement == "bass":
        arrangements = ["Bass"]
    elif arrangement == "guitar":
        arrangements = ["Lead", "Rhythm"]

    if values[1] in status:
        is_enabled = values[1] != "off"
        req = requests.put(
            url=f"https://rs-song-request-server.herokuapp.com/ecsaicow/songs",
            json={"songRequestsEnabled": is_enabled, "songArrangements": arrangements}
        )
        print(req.url, req.status_code)


# @bot.command(name='sr')
# async def song_request(ctx):
#     username = ctx.author.name.lower()
#     song_name = ctx.content.strip().split(" ", maxsplit=1)[1]
#     save_song_request_to_list(song_name, username)
#
#
# # clear song requests
# @bot.command(name='csr')
# async def clear_song_requests(ctx):
#     user = ctx.author
#     if user.is_mod:
#         write_to_request_file([])
#
#
# ## remove index or last
# @bot.command(name='rsri')
# async def remove_song_request_by_index(ctx):
#     user = ctx.author
#     if user.is_mod:
#         args = ctx.content.strip().split(" ", maxsplit=1)
#         index = int(args[1]) if len(args) > 1 else None
#         lines = get_request_file_lines()
#         length = len(lines)
#         if index is None:
#             index = length - 1 if length > 0 else 0
#         elif index > 0:
#             index = index - 1
#         if index >= length:
#             return
#         lines.pop(index)
#         write_to_request_file(lines)
#
#
# ## remove own song request
# @bot.command(name='rsr')
# async def remove_song_requests(ctx):
#     username = ctx.author.name.lower()
#     lines = get_request_file_lines()
#     indexes = [index if username in value else None for index, value in enumerate(lines)]
#     length = len(indexes)
#     if length == 0:
#         return
#     lines.pop(indexes[length - 1])
#     write_to_request_file(lines)
#
#
# def save_song_request_to_list(song_name, username):
#     lines = get_request_file_lines()
#     length = len(lines)
#     if length == 10:
#         lines.pop(0)
#     lines.append(f'x: {song_name} (by {username})\n')
#     write_to_request_file(lines)
#
#
# def get_request_file_lines():
#     try:
#         out_file = open('song_requests.txt', 'r', encoding="utf-8")
#         lines = out_file.readlines()
#         out_file.close()
#     except FileNotFoundError:
#         return []
#     return lines
#
#
# def write_to_request_file(lines):
#     out_file = open('song_requests.txt', 'w', encoding="utf-8")
#     out_file.writelines([
#         f'{index + 1}: {value.split(" ", maxsplit=1)[1]}' for index, value in enumerate(lines)
#     ])
#     out_file.close()
#
#
#####################################
# 音声合成 ＆ ファイル保存 ＆ ファイル削除
def gTTS_play():
    global gTTS_queue

    while True:
        q = gTTS_queue.get()
        if q is None:
            time.sleep(1)
        else:
            text = q[0]
            tl = q[1]
            try:
                tts = gTTS(text, lang=tl)
                tts_file = './tmp/cnt_{}.mp3'.format(datetime.now().microsecond)
                if config.Debug: print('gTTS file: {}'.format(tts_file))
                tts.save(tts_file)
                playsound(tts_file, True)
                os.remove(tts_file)
            except Exception as e:
                print('gTTS error: TTS sound is not generated...')
                if config.Debug: print(e.args)


#####################################
# !sound 音声再生スレッド -------------
def sound_play():
    global sound_queue

    while True:
        q = sound_queue.get()
        if q is None:
            time.sleep(1)
        else:
            try:
                playsound('./sound/{}.mp3'.format(q), True)
            except Exception as e:
                print('sound error: [!sound] command can not play sound...')
                if config.Debug: print(e.args)


#####################################
# 最後のクリーンアップ処理 -------------
def cleanup():
    print("!!!Clean up!!!")

    # Cleanup処理いろいろ

    time.sleep(1)
    print("!!!Clean up Done!!!")


#####################################
# sig handler  -------------
def sig_handler(signum, frame) -> None:
    sys.exit(1)


#####################################
# _MEI cleaner  -------------
# Thanks to Sadra Heydari @ https://stackoverflow.com/questions/57261199/python-handling-the-meipass-folder-in-temporary-folder
def cleanmeifolders():
    try:
        base_path = sys._MEIPASS

    except Exception:
        base_path = os.path.abspath(".")

    if config.Debug: print(f'_MEI base path: {base_path}')
    base_path = base_path.split("\\")
    base_path.pop(-1)
    temp_path = ""
    for item in base_path:
        temp_path = temp_path + item + "\\"

    mei_folders = [f for f in glob.glob(temp_path + "**/", recursive=False)]
    for item in mei_folders:
        if item.find('_MEI') != -1 and item != sys._MEIPASS + "\\":
            rmtree(item)


# メイン処理 ###########################
def main():
    signal.signal(signal.SIGTERM, sig_handler)

    try:
        # 以前に生成された _MEI フォルダを削除する
        cleanmeifolders()

        # 初期表示 -----------------------
        print('twitchTransFreeNext (Version: {})'.format(version))
        print('Connect to the channel   : {}'.format(config.Twitch_Channel))
        print('Translator Username      : {}'.format(config.Trans_Username))

        # 作業用ディレクトリ削除 ＆ 作成 ----
        if config.Debug: print("making tmp dir...")
        if os.path.exists(TMP_DIR):
            du = shutil.rmtree(TMP_DIR)
            time.sleep(0.3)

        os.mkdir(TMP_DIR)
        if config.Debug: print("made tmp dir.")

        # 音声合成スレッド起動 ################
        if config.Debug: print("run, tts thread...")
        if config.gTTS_In or config.gTTS_Out:
            thread_gTTS = threading.Thread(target=gTTS_play)
            thread_gTTS.start()

        # 音声再生スレッド起動 ################
        if config.Debug: print("run, sound play thread...")
        thread_sound = threading.Thread(target=sound_play)
        thread_sound.start()

        # bot
        bot.run()

    except Exception as e:
        if config.Debug: print(e)
        input()  # stop for error!!

    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        cleanup()
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGINT, signal.SIG_DFL)


if __name__ == "__main__":
    sys.exit(main())
