import discord
from discord.ext import commands
from dotenv import load_dotenv
import logging
import os

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
# Logging Configuration
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
logger = logging.getLogger('Cyno')
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)

TOKEN = os.getenv("CYNO_TOKEN")
bot = commands.Bot(command_prefix='why', intents=intents)

@bot.event
async def on_message(message):
    ctx = await bot.get_context(message)
    channel = message.channel
    if message.author == bot.user:
        return
    if "Hello?" in message.content:
        await ctx.send("...")
    if "What?" in message.content:
        await ctx.send("...")
    if "Cyno where" in message.content:
        await ctx.send("..the weather is 90 degrees celsius")
    if "I didn't ask that" in message.content: 
        await ctx.send("..you did")
    if message.guild and message.guild.id == 1465570284584173733:
        print(f'{message.channel}: {message.content}')
bot.run(TOKEN)
