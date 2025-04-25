#***************************************************************************#
# FloofBot
#***************************************************************************#

import discord
import platform
import random

from discord.ext import commands
from random import randint

#Variables
ownerID = 1009059379003265134
class Base(commands.Cog):

    """Cog for Base commands"""

    def __init__(self, bot):
        self.bot = bot

    
def setup(bot):
    bot.add_cog(Base(bot))