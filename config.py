import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
PUBG_API_KEY = os.getenv('PUBG_API_KEY')
PUBG_SHARD = os.getenv('PUBG_SHARD', 'steam')

HEADERS = {
    "Authorization": f"Bearer {PUBG_API_KEY}",
    "Accept": "application/vnd.api+json"
}

# Bot Settings
CFG_MINUTES = 2  # How often auto-checker runs

# Stats Configuration
LEADERBOARD_CONFIG = {
    'kills':           ('Fragger', 'Kills'),
    'team_kills':      ('The Traitor', 'Team Kills'),
    'self_damage':     ('Masochist', 'Self Dmg'),
    'blue_damage':     ('Zone Eater', 'Zone Dmg'),
    'distance_driven': ('Uber Driver', 'm Driven'),
    'revives':         ('Medic', 'Revives'),
    'bot_deaths':      ('Bot Food', 'Deaths to AI'),
    'headshots':       ('Brain Surgeon', 'Headshots'),
    'damage_dealt':    ('Damage Dealer', 'Damage')

}

# Stat Weights & Normalization (Value, Weight)
CFG_SNIPER = (150, 1.3); CFG_BRAIN_SURGEON = (1, 1.3); CFG_STORMTROOPER = (20, 2.5)
CFG_KNEECAPPER = (10, 1.5); CFG_BOXER = (1, 5.0); CFG_VULTURE = (100, 3.0)
CFG_THIRSTER = (50, 1.5); CFG_MEDIC = (0.5, 1.5); CFG_WINGMAN = (1, 1.2)
CFG_TRAITOR = (1, 5.0); CFG_SNAKE = (40, 2.0); CFG_SWIMMER = (50, 2.5)
CFG_DRIVER = (1000, 1.0); CFG_DOOR_DASHER = (15, 0.8); CFG_GRENADIER = (1.0, 1.4)
CFG_VANDAL = (1, 3.0); CFG_MASOCHIST = (1, 4.0); CFG_CAT = (0.5, 2.0)
CFG_SPONGE = (200, 1.1); CFG_BLUE_MAGNET = (30, 1.3); CFG_BOT_FOOD = (0, 10.0)
CFG_HOARDER = (40, 0.9); CFG_PINATA = (1, 6.0); CFG_GRAVE_ROBBER = (2.0, 1.3)
CFG_JUNKIE = (4, 1.2); CFG_UNDYING = (100, 1.1)

