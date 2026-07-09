import os

from dataclasses import dataclass

from dotenv import load_dotenv
import sqlite3 as sql

import discord
from discord.ext import commands
from discord import app_commands

key = ''

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

load_dotenv()

DISCORD_API_KEY = os.getenv('DISCORD_API_KEY')
GUILD = discord.Object(id=int(os.getenv('GUILD')))
CAMPER_ROLES = list([int(r) for r in os.getenv('CAMPER_ROLES').split(' ')])
STAR_CAMPER_ROLE = int(os.getenv('STAR_CAMPER_ROLE'))
CABIN_KEY_HOLDERS = list([int(r) for r in os.getenv('CABIN_KEY_HOLDERS').split(' ')])

CABINS_ACTIVE_CATEGORY_NAME = os.getenv('CABINS_ACTIVE_CATEGORY_NAME')
CABINS_DECOMISSIONED_CATEGORY_NAME = os.getenv('CABINS_DECOMISSIONED_CATEGORY_NAME')
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

def cabin_overwrites(guild):
    cabin_overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True)
    }
    for i in CABIN_KEY_HOLDERS:
        cabin_overwrites[i] = interaction.guild.me: discord.PermissionOverwrite(read_messages=True)
    return cabin_overwrites

async def get_or_make_cat(guild, cat_name):
    for c in guild.categories:
        if c.name == cat_name:
            return c
    return await guild.create_category(name=cat_name, overwrites=cabin_overwrites(guild))

async def set_roles(member, cabinate):
    if cabinate:
        await member.edit(roles=[STAR_CAMPER_ROLE])
    else:
        await member.add_roles(member.guild.get_role(CAMPER_ROLES))

async def explode_cabin(guild, cabin):
    await set_roles(guild.get_member(cabin.camper_id), False)
    cursor.execute(f"DELETE FROM cabins WHERE camper='{cabin.camper_id}'")
    connect.commit()
    await guild.get_channel(cabin.channel_id).delete()

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

    async def on_guild_channel_delete(self, channel):
        cursor.execute(f"SELECT * FROM cabins WHERE channel={str(channel.id)}")
        cabin_raw = cursor.fetchone()
        cabin = Cabin(int(cabin_raw[0]), int(cabin_raw[1]), cabin_raw[2], bool(cabin_raw[3])) if cabin_raw else None
        if cabin:
            await set_roles(channel.guild.get_member(cabin.camper_id), False)
            cursor.execute(f"DELETE FROM cabins WHERE camper='{cabin.camper_id}'")
            connect.commit()

bot = Counselor(command_prefix='.', intents=intents)

class ReviveView(discord.ui.View):

    def __init__(self, cabin):
        super().__init__(timeout=30.0)
        self.cabin = cabin

    @discord.ui.button(label='Yes', style=discord.ButtonStyle.blurple)
    async def revive_cabin(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=BOT_COMMAND_EPHEMERALITY)
        member = interaction.guild.get_member(self.cabin.camper_id)
        await bot.get_channel(self.cabin.channel_id).edit(category=cabins_active_category, overwrites=cabin_overwrites(interaction.guild)) | {
            member: discord.PermissionOverwrite(read_messages=True)
        })
        cabin_set_in_use(self.cabin, True)

        await set_roles(member, True)

        await interaction.followup.send('Good to go!', ephemeral=BOT_COMMAND_EPHEMERALITY)
        self.stop()

    @discord.ui.button(label='No', style=discord.ButtonStyle.gray)
    async def ignore_cabin(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message('Gotcha. I\'ll wait for Mosin to clean out the cabin first.', ephemeral=BOT_COMMAND_EPHEMERALITY)
        self.stop()

@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
@bot.tree.command(name='cabin', description='Make a personal cabin for a camper.', guild=GUILD)
async def find_cabin(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=BOT_COMMAND_EPHEMERALITY)

    cabin = get_cabin_by_camper(member.id)

    if cabin and cabin.in_use:
        await interaction.followup.send(f'This camper already has a cabin: <#{cabin.channel_id}>', ephemeral=BOT_COMMAND_EPHEMERALITY)
        return
    elif cabin:
        await interaction.followup.send('It looks like Mosin just finished cleaning this cabin. Should I give it back to the camper?', view=ReviveView(cabin), ephemeral=BOT_COMMAND_EPHEMERALITY)
        return

    await set_roles(member, True)

    global cabins_active_category
    if not cabins_active_category:
        cabins_active_category = await get_or_make_cat(interaction.guild, CABINS_ACTIVE_CATEGORY_NAME)

    cabin_channel = await cabins_active_category.create_text_channel(
        name=f'cabin-{cabin_number_current()}',
        overwrites=cabin_overwrites(interaction.guild) | {
            member: discord.PermissionOverwrite(read_messages=True)
        })
    append_cabin(Cabin(member.id, cabin_channel.id, cabin_number_current(), True))
    cabin_number_current_increment()
    await interaction.followup.send(f'Made a cabin: <#{cabin_channel.id}>', ephemeral=BOT_COMMAND_EPHEMERALITY)

@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
@bot.tree.command(name='dcabin', description='Decomission a camper\'s cabin.', guild=GUILD)
async def decomission_cabin(interaction: discord.Interaction, cabin_no: int):
    await interaction.response.defer(ephemeral=BOT_COMMAND_EPHEMERALITY)

    cabin = get_cabin_by_number(cabin_no)
    if not cabin:
        await interaction.followup.send(f'I couldn\'t find that cabin!', ephemeral=BOT_COMMAND_EPHEMERALITY)
        return
    elif not cabin.in_use:
        await interaction.followup.send(f'<#{cabin.channel_id}> is out of comission!', ephemeral=BOT_COMMAND_EPHEMERALITY)
        return
    
    global cabins_decomissioned_category
    if not cabins_decomissioned_category:
        cabins_decomissioned_category = await get_or_make_cat(interaction.guild, CABINS_DECOMISSIONED_CATEGORY_NAME)

    member = interaction.guild.get_member(cabin.camper_id)
    await set_roles(member, False)
    await bot.get_channel(cabin.channel_id).edit(category=cabins_decomissioned_category, overwrites= cabin_overwrites(interaction.guild) | {
        member: discord.PermissionOverwrite(read_messages=False)
    })
    cabin_set_in_use(cabin, False)
    await interaction.followup.send(f'<#{cabin.channel_id}> is out of comission!', ephemeral=BOT_COMMAND_EPHEMERALITY)

@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
@bot.tree.command(name='ecabin', description='Explode a camper\'s cabin.', guild=GUILD)
async def explode_cabin_command(interaction: discord.Interaction, cabin_no: int):
    await interaction.response.defer(ephemeral=BOT_COMMAND_EPHEMERALITY)

    cabin = get_cabin_by_number(cabin_no)
    if not cabin:
        await interaction.followup.send(f'I couldn\'t find that cabin!', ephemeral=BOT_COMMAND_EPHEMERALITY)
        return

    await explode_cabin(interaction.guild, cabin)
    await interaction.followup.send(f'It has been done.', ephemeral=BOT_COMMAND_EPHEMERALITY)

bot.run(DISCORD_API_KEY)
