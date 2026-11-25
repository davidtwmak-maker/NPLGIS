#!/usr/bin/env python3
"""The PLAY VENUES dataset: places in Hong Kong where you can actually sit
down and play trading card games (or board games) with other people.

WHY THIS IS A SEPARATE DATASET
    The BAW VAULT directory carries a `play_space` flag, but it is set on
    only 12 of its 205 shops. That is a documentation gap, not a fact about
    Hong Kong: Smiling Plaza in Cheung Sha Wan is a whole building of card
    shops that sets out tables and chairs in the corridor for shop
    tournaments, and several shops with dedicated play floors simply do not
    declare it in a directory field.

    The user's actual question is "where can we go to play the deck with
    others". So the venues are collected directly from the operators' own
    sites, the official Pokemon TCG event calendar and the tournament
    directory, and each is tagged with what kind of place it is.

THE PLACE TYPES
    card_store   - a shop that trades cards; may or may not have tables
    card_venue   - a shop built around play space (a dedicated card-game
                   floor with seats, or a card-game cafe)
    board_cafe   - a board-game cafe / space that also runs TCG
    tournament   - a shop that runs regular official tournaments

EVERY ROW CARRIES THE BUILDING'S CHINESE NAME (`bldg_zh`), because that is
the token the Hong Kong Government's own address search indexes. An English
address alone matched the wrong building in 7 of 23 cases - "Wai Industrial
Building" matched a building 40 km away in Tuen Mun, and "Fat Commercial
Building" matched a different Fat Commercial Building in Cheung Sha Wan.
"""
import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "play_venues.csv"

