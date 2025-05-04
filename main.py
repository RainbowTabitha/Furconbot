#***************************************************************************#
# FloofBot
#***************************************************************************#


import os
import platform
import discord
import json
from pathlib import Path

from cogs.base import Base
from cogs.telegram import TelegramRSSBridge

from discord.ext import tasks
from discord.ext import commands

# Load keys from keys.json
with open('keys.json', 'r') as f:
    keys = json.load(f)

#Intents
intents = discord.Intents.all()

#Define Client
bot = commands.Bot(description="FurCon Bot", command_prefix=commands.when_mentioned_or("/"), intents=intents, activity=discord.Game(name='Fursuit Games'))

@bot.event
async def on_ready():
  memberCount = len(set(bot.get_all_members()))
  serverCount = len(bot.guilds)
  print("                                                                ")
  print("################################################################") 
  print(f"Furcon Bot                                                      ")
  print("################################################################") 
  print("Running as: " + bot.user.name + "#" + bot.user.discriminator)
  print(f'With Client ID: {bot.user.id}')
  print("\nBuilt With:")
  print("Python " + platform.python_version())
  print("Py-Cord " + discord.__version__)

# From Telegram
bot.add_cog(TelegramRSSBridge(bot))
bot.add_cog(Base(bot))

# Get Discord token from keys.json
TOKEN = keys.get("discord_token")
bot.run(TOKEN)