from rgbmatrix import RGBMatrix, RGBMatrixOptions

from io import BytesIO
from PIL import Image

import board
import busio
from digitalio import DigitalInOut
import RPi.GPIO

import json
import requests

import spotipy
from spotipy.oauth2 import SpotifyOAuth


import time
import datetime
import concurrent.features
import os

# Overall file. This python file uses the spotify API
# to ping what song is currently playing and then takes the album cover
# of that song and loads it onto the RGB matrix. This is primarily
# achieved via the spotipy library and the rgbmatrix library which
# is found at: https://github.com/hzeller/rpi-rgb-led-matrix


# Main:
# In future this will be updated to take in GPIO inputs for buttons, switches
# and a bluetooth signal from the ESP 32 alarm.
# This task_manager task creates a thread for constantly updating the
# screen. Initially, I assumed that this would increase the noise and flickering
# of the screen, but the LEDs assume a proper state quick enough that
# it is not possible to see any difference between non-threaded and
# threaded performance on the screen.


def task_manager():
    print("Initializing everything")
    matrix = init_circuit()
    while True:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            f1 = executor.submit(
                spotifyTask("Nothing", "", "", "/root/spotifyScript/cache_img", matrix)
            )


# The overall spotify task. Authenticates, parses the json, names the file, saves
# the file and then loads it to the screen.
def spotifyTask(status, file_name, image_url, cache_path, matrix):
    sp = authenticate()
    overall_json_resp = jsonExtract(sp)

    # Put currently playing jsonOutput in jsonFile
    # saveToJson(overall_json_resp)

    status, file_name, image_url = setNames(
        status, file_name, image_url, overall_json_resp
    )

    # Print file_name post main logic to console
    # print(file_name)

    img = ImageGenerate(status, file_name, image_url, cache_path)

    # print(matrix)

    if img != 0:
        display_image(matrix, img)
    else:
        temp_path = cache_path + "/black_image/black.jpg"
        img = Image.open(temp_path)
        display_image(matrix, img)

    # time.sleep(10)
    return "Done with Spotify Task"


# Authenticates the API with a specific scope, of ... everything.
# This can be reduces to a threaded task that runs every ~8 hours
# because that is when the token refreshes.
# Will be done on a future version.
def authenticate():
    with open("/root/spotifyScript/spotify_tokens.json") as f:
        spotify_tokens = json.load(f)

    scope = [
        "user-read-currently-playing",
        "user-read-playback-state",
        "user-modify-playback-state",
        "user-library-read",
        "streaming",
        "user-read-playback-position",
        "playlist-read-private",
    ]

    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=spotify_tokens["client_id"],
            client_secret=spotify_tokens["client_secret"],
            redirect_uri=spotify_tokens["redirect_uri"],
            scope=scope,
            open_browser=False,
        )
    )


# Calls on the API for a json response with all the information required.
def jsonExtract(spotifyAuth):
    return spotifyAuth.current_playback(additional_types="episode")


# Standard. Will ave the json response from api as a json file
def saveToJson(jsonInput):
    with open("json_resp.json", "w") as fp:
        json.dump(jsonInput, fp)


# Logic for setting the name of the file.
# If a song is playing, it will return the status of the song playing
# and will name the file accordingly, by parsing the json response
# from the API for the link of the album cover.
# Then it will return the current status of operation
# and the filename and url.
def setNames(status, file_name, image_url, overall_json_resp):

    if overall_json_resp == None:
        status, file_name, image_url = doNothing(status, file_name, image_url)

    else:
        if bool(overall_json_resp.get("is_playing")):
            if overall_json_resp.get("currently_playing_type") == "episode":
                # Sanity check, sometimes closing app while playing keeps
                # going, to avoid this, here it is
                progress = int(overall_json_resp["progress_ms"])
                duration = int(overall_json_resp["item"]["duration_ms"])

                if progress >= duration:
                    status, file_name, image_url = doNothing(
                        status, file_name, image_url
                    )

                else:
                    file_name = overall_json_resp["item"]["name"]
                    image_url = overall_json_resp["item"]["images"][0]["url"]
                    status = "Podcast"

                # print(status)

            if overall_json_resp.get("currently_playing_type") == "track":
                # Sanity check, sometimes closing app while playing keeps
                # going, to avoid this, here it is
                progress = int(overall_json_resp["progress_ms"])
                duration = int(overall_json_resp["item"]["duration_ms"])

                if progress >= duration:
                    status, file_name, image_url = doNothing(
                        status, file_name, image_url
                    )

                else:
                    file_name = overall_json_resp["item"]["album"]["name"]
                    image_url = overall_json_resp["item"]["album"]["images"][0]["url"]
                    status = "Song"

                    # print(status)

        else:
            status, file_name, image_url = doNothing(status, file_name, image_url)

    return status, file_name, image_url


