import requests
import json
import random
import discord
from discord.ext import commands
from bs4 import BeautifulSoup
import re
import datetime
import logger
import database as db
import asyncio
import psutil
import math
import time
import os
from lxml import html

database = db.Database()


class Scraper:

    def __init__(self, client):
        self.client = client
        self.logger = logger.create_logger(__name__)
        self.start_time = time.time()
        with open('useragents.txt', 'r') as f:
            self.useragents = [x.rstrip() for x in f.readlines()]

    async def on_ready(self):
        await self.refresh_loop()

    async def refresh_loop(self):
        while True:
            try:
                await self.scrape_all_accounts()
                sleep_for = 3600-datetime.datetime.now().minute*60-datetime.datetime.now().second+60
                print("sleeping for", sleep_for)
                await asyncio.sleep(sleep_for)
            except Exception as e:
                self.logger.error(f"Ignored exception in refresh loop:\n{e}")
                continue

    def get_headers(self):
        headers = {"Accept": "*/*",
                   "Host": "www.instagram.com",
                   "Accept-Encoding": "gzip, deflate, br",
                   "Accept-Language": "en,en-US;q=0.5",
                   "Connection": "keep-alive",
                   "DNT": "1",
                   "Upgrade-Insecure-Requests": "1",
                   "Cookie": 'mid=XD0GAwAEAAGABtHtkoc67OJpMGj0; ig_cb=1; mcd=3; fbm_124024574287414=base_domain='
                             '.instagram.com; shbid=6442; shbts=1549295359.7539752; '
                             'csrftoken=5HnQKbzyssnbspn9tpnBVCABIPgHM4yJ; '
                             'ds_user_id=5951951432; sessionid=5951951432%3AwdFliKT8fr2DbI%3A11; rur=ATN; '
                             'urlgen="{\"88.193.149.245\": 1759}:1griMi:es31bLlcL8_CmsTYooTAZIsB6jA"',
                   "User-Agent": random.choice(self.useragents)}
        return headers

    def get_user_posts(self, username):
        url = f"https://www.instagram.com/{username}/?__a=1"
        response = requests.get(url, headers=self.get_headers())
        data = json.loads(response.content.decode('utf-8'))
        return data

    async def send_video(self, channel, shortcode, params):
        url = f"https://www.instagram.com/p/{shortcode}"
        response = requests.get(url, headers=self.get_headers())
        tree = html.fromstring(response.content)
        results = tree.xpath('//meta[@content]')
        sources = []
        for result in results:
            try:
                if result.attrib['property'] == "og:video":
                    sources.append(result.attrib['content'])
            except KeyError:
                pass
        if sources:
            await channel.send(sources[0])

    async def send_post(self, channel, shortcode, params):
        url = f"https://www.instagram.com/p/{shortcode}"
        response = requests.get(url, headers=self.get_headers())
        soup = BeautifulSoup(response.text, 'html.parser')
        script = soup.find_all('script')
        sources = []
        for i in range(len(script)):
            urls = re.findall('"display_url":"(.*?)"', script[i].text)
            if urls:
                sources = urls
        sources = list(set(sources))

        if sources:
            content = discord.Embed(color=discord.Color.magenta())
            content.description = params.get('title')
            content.set_author(name='@' + params.get('user'), url=url, icon_url=params.get('avatar_url'))
            content.timestamp = datetime.datetime.utcfromtimestamp(params.get('timestamp'))
            for url in sources:
                content.set_image(url=url)
                await channel.send(embed=content)
                content.description = None
        else:
            print(f"Error sending post {shortcode}")
            # await ctx.send("Found nothing, sorry!")

    async def get_posts(self, username, howmany=1, channel=None):
        data = self.get_user_posts(username)
        avatar = data['graphql']['user']['profile_pic_url']
        posts = []
        for x in data['graphql']['user']['edge_owner_to_timeline_media']['edges']:
            posts.append(x)
        for i in range(howmany):
            timestamp = posts[i]['node']['taken_at_timestamp']
            if channel is None and timestamp < database.get_attr("accounts", [username, "last_scrape"], 0):
                self.logger.info(f"{username} : no more new posts")
                return
            try:
                title = posts[i]['node']['edge_media_to_caption']['edges'][0]['node']['text']
            except IndexError:
                title = None
            shortcode = posts[i]['node']['shortcode']
            user = posts[i]['node']['owner']['username']
            data = {"title": title, "user": user, "avatar_url": avatar, "timestamp": timestamp}
            if channel is None:
                database.set_attr("accounts", [username, "last_scrape"], datetime.datetime.now().timestamp())
                for channel_id in database.get_attr("accounts", [username, "channels"]):
                    await self.send_post(self.client.get_channel(channel_id), shortcode, data)
                    self.logger.info(logger.post_log(self.client.get_channel(channel_id), username))
            else:
                await self.send_post(channel, shortcode, data)

    async def scrape_all_accounts(self):
        for username in database.get_attr("accounts", []):
            await self.get_posts(username, 6)

    @commands.command()
    async def get(self, ctx, username, howmany=1):
        self.logger.info(logger.command_log(ctx))
        await self.get_posts(username, howmany, ctx.channel)

    @commands.command()
    async def add(self, ctx, channelmention, username):
        self.logger.info(logger.command_log(ctx))
        channel = channel_from_mention(ctx.guild, channelmention)
        if channel is None:
            await ctx.send("Invalid channel")
            return

        database.append_attr("accounts", [username, "channels"], channel.id)
        if database.get_attr("accounts", [username, "last_scrape"]) is None:
            database.set_attr("accounts", [username, "last_scrape"], datetime.datetime.now().timestamp())
        await ctx.send(f"New posts by `{username}` will now be posted to {channel.mention}\n"
                       f"https://www.instagram.com/{username}")
        # await self.get_posts(username, 1, channel)

    @commands.command()
    async def remove(self, ctx, channelmention, username):
        self.logger.info(logger.command_log(ctx))
        channel = channel_from_mention(ctx.guild, channelmention)
        if channel is None:
            await ctx.send("Invalid channel")
            return

        database.delete_key("accounts", [username])
        await ctx.send(f"`{username}` removed from {channel.mention}")

    @commands.command(aliases=["info"])
    async def status(self, ctx):
        up_time = time.time() - self.start_time
        m, s = divmod(up_time, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)
        uptime_string = "%d days %d hours %d minutes %d seconds" % (d, h, m, s)

        stime = time.time() - psutil.boot_time()
        m, s = divmod(stime, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)
        system_uptime_string = "%d days %d hours %d minutes %d seconds" % (d, h, m, s)

        mem = psutil.virtual_memory()

        pid = os.getpid()
        memory_use = psutil.Process(pid).memory_info()[0]

        content = discord.Embed(title=f"Instagram Tracker | version 1.1")
        content.set_thumbnail(url=self.client.user.avatar_url)

        content.add_field(name="Bot process uptime", value=uptime_string)
        content.add_field(name="System CPU Usage", value=f"{psutil.cpu_percent()}%")
        content.add_field(name="System uptime", value=system_uptime_string)

        content.add_field(name="System RAM Usage", value=f"{mem.percent}%")
        content.add_field(name="Bot memory usage", value=f"{memory_use / math.pow(1024, 2):.2f}MB")

        await ctx.send(embed=content)

    @commands.command()
    async def list(self, ctx, mention=None):
        self.logger.info(logger.command_log(ctx))
        channel_limit = None
        if mention is not None:
            channel_limit = channel_from_mention(ctx.guild, mention)
            if channel_limit is None:
                await ctx.send(f"Invalid channel `{mention}`")
                return

        pages = []
        rows = []
        for username in database.get_attr("accounts", []):
            channel_mentions = []
            for channel_id in database.get_attr("accounts", [username, "channels"]):
                channel = ctx.guild.get_channel(channel_id)
                if channel is not None:
                    if channel_limit is not None and not channel == channel_limit:
                        continue
                    channel_mentions.append(channel.mention)

            if channel_mentions:
                if channel_limit is not None:
                    rows.append(f"**{username}**")
                else:
                    rows.append(f"**{username}** >> {'|'.join(channel_mentions)}")
            if len(rows) == 25:
                pages.append("\n".join(rows))
                rows = []

        if rows:
            pages.append("\n".join(rows))

        if not pages:
            await ctx.send("I am not following any users on this server yet!")
            return

        content = discord.Embed()
        if channel_limit is not None:
            content.title = f"Followed users in **{channel_limit.name}** channel:"
        else:
            content.title = f"Followed users in **{ctx.guild.name}**:"

        content.set_footer(text=f"page 1 of {len(pages)}")
        content.description = pages[0]
        msg = await ctx.send(embed=content)

        if len(pages) > 1:
            await page_switcher(self.client, msg, content, pages)

    @commands.command()
    @commands.is_owner()
    async def force_refresh(self, ctx):
        self.logger.info(logger.command_log(ctx))
        await self.scrape_all_accounts()


def setup(client):
    client.add_cog(Scraper(client))


def channel_from_mention(guild, text, default=None):
    text = text.strip("<>#!@")
    try:
        channel = guild.get_channel(int(text))
        if channel is None:
            return default
        return channel
    except ValueError:
        return default


async def page_switcher(client, my_msg, content, pages):
    current_page = 0

    def check(_reaction, _user):
        return _reaction.message.id == my_msg.id and _reaction.emoji in ["⬅", "➡"] \
               and not _user == client.user

    await my_msg.add_reaction("⬅")
    await my_msg.add_reaction("➡")

    while True:
        try:
            reaction, user = await client.wait_for('reaction_add', timeout=3600.0, check=check)
        except asyncio.TimeoutError:
            return
        else:
            try:
                if reaction.emoji == "⬅" and current_page > 0:
                    content.description = pages[current_page - 1]
                    current_page -= 1
                    await my_msg.remove_reaction("⬅", user)
                elif reaction.emoji == "➡":
                    content.description = pages[current_page + 1]
                    current_page += 1
                    await my_msg.remove_reaction("➡", user)
                else:
                    continue
                content.set_footer(text=f"page {current_page + 1} of {len(pages)}")
                await my_msg.edit(embed=content)
            except IndexError:
                continue
