import discord
from discord.ext import commands, tasks
import cloudscraper
import feedparser
import json
from pathlib import Path
from datetime import datetime, timezone
import re
import asyncio
from telethon import TelegramClient
import os
from typing import Dict, List, Optional
import aiohttp

class TelegramRSSBridge(commands.Cog):
    def __init__(self, bot, since_date=None):
        self.bot = bot
        self.mappings_path = "mappings.json"
        self.posted_links_path = "posted_links.json"
        self.pending_posts_path = "pending_posts.json"
        self.keys_path = "keys.json"
        
        # Load keys from keys.json
        try:
            with open(self.keys_path, 'r') as f:
                self.keys = json.load(f)
        except FileNotFoundError:
            print("Error: keys.json not found!")
            self.keys = {}
        
        self.channel_mappings = self.load_mappings()
        self.posted_links = self.load_posted_links()
        self.pending_posts: Dict[str, List[dict]] = self.load_pending_posts()
        self.since_date = since_date  # datetime object or None
        self.scraper = cloudscraper.create_scraper()
        self.color = 0x0088cc  # Telegram's brand color
        self.check_rss.start()
        
        # Initialize Telegram client
        self.tg_client = None
        self.telegram_api_id = self.keys.get("telegram_api_id")
        self.telegram_api_hash = self.keys.get("telegram_api_hash")
        self.telegram_bot_token = self.keys.get("telegram_bot_token")
        self.telegram_phone = None
        
        self.tg_client = TelegramClient('telegram_session', 
                                      self.telegram_api_id,
                                      self.telegram_api_hash)

    async def start_telegram_client(self):
        """Start the Telegram client with appropriate authentication"""
        if not self.tg_client.is_connected():
            await self.tg_client.connect()
            
        if not await self.tg_client.is_user_authorized():
            if self.telegram_bot_token:
                # Use bot token
                await self.tg_client.start(bot_token=self.telegram_bot_token)
            elif self.telegram_phone:
                # Use phone number authentication
                await self.tg_client.start(phone=self.telegram_phone)
            else:
                print("Error: No authentication method provided. Please set either telegram_bot_token or telegram_phone")
                return False
        return True

    def load_mappings(self):
        path = Path(self.mappings_path)
        if not path.exists():
            with path.open("w") as f:
                json.dump({}, f, indent=4)
            return {}
        with path.open("r") as f:
            return json.load(f)

    def load_posted_links(self):
        path = Path(self.posted_links_path)
        if not path.exists():
            return {channel: [] for channel in self.channel_mappings}
        try:
            with path.open("r") as f:
                return json.load(f)
        except:
            return {channel: [] for channel in self.channel_mappings}

    def load_pending_posts(self) -> Dict[str, List[dict]]:
        path = Path(self.pending_posts_path)
        if not path.exists():
            return {channel: [] for channel in self.channel_mappings}
        try:
            with path.open("r") as f:
                return json.load(f)
        except:
            return {channel: [] for channel in self.channel_mappings}

    def save_posted_links(self):
        with open(self.posted_links_path, "w") as f:
            json.dump(self.posted_links, f)

    def save_pending_posts(self):
        with open(self.pending_posts_path, "w") as f:
            json.dump(self.pending_posts, f, indent=4)

    def cog_unload(self):
        if self.tg_client and self.tg_client.is_connected():
            self.tg_client.disconnect()
        self.save_posted_links()
        self.save_pending_posts()
        self.check_rss.cancel()

    def clean_text(self, text):
        # Super simple approach - just join all letters that are separated by single spaces
        words = text.split()
        cleaned_words = []
        current_word = ''
        
        for word in words:
            if len(word) == 1 and word.isalpha():
                current_word += word
            else:
                if current_word:
                    cleaned_words.append(current_word)
                    current_word = ''
                cleaned_words.append(word)
        
        if current_word:
            cleaned_words.append(current_word)
            
        text = ' '.join(cleaned_words)
        
        # Handle hashtag links
        text = re.sub(r'<a href="[^"]+\?q=%23([^"]+)">#[^<]+</a>', r'#\1', text)
        
        # Handle regular links
        text = re.sub(r'<a href="([^"]+)"[^>]*>([^<]+)</a>', lambda m: f'<{m.group(1)}>' if m.group(1) == m.group(2) else f'{m.group(2)} <{m.group(1)}>', text)
        
        # Remove all other HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Fix special characters
        text = text.replace('&amp;', '&')
        
        # Fix spacing around ALL emojis using correct unicode ranges
        emoji_pattern = (
            r'['
            r'\U0001F1E0-\U0001F1FF'  # flags (iOS)
            r'\U0001F300-\U0001F5FF'  # symbols & pictographs
            r'\U0001F600-\U0001F64F'  # emoticons
            r'\U0001F680-\U0001F6FF'  # transport & map symbols
            r'\U0001F700-\U0001F77F'  # alchemical symbols
            r'\U0001F780-\U0001F7FF'  # Geometric Shapes Extended
            r'\U0001F800-\U0001F8FF'  # Supplemental Arrows-C
            r'\U0001F900-\U0001F9FF'  # Supplemental Symbols and Pictographs
            r'\U0001FA00-\U0001FA6F'  # Chess Symbols
            r'\U0001FA70-\U0001FAFF'  # Symbols and Pictographs Extended-A
            r'\U00002702-\U000027B0'  # Dingbats
            r'\U000024C2-\U0001F251' 
            r']'
        )
        text = re.sub(fr'([^\s])({emoji_pattern})', r'\1 \2', text)
        text = re.sub(fr'({emoji_pattern})([^\s])', r'\1 \2', text)
        
        # Fix multiple spaces and newlines
        text = re.sub(r' +', ' ', text)
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        
        # Fix dashes
        text = text.replace('—', '\n—\n')
        
        # Preserve formatting for event listings
        text = re.sub(r'(\d{2}:\d{2} [AP]M)', r'\n\1', text)
        
        return text.strip()

    def is_spaced_text(self, text):
        # Count the ratio of spaces to characters
        chars = len(text.replace(" ", ""))
        spaces = text.count(" ")
        return spaces > chars * 0.5  # If more than 50% of non-space chars have spaces between them

    async def get_file_path(self, file_id: str) -> str:
        """Get the file path from Telegram's API"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.telegram.org/bot{self.telegram_bot_token}/getFile"
                params = {'file_id': file_id}
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('ok'):
                            return data['result']['file_path']
            return None
        except Exception as e:
            print(f"Error getting file path: {str(e)}")
            return None

    async def upload_to_imgbb(self, image_path: str) -> str:
        """Upload an image to imgbb and return the URL"""
        try:
            api_key = self.keys.get("imgbb_api_key")
            if not api_key:
                return None
            
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('key', api_key)
                data.add_field('image', open(image_path, 'rb'))
                
                async with session.post('https://api.imgbb.com/1/upload', data=data) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('success'):
                            image_data = data['data']
                            if image_data.get('image', {}).get('url'):
                                return image_data['image']['url']
                            elif image_data.get('display_url'):
                                return image_data['display_url']
                            elif image_data.get('url'):
                                return image_data['url']
            return None
        except Exception:
            return None

    async def get_media_url(self, channel_name: str, message_id: int) -> str:
        """Get direct media URL from Telegram"""
        if not self.tg_client:
            return None
            
        try:
            if not await self.start_telegram_client():
                return None

            channel_name = channel_name.replace('telegram/channel/', '').replace('channel/', '')
            channel = await self.tg_client.get_entity(channel_name)
            message = await self.tg_client.get_messages(channel, ids=message_id)
            
            if message and message.media:
                try:
                    if hasattr(message.media, 'photo') or hasattr(message.media, 'document'):
                        temp_path = f"temp_{message_id}.jpg"
                        path = await message.download_media(temp_path)
                        if path:
                            url = await self.upload_to_imgbb(path)
                            os.remove(path)
                            return url
                except Exception:
                    if 'path' in locals() and os.path.exists(path):
                        os.remove(path)
            return None
        except Exception:
            return None

    async def format_message(self, entry, channel_name):
        embed = discord.Embed(color=self.color)
        
        channel_name = channel_name.capitalize()
        embed.set_author(
            name=f"Telegram | {channel_name}",
            icon_url="https://telegram.org/img/t_logo.png"
        )

        content = entry.get('description', '')
        
        # Handle forwarded messages
        forward_match = re.search(r'Forwarded From <b><a href="([^"]+)">([^<]+)</a></b> \(([^)]+)\)', content)
        if forward_match:
            forward_link, forward_channel, forward_author = forward_match.groups()
            embed.set_footer(
                text=f"Forwarded from {forward_author}",
                icon_url="https://telegram.org/img/t_logo.png"
            )

        # Remove forwarding header and clean content
        clean_content = re.sub(r'Forwarded From.*?\)', '', content)
        if self.is_spaced_text(clean_content):
            clean_content = ''.join(clean_content.split())
        clean_content = self.clean_text(clean_content)
        if clean_content:
            embed.description = clean_content

        # Handle images
        img_urls = []
        img_matches = re.finditer(r'<img[^>]+src="([^"]+)"[^>]*>', content)
        content_modified = content
        
        for match in img_matches:
            url = match.group(1)
            original_url = url
            processed = False
            
            if 'undefined://' in url or 'undefined:' in url:
                try:
                    parts = url.split('/')
                    msg_id_match = re.search(r'_(\d+)$', parts[-1])
                    
                    if not msg_id_match:
                        continue
                        
                    msg_id = int(msg_id_match.group(1))
                    
                    channel = None
                    if 'channel' in parts:
                        channel_index = parts.index('channel')
                        channel_part = '/'.join([p for i, p in enumerate(parts) if i > channel_index])
                        channel_match = re.match(r'([^0-9]+)', channel_part)
                        if channel_match:
                            channel = channel_match.group(1).rstrip('_')
                    
                    if not channel:
                        continue
                    
                    direct_url = await self.get_media_url(channel, msg_id)
                    if direct_url:
                        url = direct_url
                        content_modified = content_modified.replace(original_url, url)
                        processed = True
                        
                except Exception as e:
                    print(f"Error processing undefined URL: {str(e)}")
            
            if url.startswith(('http://', 'https://')) and ' ' not in url and '\n' not in url:
                img_urls.append(url)

        content = content_modified

        if img_urls:
            try:
                url = img_urls[0]
                embed.set_image(url=url)
            except Exception as e:
                print(f"Error setting image URL: {str(e)}")
            
            if len(img_urls) > 1:
                additional_images = len(img_urls) - 1
                if embed.description:
                    embed.description += f"\n\n*+{additional_images} more image{'s' if additional_images > 1 else ''}*"
                else:
                    embed.description = f"*+{additional_images} more image{'s' if additional_images > 1 else ''}*"

        # Set timestamp
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            post_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            embed.timestamp = post_date

        return embed

    @tasks.loop(minutes=5)
    async def check_rss(self):
        for channel_name, discord_channel_id in self.channel_mappings.items():
            try:
                if channel_name not in self.posted_links:
                    self.posted_links[channel_name] = []

                rss_url = f"https://rss.tabithahanegan.com/telegram/channel/{channel_name}"
                resp = self.scraper.get(rss_url, timeout=20)
                feed = feedparser.parse(resp.content)
                
                channel = self.bot.get_channel(int(discord_channel_id))
                if not channel:
                    continue

                # Get the latest post's date from our posted links
                latest_post_date = None
                for entry in feed.entries:
                    if entry.link in self.posted_links[channel_name]:
                        if hasattr(entry, 'published_parsed') and entry.published_parsed:
                            post_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                            if latest_post_date is None or post_date > latest_post_date:
                                latest_post_date = post_date

                # Process all posts that we haven't seen before
                new_entries = []
                for entry in feed.entries:
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        post_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                        if entry.link not in self.posted_links[channel_name]:
                            new_entries.append((post_date, entry))

                # Sort new entries by date
                new_entries.sort(key=lambda x: x[0])

                # Process new entries
                for post_date, entry in new_entries:
                    try:
                        embed = await self.format_message(entry, channel_name)
                        message = await channel.send(embed=embed)
                        
                        # If this is an announcement channel, publish the message
                        if isinstance(channel, discord.TextChannel) and channel.is_news():
                            # Check permissions first
                            permissions = channel.permissions_for(channel.guild.me)
                            if not permissions.manage_messages:
                                print(f"Bot lacks manage_messages permission in channel {channel.name}")
                                continue
                                
                            try:
                                await message.publish()
                                print(f"Successfully published message in announcement channel {channel.name}")
                            except discord.Forbidden:
                                print(f"Missing permissions to publish in announcement channel {channel.name}")
                            except discord.HTTPException as e:
                                print(f"HTTP error when publishing in announcement channel {channel.name}: {str(e)}")
                            except Exception as e:
                                print(f"Unexpected error when publishing in announcement channel {channel.name}: {str(e)}")
                                
                        self.posted_links[channel_name].append(entry.link)
                        self.save_posted_links()
                        await asyncio.sleep(1)
                    except Exception as e:
                        print(f"Error processing entry: {str(e)}")
                        continue

            except Exception:
                continue

    @check_rss.before_loop
    async def before_check_rss(self):
        await self.bot.wait_until_ready()

    @commands.group(name="telegram")
    @commands.has_permissions(manage_messages=True)
    async def telegram_group(self, ctx):
        """Commands for managing Telegram bridge posts"""
        if ctx.invoked_subcommand is None:
            await ctx.send("Please specify a subcommand. Use `help telegram` for more information.")
    @telegram_group.command(name="pending")
    async def list_pending(self, ctx, channel_name: Optional[str] = None):
        """List pending posts for a channel or all channels"""
        if channel_name and channel_name not in self.pending_posts:
            await ctx.send(f"No pending posts found for channel {channel_name}")
            return

        channels_to_check = [channel_name] if channel_name else self.pending_posts.keys()
        
        for chan in channels_to_check:
            if not self.pending_posts[chan]:
                continue
                
            embed = discord.Embed(
                title=f"Pending Posts for {chan}",
                color=self.color
            )
            
            for i, post in enumerate(self.pending_posts[chan]):
                post_date = datetime.fromisoformat(post["post_date"]).strftime("%Y-%m-%d %H:%M UTC")
                embed.add_field(
                    name=f"Post #{i+1}",
                    value=f"Posted at: {post_date}\nLink: {post['link']}",
                    inline=False
                )
            
            await ctx.send(embed=embed)

    @telegram_group.command(name="publish")
    async def publish_posts(self, ctx, channel_name: str, count: int = 1):
        """Publish specified number of pending posts for a channel"""
        if channel_name not in self.pending_posts:
            await ctx.send(f"No pending posts found for channel {channel_name}")
            return

        if not self.pending_posts[channel_name]:
            await ctx.send(f"No pending posts available for {channel_name}")
            return

        posts_to_publish = self.pending_posts[channel_name][:count]
        self.pending_posts[channel_name] = self.pending_posts[channel_name][count:]
        
        for post in posts_to_publish:
            channel = self.bot.get_channel(int(post["channel_id"]))
            if channel:
                try:
                    embed = discord.Embed.from_dict(post["embed_dict"])
                    await channel.send(embed=embed)
                    self.posted_links[channel_name].append(post["link"])
                    await asyncio.sleep(1)
                except Exception:
                    continue

        self.save_pending_posts()
        self.save_posted_links()
        await ctx.send(f"Published {len(posts_to_publish)} posts for {channel_name}")

    @telegram_group.command(name="clear")
    async def clear_pending(self, ctx, channel_name: str):
        """Clear all pending posts for a channel"""
        if channel_name not in self.pending_posts:
            await ctx.send(f"No pending posts found for channel {channel_name}")
            return

        post_count = len(self.pending_posts[channel_name])
        self.pending_posts[channel_name] = []
        self.save_pending_posts()
        await ctx.send(f"Cleared {post_count} pending posts for {channel_name}")