# Sets status for not doing anything.
def doNothing(status, file_name, image_url):
    file_name = ""
    image_url = ""
    status = "Nothing"

    # print(status)

    return status, file_name, image_url


# A function that looks through and generates an image and saves it
# if it is not already saved.
# Saves an image if a song is playing, and it has not been saved already.
# Has smaller logic for differentiating between podcast and song images
# and sorts the logic for not generating an image, for saving power.
def ImageGenerate(status, file_name, image_url, cache_path):
    img = 0
    if not (status == "Nothing"):
        file_name = removeIllegalChars(file_name)
        image_name = file_name.strip()
        image_name = image_name + ".jpg"

        if status == "Podcast":
            image_name = os.path.join(cache_path + "/podcasts", image_name)

            if os.path.isfile(image_name):
                # print("Loading cached image")
                img = Image.open(image_name)

            else:
                img_response = requests.get(image_url)
                img = Image.open(BytesIO(img_response.content))
                # print("Caching image")
                img.save(image_name, "jpeg")

        else:
            image_name = os.path.join(cache_path + "/songs", image_name)

            if os.path.isfile(image_name):
                # print("Loading cached image")
                img = Image.open(image_name)

            else:
                img_response = requests.get(image_url)
                img = Image.open(BytesIO(img_response.content))
                # print("Caching image")
                img.save(image_name, "jpeg")
    return img


# A poorly made function that removes illegal characters from the string it is passed
# Can be improved, will be in a future version
def removeIllegalChars(string):
    string = string.replace("#", " ")
    string = string.replace("%", " ")
    string = string.replace("&", " ")
    string = string.replace("{", " ")
    string = string.replace("}", " ")
    string = string.replace('"\\"', " ")
    string = string.replace("<", " ")
    string = string.replace(">", " ")
    string = string.replace("*", " ")
    string = string.replace("?", " ")
    string = string.replace("/", " ")
    string = string.replace("$", " ")
    string = string.replace("!", " ")
    string = string.replace("'", " ")
    string = string.replace('"', " ")
    string = string.replace(":", " ")
    string = string.replace("@", " ")
    string = string.replace("+", " ")
    string = string.replace("`", " ")
    string = string.replace("|", " ")
    string = string.replace("=", " ")

    return string


# Calls on the HZeller RGB matrix library and converts the jpg matrix
# into values that the RGB matrix can use.
def display_image(matrix, img):
    # print("Displaying image")
    img.thumbnail((matrix.width, matrix.height), Image.ANTIALIAS)
    matrix.SetImage(img.convert("RGB"))


# Calls on the HZeller RGB matrix library that was installed from github.
# Sets the conditions of the current RGB matrix, 64 x 64, with
# a PWM setup. Thus initializing and setting the GPIO pins
# to properly correspond with the matrix.
def init_circuit():
    options = RGBMatrixOptions()

    # if args.led_gpio_mapping != None:
    #     options.hardware_mapping = args.led_gpio_mapping

    options.hardware_mapping = "adafruit-hat-pwm"
    options.rows = 64
    options.cols = 64
    options.chain_length = 1
    options.parallel = 1
    options.row_address_type = 0
    options.multiplexing = 0
    options.pwm_bits = 11
    options.brightness = 100
    options.pwm_lsb_nanoseconds = 130
    options.led_rgb_sequence = "RGB"
    options.pixel_mapper_config = ""
    options.panel_type = ""
    options.show_refresh_rate = 0
    options.gpio_slowdown = 1
    options.disable_hardware_pulsing = True
    options.drop_privileges = False

    # if args.led_show_refresh:
    #     options.show_refresh_rate = 1
    # if args.led_slowdown_gpio != None:
    #     options.gpio_slowdown = args.led_slowdown_gpio
    # if args.led_no_hardware_pulse:
    #     options.disable_hardware_pulsing = True
    # if not args.drop_privileges:
    #     options.drop_privileges=False

    matrix = RGBMatrix(options=options)
    # print("Initialized RGB Matrix")

    return matrix


if __name__ == "__main__":
    task_manager()
