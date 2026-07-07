import os
import argparse
import asyncio

from dataclasses import dataclass

import sqlite3 as sql

import discord
from discord.ext import commands
from discord import app_commands

key = ''

parser = argparse.ArgumentParser(description='Discord bot')
parser.add_argument('-k', '--key', type=str, default='', help='Key for running Discord bot locally')
args = parser.parse_args()
if args.key:
    key = args.key
else:
    key = os.environ['DISCORD_API_KEY']


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

GUILD = discord.Object(id=1524041793400733716)
CABINS_ACTIVE_CATEGORY_NAME = 'Campsite Cabins'
CABINS_DECOMISSIONED_CATEGORY_NAME = 'Decomissioned Cabins'
BOT_COMMAND_EPHEMERALITY = True

cabins_active_category = None
cabins_decomissioned_category = None

@dataclass
class Cabin:
    camper_id: discord.Object
    channel_id: discord.Object
    cabin_number: int
    in_use: bool

os.makedirs('db', exist_ok=True)
connect = sql.connect('db/cabins.db')
cursor = connect.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS cabins (
    camper text,
    channel text,
    cabin_number integer,
    in_use integer
    )""")

try:
    cursor.execute("""CREATE TABLE cabin_number_current (
        val integer
        )""")
    cursor.execute('INSERT INTO cabin_number_current VALUES (1)')
except:
    pass

connect.commit()

cursor.execute('SELECT * FROM cabins')

def get_cabin_by_camper(camper_id):
    cursor.execute(f"SELECT * FROM cabins WHERE camper='{camper_id}'")
    cabin_raw = cursor.fetchone()
    return Cabin(int(cabin_raw[0]), int(cabin_raw[1]), cabin_raw[2], bool(cabin_raw[3])) if cabin_raw else None

def get_cabin_by_number(cabin_number):
    cursor.execute(f"SELECT * FROM cabins WHERE cabin_number={cabin_number}")
    cabin_raw = cursor.fetchone()
    return Cabin(int(cabin_raw[0]), int(cabin_raw[1]), cabin_raw[2], bool(cabin_raw[3])) if cabin_raw else None

def append_cabin(cabin):
    cursor.execute('INSERT INTO cabins VALUES (?, ?, ?, ?)', (str(cabin.camper_id), str(cabin.channel_id), cabin.cabin_number, int(cabin.in_use)))
    connect.commit()

def cabin_set_in_use(cabin, in_use):
    cursor.execute('UPDATE cabins SET in_use = ? WHERE cabin_number = ?', (int(in_use), cabin.cabin_number))

def cabin_number_current():
    cursor.execute('SELECT * FROM cabin_number_current')
    return cursor.fetchone()[0]

def cabin_number_current_increment():
    cursor.execute('UPDATE cabin_number_current SET val = ?', (cabin_number_current() + 1,))
    connect.commit()

async def get_or_make_cat(guild, cat_name):
    for c in guild.categories:
        if c.name == cat_name:
            return c
    return await guild.create_category(name=cat_name, overwrites={
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True),
    })

async def explode_cabin(guild, cabin):
    await guild.get_channel(cabin.channel_id).delete()
    cursor.execute(f"DELETE FROM cabins WHERE camper='{cabin.camper_id}'")
    connect.commit()

class Counselor(commands.Bot):
    async def on_ready(self):
        print(f'Logged in as {self.user}')

        try:
            synced = await self.tree.sync(guild=GUILD)
            print(f'Synced {len(synced)} commands to {GUILD.id}')
        except Exception as e:
            print(e)

    async def on_member_remove(self, member):
        cabin = get_cabin_by_camper(member.id)
        if cabin:
            await explode_cabin(member.guild, cabin)

bot = Counselor(command_prefix='.', intents=intents)

class ReviveView(discord.ui.View):

    def __init__(self, cabin):
        super().__init__(timeout=30.0)
        self.cabin = cabin

    @discord.ui.button(label='Yes', style=discord.ButtonStyle.blurple)
    async def revive_cabin(self, interaction: discord.Interaction, button: discord.ui.Button):

        await bot.get_channel(self.cabin.channel_id).edit(category=cabins_active_category, overwrites={
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True),
            interaction.guild.get_member(self.cabin.camper_id): discord.PermissionOverwrite(read_messages=True)
        })
        cabin_set_in_use(self.cabin, True)
        await interaction.response.send_message('Good to go!', ephemeral=BOT_COMMAND_EPHEMERALITY)
        self.stop()

    @discord.ui.button(label='No', style=discord.ButtonStyle.gray)
    async def ignore_cabin(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message('Gotcha. I\'ll wait for Mosin to clean out the cabin first.', ephemeral=BOT_COMMAND_EPHEMERALITY)
        self.stop()

@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
@bot.tree.command(name='cabin', description='Make a personal cabin for a camper.', guild=GUILD)
async def find_cabin(interaction: discord.Interaction, member: discord.Member):
    cabin = get_cabin_by_camper(member.id)
    if cabin and cabin.in_use:
        await interaction.response.send_message(f'This camper already has a cabin: <#{cabin.channel_id}>', ephemeral=BOT_COMMAND_EPHEMERALITY)
        return
    elif cabin:
        await interaction.response.send_message('It looks like Mosin just finished cleaning this cabin. Should I give it back to the camper?', view=ReviveView(cabin), ephemeral=BOT_COMMAND_EPHEMERALITY)
        return


    global cabins_active_category
    if not cabins_active_category:
        cabins_active_category = await get_or_make_cat(interaction.guild, CABINS_ACTIVE_CATEGORY_NAME)

    cabin = await cabins_active_category.create_text_channel(
        name=f'cabin-{cabin_number_current()}',
        overwrites={
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True),
            member: discord.PermissionOverwrite(read_messages=True)
        })
    append_cabin(Cabin(member.id, cabin.id, cabin_number_current(), True))
    cabin_number_current_increment()
    await interaction.response.send_message(f'Made a cabin: <#{cabin.id}>', ephemeral=BOT_COMMAND_EPHEMERALITY)

@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
@bot.tree.command(name='dcabin', description='Decomission a camper\'s cabin.', guild=GUILD)
async def decomission_cabin(interaction: discord.Interaction, cabin_no: int):
    cabin = get_cabin_by_number(cabin_no)
    if not cabin:
        await interaction.response.send_message(f'I couldn\'t find that cabin!', ephemeral=BOT_COMMAND_EPHEMERALITY)
        return
    elif not cabin.in_use:
        await interaction.response.send_message(f'<#{cabin.channel_id}> is out of comission!', ephemeral=BOT_COMMAND_EPHEMERALITY)
        return
    
    global cabins_decomissioned_category
    if not cabins_decomissioned_category:
        cabins_decomissioned_category = await get_or_make_cat(interaction.guild, CABINS_DECOMISSIONED_CATEGORY_NAME)

    await bot.get_channel(cabin.channel_id).edit(category=cabins_decomissioned_category, overwrites={
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.guild.me: discord.PermissionOverwrite(read_messages=True),
        interaction.guild.get_member(cabin.camper_id): discord.PermissionOverwrite(read_messages=False)
    })
    cabin_set_in_use(cabin, False)
    await interaction.response.send_message(f'<#{cabin.channel_id}> is out of comission!', ephemeral=BOT_COMMAND_EPHEMERALITY)

@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
@bot.tree.command(name='ecabin', description='Explode a camper\'s cabin.', guild=GUILD)
async def explode_cabin_command(interaction: discord.Interaction, cabin_no: int):
    cabin = get_cabin_by_number(cabin_no)
    if not cabin:
        await interaction.response.send_message(f'I couldn\'t find that cabin!', ephemeral=BOT_COMMAND_EPHEMERALITY)
        return

    await explode_cabin(interaction.guild, cabin)
    await interaction.response.send_message(f'It has been done.', ephemeral=BOT_COMMAND_EPHEMERALITY)

bot.run(key)