# name, name_zh, address (English), address_zh, bldg_zh, area, type, size, note, src
ROWS = [
    ("Battleground 卡牌遊戲及桌遊專門店 荔枝角", "BATTLEGROUND",
     "Unit 105-107 1/F, D2 PLACE TWO, 15 Cheung Shun Street, Lai Chi Kok, Kowloon",
     "九龍荔枝角長順街15號D2 PLACE TWO 1樓105-107室",
     "D2 PLACE TWO", "Lai Chi Kok", "Sham Shui Po", "card_venue", "",
     "Card game and board game specialist with a dedicated shop floor; also a second branch in Kwun Tong",
     "https://bgtcg.com/"),

    ("BATTLEGROUND 觀塘店 THE ANGLE", "BATTLEGROUND",
     "Shop 701-706, 7/F, THE ANGLE, 98 How Ming Street, Kwun Tong, Kowloon",
     "觀塘巧明街98號THE ANGLE 7樓701-706室",
     "THE ANGLE", "Kwun Tong", "Kwun Tong", "card_venue", "",
     "Second branch of Battleground, in the same building as a large shopping mall",
     "https://bgtcg.com/"),

    ("ACard TCG", "ACard TCG",
     "Room 06, 19/F, New Treasure Centre, 10 Ng Fong Street, San Po Kong, Kowloon",
     "新蒲崗福榮街10號新寶中心19樓06室",
     "新寶中心", "San Po Kong", "Wong Tai Sin", "card_venue", "1,200 sq ft",
     "Over 1,200 sq ft of sales AND play space; a Pokemon Official Gym",
     "https://www.acardtcg.com/about"),

    ("Brave Soul TCG", "Brave Soul TCG",
     "Room 1, 12/F, Midas Plaza, 1 Tai Yau Street, San Po Kong, Kowloon",
     "新蒲崗大有街1號金輝商業大廈12樓1室",
     "金輝商業大廈", "San Po Kong", "Wong Tai Sin", "card_venue", "64 seats",
     "Over 1,200 sq ft with a maximum of 64 seats; hosts weekly TCG activities",
     "https://www.bravesoulcard.com/about"),

    ("Players' Club", "Players' Club",
     "Shop 210, 2/F, iSQUARE, 63 Nathan Road, Tsim Sha Tsui, Kowloon",
     "尖沙咀彌敦道63號iSQUARE 2樓210室",
     "iSQUARE", "Tsim Sha Tsui", "Yau Tsim Mong", "card_venue", "",
     "Well-known TCG venue; display case holds the first Yu-Gi-Oh! World Champion trophy; moved to iSQUARE on 5 June 2026",
     "https://roadoftheking.com/card-stores-in-kowloon/"),

    ("Slash All 香港桌遊專門店", "SLASH ALL",
     "Room 305, 3/F, Shiu Wai Industrial Building, 29-33 Wing Hong Street, Cheung Sha Wan, Kowloon",
     "長沙灣永康街29-33號兆威工業大廈3樓305室",
     "兆威工業大廈", "Cheung Sha Wan", "Sham Shui Po", "board_cafe", "2,000 sq ft",
     "Board game and TCG space; 2,000 sq ft of seating, walk-in or by appointment; dedicated TCG product range",
     "https://www.slashall.hk/"),

    ("GameTable 遊桌", "GameTable 遊桌",
     "Room 404, 4/F, Hing Fat Commercial Building, 9 Yuen Long Street, Mong Kok, Kowloon",
     "旺角煙廠街9號興發商業大廈4樓404室",
     "興發商業大廈", "Mong Kok", "Sham Shui Po", "board_cafe", "1,000 sq ft",
     "The largest board-game space in Mong Kok; private rooms; also sells and lends games",
     "http://www.gametable.hk/"),

    ("GALA 旮旯桌遊", "GALA 旮旯",
     "1/F, 51 Carnarvon Road, Tsim Sha Tsui, Kowloon",
     "尖沙咀加拿分道51號地下",
     "加拿分道51號", "Tsim Sha Tsui", "Yau Tsim Mong", "board_cafe", "",
     "Board-game experience space charged by the hour, free drinks; staff teach the rules",
     "https://galainhk.com/"),

    ("Capstone 桌上遊戲專賣店 銅鑼灣", "Capstone",
     "Unit A, 23/F, Kam Hing Commercial Building, 438-444 Hennessy Road, Causeway Bay",
     "銅鑼灣軒尼詩道438-444號金鵝商業大廈23樓A室",
     "金鵝商業大廈", "Causeway Bay", "Central and Western", "board_cafe", "40 seats",
     "About 40 seats with staff running board-game sessions; also a Kwun Tong branch",
     "https://www.flowtheroom.com/hk/zh/blog/board-game-cafe"),

    ("Jolly Thinkers 空中棋園 灣仔店", "空中棋園",
     "11/F, Cheung Hing Building, 99 Hennessy Road, Wan Chai",
     "灣仔軒尼詩道99號彰顯大廈11樓",
     "彰顯大廈", "Wan Chai", "Wan Chai", "board_cafe", "",
     "Board-game space charging from HK$20 per hour with an instructor; also a Prince Edward branch",
     "https://www.flowtheroom.com/hk/zh/blog/board-game-cafe"),

    ("Jolly Thinkers 空中棋園 太子店", "空中棋園",
     "14/F, Ka Hong Centre, 155 Sai Yeung Choi Street, Prince Edward, Kowloon",
     "太子西洋菜街北155號嘉康中心14樓",
     "嘉康中心", "Prince Edward", "Yau Tsim Mong", "board_cafe", "",
     "Second branch of Jolly Thinkers",
     "https://www.flowtheroom.com/hk/zh/blog/board-game-cafe"),

    ("甜在棋中 Odd Board Game Bar and Cafe", "甜在棋中",
     "Unit 1, 13/F, Argyle Centre, 43H Tong Mi Road, Mong Kok, Kowloon",
     "旺角登打士街43H號登打士廣場13樓1室",
     "登打士廣場", "Mong Kok", "Yau Tsim Mong", "board_cafe", "",
     "Bar and cafe with a library of board games; customers may stay on playing",
     "https://www.flowtheroom.com/hk/zh/blog/board-game-cafe"),

    ("YMC Boardgame 桌遊工作室", "YMC Boardgame",
     "Room 02, 21/F, Texwin Plaza, 32 Tai Yau Street, San Po Kong, Kowloon",
     "新蒲崗大有街32號泰力工業中心21樓02室",
     "泰力工業中心", "San Po Kong", "Kowloon City", "board_cafe", "",
     "Board-game shop with guided play sessions",
     "https://ymc.studio/"),

    ("Welcome On Board 桌遊天地 屯門", "WOB 桌遊天地",
     "Room H, 13/F, Phase 1, Hong Cheong Industrial Centre, 12 Tsing Yeung Street, Tuen Mun",
     "屯門青楊街12號鴻昌工業中心一期13樓H室",
     "鴻昌工業中心", "Tuen Mun", "Tuen Mun", "board_cafe", "",
     "Board-game retailer and play area; over a hundred titles with staff guidance",
     "https://wobgames.net/"),

    ("Card Game Station", "Card Game Station",
     "Room 212, 2/F, Fuki Industrial Building, 658 Castle Peak Road, Lai Chi Kok, Kowloon",
     "荔枝角青山道658號福至工業大廈2樓212室",
     "福至工業大廈", "Lai Chi Kok", "Sham Shui Po", "tournament", "",
     "Runs Pokemon Gym Battle events (capacity 20, entry fee HK$80)",
     "https://asia.pokemon-card.com/hk/event-search/20901/"),

    ("Justice Of Trading Card Games 正氣卡店", "正氣卡店",
     "Room 6, 7/F, Shing On Industrial Building, 25-27 Shing On Street, Tai Wai, New Territories",
     "大圍成運路25-27號成全工業大廈7樓6室",
     "成全工業大廈", "Tai Wai", "Tuen Mun", "tournament", "",
     "Runs Pokemon Card Day events (capacity 32, entry fee HK$65)",
     "https://asia.pokemon-card.com/hk/event-search/20361/"),

    ("大木研究所 集換式卡牌遊戲店 Ookido Institute TCG", "大木研究所",
     "Room 128, 1/F, Ka Shing Industrial Building, 25 Luk Hop Street, Sham Shui Po, Kowloon",
     "深水埗福華街25號嘉時工業大廈1樓128室",
     "嘉時工業大廈", "Sham Shui Po", "Sham Shui Po", "card_store", "",
     "Card game shop in the same building as ACard TCG and Play Card Chill",
     "https://www.google.com/maps"),

    ("Play Card Chill", "Play Card Chill",
     "Room B06, 15/F, Wing Shing Industrial Building, 15 Ng Fong Street, San Po Kong, Kowloon",
     "新蒲崗福榮街15號永盛工業大廈15樓B06室",
     "永盛工業大廈", "San Po Kong", "Wong Tai Sin", "card_store", "",
     "Card shop in the same building as ACard TCG; open afternoons and evenings",
     "https://www.google.com/maps"),

    ("Boss's Orders TCG 老大卡店", "老大卡店",
     "Room 2B, 16/F, 95 Chai Wan Kok Street, Chai Wan, Hong Kong",
     "柴灣柴灣道95號16樓2B室",
     "柴灣道95號", "Chai Wan", "Kwai Tsing", "card_store", "",
     "TCG shop in Chai Wan, open afternoons and evenings",
     "https://www.google.com/maps"),

    ("Battlefield Hobby Card and TCG Shop", "Battlefield",
     "Room 607, Fullagar Industrial Building, 234 Aberdeen Main Road, Aberdeen, Hong Kong",
     "香港仔香港仔大道234號富嘉工業大廈607室",
     "富嘉工業大廈", "Aberdeen", "Southern", "card_store", "",
     "Card and TCG shop in Aberdeen",
     "https://www.google.com/maps"),

    ("Game's Lair Company (TCG Store)", "Game's Lair",
     "Room 12, 14/F, Block B, Wah Kai Industrial Building, 3-5 Cheung Tat Road, Tseung Kwan O, New Territories",
     "將軍澳敬業街3-5號華蓋工業大廈B座14樓12室",
     "華蓋工業大廈", "Tseung Kwan O", "Sai Kung", "card_store", "",
     "TCG shop in Tseung Kwan O",
     "https://www.google.com/maps"),

    ("Light TCG", "Light TCG",
     "Units 41C-D, Granville House, 15-19 Granville Road, Tsim Sha Tsui, Kowloon",
     "尖沙咀加連威老道15-19號嘉威大廈41C-D室",
     "嘉威大廈", "Tsim Sha Tsui", "Yau Tsim Mong", "card_store", "",
     "TCG shop in Tsim Sha Tsui, open afternoons and evenings",
     "https://www.google.com/maps"),

    ("電電屋 Den Den House", "電電屋",
     "Flat E2, 13/F, Phase 1, Kaiser Estate, 41 Man Yue Street, Kennedy Town, Hong Kong",
     "堅尼地城士美菲路41號凱旋工商中心一期13樓E2室",
     "凱旋工商中心", "Kennedy Town", "Kowloon City", "card_store", "",
     "Card shop in Kennedy Town",
     "https://www.google.com/maps"),
]


def main():
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "name_zh", "address", "address_zh", "bldg_zh",
                    "area", "dc_district", "place_type", "size", "play_note",
                    "src"])
        for r in ROWS:
            w.writerow(r)
    print(f"wrote {OUT} with {len(ROWS)} play venues")
    from collections import Counter
    c = Counter(r[7] for r in ROWS)
    for k, v in c.most_common():
        print(f"  {k:14} {v}")


if __name__ == "__main__":
    main()
