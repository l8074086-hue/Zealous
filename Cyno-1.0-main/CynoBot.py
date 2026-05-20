import discord
from discord.ext import commands
import logging
import requests
from dotenv import load_dotenv
import os   

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True  
intents.members = True  
secret_role = "Targeted"
bot = commands.Bot(command_prefix='%', intents=intents)
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} - {bot.user.id}')
    print('------')
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    print(f'{message.author}:{message.channel}: {message.content}')
    await bot.process_commands(message)
@bot.event
async def on_member_join(member):
    await member.send(f'Welcome to the server, {member.name}!')
@bot.command()
async def hello(ctx):
    await ctx.send(f"Hello, {ctx.author.mention}!")
@bot.command()
async def target(ctx):
    role = discord.utils.get(ctx.guild.roles, name = secret_role )
    if role:
        await ctx.author.add_roles(role)
        await ctx.send(f"You are now {secret_role} by ME! {ctx.author.mention}")
    else:
        await ctx.send(f"Role doesn't even exist bozo")
@bot.command()
async def untarget(ctx):
    role = discord.utils.get(ctx.guild.roles, name = secret_role )
    if role:
        await ctx.author.remove_roles(role)
        await ctx.send(f"You are no longer {secret_role} by ME! {ctx.author.mention}")
    else:
        await ctx.send(f"Role doesn't even exist bozo")
@bot.command()
async def Cyno(ctx, *, message: str):
    if ctx.author == "kevon6789_58439":
        await ctx.send("You cannot use Cyno, you are too powerful already.")
        return
    messages= []
    async for msg in ctx.channel.history(limit=10):
        if msg.author == bot.user:
            messages.append({"role": "assistant", "content": msg.content})
        else:
            messages.append({"role": "user", "content": msg.content})
        context = "\n".join([f"{m['role']}: {m['content']}" for m in messages]) 
    try:
        resp = requests.post("http://localhost:5000/talk", json={"message": message, "context": context})
        reply = resp.json().get("reply", "I didn't get a response.")
        await ctx.send(f"Cyno: {reply}")
    except Exception as e:
        await ctx.send(f"Error communicating with the server: {e}")
@bot.command()
async def Sunset(ctx, *, message: str):
    try:
        resp = requests.post("http://localhost:5000/sunset", json={"message": message})
        reply = resp.json().get("reply", "I didn't get a response.")
        await ctx.send(f"Sunset: {reply}")
    except Exception as e:
        await ctx.send(f"Error communicating with the server: {e}")
@bot.command()
async def Memory(ctx):
    memory = []

    async for msg in ctx.channel.history(limit=5):
        memory.append({
            "author": msg.author.name,
            "content": msg.content
        })

    if not memory:
        await ctx.send("Memory is empty 💀")
        return

    await ctx.send("Memory log:")
    for mem in reversed(memory):
        await ctx.send(f"{mem['author']}: {mem['content']}")

@bot.command()
async def Manual(ctx):
    if ctx.author.name == "kevon6789_58439":
        activated = True
        while activated:
            user_input = input()
            if user_input.lower() == "exit":
                activated = False
                await ctx.send("Exiting manual mode.")
            
            await ctx.send(f"{user_input}")
    else:
        await ctx.send("You are not authorized to use this command.")

@bot.command(name="cyno_forget")
async def cyno_forget(ctx):
    try:
        res = requests.post("http://127.0.0.1:5000/reset_memory", timeout=3)
        data = res.json()
        await ctx.send(data.get("reply", "Memory reset. Probably."))
    except Exception as e:
        await ctx.send("Failed to reset memory. Cyno is clinging to his past.")
@bot.command(name= "memory_print")
async def cyno_memory(ctx):
    try:
        res = requests.get("http://127.0.0.1:5000/get_memory", timeout=3)
        data = res.json()
        await ctx.send(f"Cyno's Memory: {data.get('memory', 'No memory found.')}")
    except Exception as e:
        await ctx.send("Failed to retrieve memory. Cyno's mind is a mystery.")
bot.run(TOKEN, log_handler=handler, log_level=logging.DEBUG)