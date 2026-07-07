import os
import argparse
import asyncio

from dataclasses import dataclass

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

cabin_number_current = 1

cabins = []
decomissioned_cabins = []

async def get_or_make_cat(guild, cat_name):
    for c in guild.categories:
        if c.name == cat_name:
            return c
    return await guild.create_category(name=cat_name, overwrites={
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True),
    })
            
    global cabin_number_current

class Counselor(commands.Bot):
    async def on_ready(self):
        print(f'Logged in as {self.user}')

        try:
            synced = await self.tree.sync(guild=GUILD)
            print(f'Synced {len(synced)} commands to {GUILD.id}')
        except Exception as e:
            print(e)

    async def on_member_remove(self, member):
        cabin = None
        for c in cabins:
            if c.camper_id == member.id:
                cabin = c
                break
        if not cabin:
            for c in decomissioned_cabins:
                if c.camper_id == member.id:
                    cabin = c
                    break
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
        decomissioned_cabins.remove(self.cabin)
        cabins.append(self.cabin)
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
    for cabin in cabins:
        if cabin.camper_id == member.id:
            await interaction.response.send_message(f'This camper already has a cabin: <#{cabin.channel_id}>', ephemeral=BOT_COMMAND_EPHEMERALITY)
            return

    global cabins_active_category
    if not cabins_active_category:
        cabins_active_category = await get_or_make_cat(interaction.guild, CABINS_ACTIVE_CATEGORY_NAME)

    for cabin in decomissioned_cabins:
        if cabin.camper_id == member.id:
            await interaction.response.send_message('It looks like Mosin just finished cleaning this cabin. Should I give it back to the camper?', view=ReviveView(cabin), ephemeral=BOT_COMMAND_EPHEMERALITY)
            return

    global cabin_number_current
    cabin = await cabins_active_category.create_text_channel(
        name=f'cabin-{cabin_number_current}',
        overwrites={
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True),
            member: discord.PermissionOverwrite(read_messages=True)
        })
    cabins.append(Cabin(member.id, cabin.id, cabin_number_current))
    cabin_number_current += 1
    await interaction.response.send_message(f'Made a cabin: <#{cabin.id}>', ephemeral=BOT_COMMAND_EPHEMERALITY)

@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
@bot.tree.command(name='dcabin', description='Decomission a camper\'s cabin.', guild=GUILD)
async def decomission_cabin(interaction: discord.Interaction, cabin_no: int):
    cabin = None
    for c in cabins:
        if c.cabin_number == cabin_no:
            cabin = c
            break
    if not cabin:
        await interaction.response.send_message(f'I couldn\'t find that cabin!', ephemeral=BOT_COMMAND_EPHEMERALITY)
        return
    
    global cabins_decomissioned_category
    if not cabins_decomissioned_category:
        cabins_decomissioned_category = await get_or_make_cat(interaction.guild, CABINS_DECOMISSIONED_CATEGORY_NAME)

    await bot.get_channel(cabin.channel_id).edit(category=cabins_decomissioned_category, overwrites={
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.guild.me: discord.PermissionOverwrite(read_messages=True),
        interaction.guild.get_member(cabin.camper_id): discord.PermissionOverwrite(read_messages=False)
    })
    cabins.remove(cabin)
    decomissioned_cabins.append(cabin)
    await interaction.response.send_message(f'<#{cabin.channel_id}> is out of comission!', ephemeral=BOT_COMMAND_EPHEMERALITY)

async def explode_cabin(guild, cabin):
    await guild.get_channel(cabin.channel_id).delete()

@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
@bot.tree.command(name='ecabin', description='Explode a camper\'s cabin.', guild=GUILD)
async def explode_cabin_command(interaction: discord.Interaction, cabin_no: int):
    cabin = None
    for c in cabins:
        if c.cabin_number == cabin_no:
            cabin = c
            break
    if not cabin:
        for c in decomissioned_cabins:
            if c.cabin_number == cabin_no:
                cabin = c
                break
    if not cabin:
        await interaction.response.send_message(f'I couldn\'t find that cabin!', ephemeral=BOT_COMMAND_EPHEMERALITY)
        return

    await explode_cabin(interaction.guild, cabin)
    await interaction.response.send_message(f'It has been done.', ephemeral=BOT_COMMAND_EPHEMERALITY)

bot.run(key)
