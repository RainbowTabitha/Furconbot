#***************************************************************************#
# FloofBot
#***************************************************************************#


import os
import platform
import discord
from dotenv import load_dotenv

from cogs.base import Base
from cogs.telegram import TelegramRSSBridge

from discord.ext import tasks
from discord.ext import commands

# Load environment variables from .env file
load_dotenv()

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

# To Discord
TOKEN = os.environ.get("DISCORD_TOKEN")
bot.run(TOKEN)