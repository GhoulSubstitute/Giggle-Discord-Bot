import datetime
import random
import pandas
import discord
from discord.ext import commands
import yt_dlp
import asyncio
import imageio_ffmpeg as ffmpeg
import os

TOKEN = os.getenv("TOKEN")

ffmpeg_path = ffmpeg.get_ffmpeg_exe()
intents = discord.Intents.default()
intents.message_content = True
giggle = commands.Bot(command_prefix="!", intents=intents)

# ---------- QUEUE SYSTEM ----------
queues = {}  # {guild_id: [song_dicts...]}

# YTDL setup
ytdl_format_options = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0"
}
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

ffmpeg_options = {
    "before_options": (
        "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
        "-headers \"User-Agent:Mozilla/5.0\""
    ),
    "options": "-vn"
}


async def search_yt(query):
    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
    if "entries" in info:
        info = info["entries"][0]
    return {"url": info["url"], "title": info["title"]}


async def play_next(ctx):
    guild_id = ctx.guild.id
    if queues.get(guild_id):
        song = queues[guild_id].pop(0)

        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: ytdl.extract_info(song["title"], download=False))
        if "entries" in info:
            info = info["entries"][0]
        url = info["url"]

        ctx.voice_client.play(
            discord.FFmpegPCMAudio(url, executable  =ffmpeg_path, **ffmpeg_options),
            after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), asyncio.get_running_loop())
        )
        await ctx.send(f"🎶 Now playing: **{song['title']}**")


# ---------- FUN COMMANDS ----------
@giggle.command("hello")
async def hello(ctx):
    await ctx.send(f"Hello {ctx.author.mention}")


@giggle.command("joke")
async def joke(ctx):
    await ctx.send(random.choice(pandas.read_csv("jokes.csv")["Joke"]))


# ---------- RPS GAME ----------
@giggle.command(name="rps")
async def rps(ctx):
    await ctx.send(f"{ctx.author.mention}, game begins! Type rock, paper, or scissors in this channel.")
    bot_score = 0
    user_score = 0
    while bot_score < 3 and user_score < 3:
        try:
            msg = await giggle.wait_for("message", timeout=20.0,
                                        check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
        except:
            await ctx.send(f"{ctx.author.mention}, game ended due to inactivity.")
            return

        player_choice = msg.content.lower()
        choices = ["rock", "paper", "scissors"]
        if player_choice not in choices:
            await ctx.send(f"{ctx.author.mention}, invalid choice. Please type rock, paper, or scissors.")
            continue

        bot_choice = random.choice(choices)
        await ctx.send(f"I chose {bot_choice}.")
        if player_choice == "rock" and bot_choice == "scissors":
            user_score += 1
        if player_choice == "rock" and bot_choice == "paper":
            bot_score += 1
        if player_choice == "paper" and bot_choice == "rock":
            user_score += 1
        if player_choice == "paper" and bot_choice == "scissors":
            bot_score += 1
        if player_choice == "scissors" and bot_choice == "paper":
            user_score += 1
        if player_choice == "scissors" and bot_choice == "rock":
            bot_score += 1
        if player_choice == bot_choice:
            await ctx.send("It's a tie!")
        await ctx.send(f"{ctx.author.mention}: {user_score} | Giggle: {bot_score}")

    if user_score == 3:
        await ctx.send(f"{ctx.author.mention} won the game!")
    else:
        await ctx.send("I won the game!")


# ---------- BLACKJACK ----------
def deal_card():
    cards = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11]
    return random.choice(cards)


def calculate_score(hand):
    score = sum(hand)
    if score > 21 and 11 in hand:
        hand[hand.index(11)] = 1
        score = sum(hand)
    return score


@giggle.command("blackjack")
async def blackjack(ctx):
    user = ctx.author
    user_hand = [deal_card(), deal_card()]
    dealer_hand = [deal_card(), deal_card()]
    user_score = calculate_score(user_hand)
    dealer_score = calculate_score(dealer_hand)

    await ctx.send(
        f"{user.mention}, your cards: {user_hand}, current score: {user_score}\nDealer's first card: {dealer_hand[0]}")

    game_over = False
    while not game_over:
        if user_score == 21 or dealer_score == 21 or user_score > 21:
            game_over = True
            break

        await ctx.send("Type 'hit' to draw another card or 'stand' to pass:")
        try:
            msg = await giggle.wait_for("message",
                                        check=lambda
                                        m: m.author == user and m.channel == ctx.channel and m.content.lower() in [
                                            "hit", "stand"],
                                        timeout=30)
        except:
            await ctx.send("Game timed out.")
            return

        if msg.content.lower() == "hit":
            user_hand.append(deal_card())
            user_score = calculate_score(user_hand)
            await ctx.send(f"Your cards: {user_hand}, current score: {user_score}")
        else:
            game_over = True

    while dealer_score < 17 and dealer_score != 21:
        dealer_hand.append(deal_card())
        dealer_score = calculate_score(dealer_hand)

    await ctx.send(
        f"Your final hand: {user_hand}, final score: {user_score}\nDealer's final hand: {dealer_hand}, final score: {dealer_score}")

    if user_score > 21:
        await ctx.send("You went over. Dealer wins.")
    elif dealer_score > 21:
        await ctx.send("Dealer went over. You win.")
    elif user_score == dealer_score:
        await ctx.send("It's a draw.")
    elif user_score > dealer_score:
        await ctx.send("You win.")
    else:
        await ctx.send("Dealer wins.")


# ---------- MUSIC COMMANDS ----------
@giggle.command("play")
async def play(ctx, *, query: str):
    if not ctx.author.voice:
        await ctx.send("You must be in a voice channel to play music.")
        return

    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()

    song = await search_yt(query)
    guild_id = ctx.guild.id

    if guild_id not in queues:
        queues[guild_id] = []

    queues[guild_id].append(song)

    if not ctx.voice_client.is_playing():
        await play_next(ctx)
    else:
        await ctx.send(f"✅ Added to queue: **{song['title']}**")


@giggle.command("skip")
async def skip(ctx):
    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭ Skipped.")


@giggle.command("queue")
async def queue(ctx):
    guild_id = ctx.guild.id
    if guild_id not in queues or not queues[guild_id]:
        await ctx.send("🎵 Queue is empty.")
    else:
        qlist = "\n".join([f"{i + 1}. {song['title']}" for i, song in enumerate(queues[guild_id])])
        await ctx.send(f"🎶 Current queue:\n{qlist}")


@giggle.command("pause")
async def pause(ctx):
    if ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("Paused.")


@giggle.command("resume")
async def resume(ctx):
    if ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Resumed.")


@giggle.command("stop")
async def stop(ctx):
    queues[ctx.guild.id] = []
    ctx.voice_client.stop()
    await ctx.send("Stopped playback and cleared queue.")


@giggle.command("leave")
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Left the voice channel.")

# Kick member


@giggle.command("kick")
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, reason=None):
    await member.kick(reason=reason)
    await ctx.send(f"{member.mention} has been kicked. Reason: {reason}")


# Ban member

@giggle.command("ban")
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, reason=None):
    await member.ban(reason=reason)
    await ctx.send(f"{member.mention} has been banned. Reason: {reason}")

# Timeout a member


@giggle.command("timeout")
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int, reason=None):
    duration = datetime.timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    await ctx.send(f"{member.mention} has been timed out until {minutes} minutes. Reason: {reason}")

print("TOKEN from env:", repr(TOKEN))

giggle.run(TOKEN)