FACT_DEFINITIONS = {
    'medic': {'title': 'The Medic', 'normal': CFG_MEDIC[0], 'weight': CFG_MEDIC[1], 'unit': 'revives', 'format': '{:.0f}'},
    'sniper': {'title': 'Eagle Eye', 'normal': CFG_SNIPER[0], 'weight': CFG_SNIPER[1], 'unit': 'm kill', 'format': '{:.0f}'},
    'brain_surgeon': {'title': 'Brain Surgeon', 'normal': CFG_BRAIN_SURGEON[0], 'weight': CFG_BRAIN_SURGEON[1], 'unit': 'headshots', 'format': '{:.0f}'},
    'stormtrooper': {'title': 'Stormtrooper', 'normal': CFG_STORMTROOPER[0], 'weight': CFG_STORMTROOPER[1], 'unit': '% accuracy', 'format': '{:.1f}'},
    'kneecapper': {'title': 'The Kneecapper', 'normal': CFG_KNEECAPPER[0], 'weight': CFG_KNEECAPPER[1], 'unit': '% leg shots', 'format': '{:.1f}'},
    'snake': {'title': 'The Snake', 'normal': CFG_SNAKE[0], 'weight': CFG_SNAKE[1], 'unit': 'm crawled', 'format': '{:.0f}'},
    'swimmer': {'title': 'The Fish', 'normal': CFG_SWIMMER[0], 'weight': CFG_SWIMMER[1], 'unit': 'm swam', 'format': '{:.0f}'},
    'driver': {'title': 'Taxi Driver', 'normal': CFG_DRIVER[0], 'weight': CFG_DRIVER[1], 'unit': 'm driven', 'format': '{:.0f}'},
    'door_dasher': {'title': 'Door Dasher', 'normal': CFG_DOOR_DASHER[0], 'weight': CFG_DOOR_DASHER[1], 'unit': 'doors', 'format': '{:.0f}'},
    'grenadier': {'title': 'Bomber', 'normal': CFG_GRENADIER[0], 'weight': CFG_GRENADIER[1], 'unit': 'thrown', 'format': '{:.0f}'},
    'vandal': {'title': 'The Vandal', 'normal': CFG_VANDAL[0], 'weight': CFG_VANDAL[1], 'unit': 'tires pop', 'format': '{:.0f}'},
    'boxer': {'title': 'The Boxer', 'normal': CFG_BOXER[0], 'weight': CFG_BOXER[1], 'unit': 'melee dmg', 'format': '{:.0f}'},
    'wingman': {'title': 'The Wingman', 'normal': CFG_WINGMAN[0], 'weight': CFG_WINGMAN[1], 'unit': 'assists', 'format': '{:.0f}'},
    'traitor': {'title': 'The Traitor', 'normal': CFG_TRAITOR[0], 'weight': CFG_TRAITOR[1], 'unit': 'team dmg', 'format': '{:.0f}'},
    'masochist': {'title': 'The Masochist', 'normal': CFG_MASOCHIST[0], 'weight': CFG_MASOCHIST[1], 'unit': 'self dmg', 'format': '{:.0f}'},
    'cat': {'title': 'The Cat', 'normal': CFG_CAT[0], 'weight': CFG_CAT[1], 'unit': 'times knocked', 'format': '{:.0f}'},
    'sponge': {'title': 'The Sponge', 'normal': CFG_SPONGE[0], 'weight': CFG_SPONGE[1], 'unit': 'dmg taken', 'format': '{:.0f}'},
    'blue_magnet': {'title': 'Zone Magnet', 'normal': CFG_BLUE_MAGNET[0], 'weight': CFG_BLUE_MAGNET[1], 'unit': 'dmg', 'format': '{:.0f}'},
    'bot_food': {'title': 'The Bot', 'normal': CFG_BOT_FOOD[0], 'weight': CFG_BOT_FOOD[1], 'unit': '', 'format': 'Killed by AI'},
    'hoarder': {'title': 'The Hoarder', 'normal': CFG_HOARDER[0], 'weight': CFG_HOARDER[1], 'unit': 'items', 'format': '{:.0f}'},
    'pinata': {'title': 'Loot Pinata', 'normal': CFG_PINATA[0], 'weight': CFG_PINATA[1], 'unit': 'items delivered', 'format': '{:.0f}'},
    'grave_robber': {'title': 'Grave Robber', 'normal': CFG_GRAVE_ROBBER[0], 'weight': CFG_GRAVE_ROBBER[1], 'unit': 'dead loots', 'format': '{:.0f}'},
    'junkie': {'title': 'The Junkie', 'normal': CFG_JUNKIE[0], 'weight': CFG_JUNKIE[1], 'unit': 'boosts', 'format': '{:.0f}'},
    'undying': {'title': 'The Undying', 'normal': CFG_UNDYING[0], 'weight': CFG_UNDYING[1], 'unit': 'HP healed', 'format': '{:.0f}'},
    'vulture': {'title': 'The Vulture', 'normal': CFG_VULTURE[0], 'weight': CFG_VULTURE[1], 'unit': 'dmg/kill', 'format': '{:.0f}'},
    'thirster': {'title': 'The Thirster', 'normal': CFG_THIRSTER[0], 'weight': CFG_THIRSTER[1], 'unit': 'dmg to knocked', 'format': '{:.0f}'},
}