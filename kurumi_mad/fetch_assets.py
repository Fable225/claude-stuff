#!/usr/bin/env python3
"""Download the image assets for the MAD into ./assets (see SOURCES.md).

audio.mp3 and map.osu are not downloaded — put your own copies in ./assets.
Fonts: `npm i @expo-google-fonts/{noto-sans-tc,noto-sans-jp,noto-serif-tc,dela-gothic-one,dotgothic16,bebas-neue,jetbrains-mono}`
and copy the .ttf files named in render.py FONTS into ./assets/fonts.
"""
import hashlib
import os
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "assets")
# Wikimedia asks automated clients to identify themselves; put your own contact here.
UA = {"User-Agent": "KurumiMadFetch/1.0 (set-your-contact-here) python-urllib"}

SITE = "https://fxkurumi-info.com/"
OFFICIAL = {
    "top_visual_visual1.jpg": "assets/img/top/visual/visual1.jpg",
    "top_visual_teaser.png": "assets/img/top/visual/teaser.png",
    "top_losscut_losscut_bg.jpg": "assets/img/top/losscut/losscut_bg.jpg",
    "top_losscut_losscut_kurumi.png": "assets/img/top/losscut/losscut_kurumi.png",
    "top_losscut_losscut_txt.png": "assets/img/top/losscut/losscut_txt.png",
    "music_jk.jpg": "assets/img/music/jk.jpg",
    **{f"character_main_{c}.png": f"assets/img/character/main_{c}.png" for c in ("kurumi", "mochiko", "mebuki", "yasuko")},
}
COMMONS = {
    "tulip.jpg": "Semper_Augustus_Tulip_17th_century.jpg",
    "southsea.jpg": "Edward_Matthew_Ward_(1816-1879)_-_The_South_Sea_Bubble,_a_Scene_in_'Change_Alley_in_1720_-_N00432_-_National_Gallery.jpg",
    "railway.png": "Off_the_Rail_(Punch_Cartoon).png",
    "crash1929.jpg": "Crowd_outside_nyse.jpg",
    "japan.jpg": "Market_centre_in_Tokyo_stock_exchange.jpg",
    "dotcom.jpg": "Pets.com_Sock_Puppet_(12935451763).jpg",
    "lehman2.jpg": "Lehman_Brothers-NYC-20080915.jpg",
    "snb.jpg": "SNB_(Swiss_National_Bank)_headquarters_at_Bundesplatz,_Bern,_Switzerland_(Ank_Kumar,_Infosys_Limited)_06.jpg",
    "bitcoin.jpg": "Bitcoin_BTC_golden_coin_with_the_symbol.jpg",
    "gamestop.jpg": "GameStop_store_in_Glen_Ellyn_Illinois.jpg",
    "nft3.jpg": "Node_NFT_art_gallery.jpg",
    "ftx.jpg": "FTX_Arena_Downtown_Miami_-_But_not_for_long_-_11_November_2022.jpg",
    "ai.png": "NVIDIA_H100_(极客湾Geekerwan)_024.png",
}


def get(url, dst, pause=0.0):
    if os.path.exists(dst):
        return True
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
    except Exception as e:  # noqa: BLE001
        print("  failed:", url, e)
        return False
    with open(dst, "wb") as f:
        f.write(data)
    print("  ok:", os.path.relpath(dst, HERE))
    time.sleep(pause)
    return True


def main():
    for name, path in OFFICIAL.items():
        get(SITE + path, os.path.join(OUT, "kurumi/off", name))
    for ep in range(1, 8):
        for i in range(1, 7):
            get(f"{SITE}story/img/ep{ep:02d}/{ep:02d}_{i}.jpg", os.path.join(OUT, "kurumi/ep", f"{ep:02d}_{i}.jpg"))
    for name, f in COMMONS.items():
        m = hashlib.md5(f.encode()).hexdigest()
        q = urllib.parse.quote(f)
        dst = os.path.join(OUT, "hist", name)
        # Commons only serves a fixed set of thumbnail widths; fall back to smaller ones
        for w in (1280, 960, 500):
            if get(f"https://upload.wikimedia.org/wikipedia/commons/thumb/{m[0]}/{m[:2]}/{q}/{w}px-{q}", dst, pause=4):
                break
            time.sleep(6)


if __name__ == "__main__":
    main()
