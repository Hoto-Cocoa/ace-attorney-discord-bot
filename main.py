import discord
import os
import random
import traceback
import sys
import threading
import time
import yaml
import gc
sys.path.append("./objection_engine")

from deletion import Deletion
from discord.ext import commands, tasks
from message import Message
from objection_engine.beans.comment import Comment
from objection_engine.renderer import render_comment_list
from objection_engine import get_all_music_available
from render import Render, State
from typing import List

# Global Variables:
renderQueue = []
deletionQueue = []
lastRender = 0

intents = discord.Intents.all()
intents.members = True
def loadConfig():
    try:
        with open("config.yaml") as file:
            config = yaml.load(file, Loader=yaml.FullLoader)
            global token, prefix, deletionDelay, max_per_guild, max_per_user, invite_link, cooldown, staff_only

            token = config["token"].strip()
            if not token:
                raise Exception("The 'token' field is missing in the config file (config.yaml)!")

            prefix = config["prefix"].strip()
            if not prefix:
                raise Exception("The 'prefix' field is missing in the config file (config.yaml)!")

            deletionDelay = config["deletionDelay"].strip()
            if not deletionDelay:
                raise Exception("The 'deletionDelay' field is missing in the config file (config.yaml)!")

            max = config["max_tasks"]
            if max is not None:
                max_per_guild = max["per_guild"]
                max_per_user = max["per_user"]
            
            if not max_per_guild:
                max_per_guild = 100
            if not max_per_user:
                max_per_user = 5

            invite_link = config["invite_link"]

            cooldown = config["cooldown"]

            staff_only = config["staff_only"]

            return True
    except KeyError as keyErrorException:
        print(f"The mapping key {keyErrorException} is missing in the config file (config.yaml)!")
    except Exception as exception:
        print(exception)
        return False

if not loadConfig():
    exit()

courtBot = commands.AutoShardedBot(command_prefix=prefix, intents=intents, max_messages=None)
# Default 'help' command is removed, we will make our own
courtBot.remove_command("help")
currentActivityText = f"{prefix}help"

async def changeActivity(newActivityText):
    try:
        global currentActivityText
        if currentActivityText == newActivityText:
            return
        else:
            newActivity = discord.Game(newActivityText)
            await courtBot.change_presence(activity=newActivity)
            currentActivityText = newActivityText
            print(f"Activity was changed to {currentActivityText}")
    except Exception as exception:
        print(f"Error: {exception}")

def addToDeletionQueue(message: discord.Message):
    # Only if deletion delay is grater than 0, add it to the deletionQueue.
    if int(deletionDelay) > 0:
        newDeletion = Deletion(message, int(deletionDelay))
        deletionQueue.append(newDeletion)

@courtBot.event
async def on_message(message):
    if message.author is courtBot.user or message.author.bot:
        return
    if message.channel.type is discord.ChannelType.private:
        embedResponse = discord.Embed(description="I won't process any messages via PM.\nIf you have any problems, please go to [the support server](https://discord.gg/pcS4MPbRDU).", color=0xff0000)
        await message.channel.send(embed=embedResponse)
        return
    await courtBot.process_commands(message)
@courtBot.command()
async def music(context):
    if staff_only:
        if not context.author.guild_permissions.manage_messages:
            errEmbed = discord.Embed(description="Only staff members can use this command!", color=0xff0000)
            errMsg = await context.send(embed=errEmbed)
            addToDeletionQueue(errMsg)
            return

    music_arr = get_all_music_available()
    music_string = '\n- '.join(music_arr)
    await context.reply('The available music is:\n- ' + music_string)

@courtBot.command()
async def invite(context):
    if staff_only:
        if not context.author.guild_permissions.manage_messages:
            errEmbed = discord.Embed(description="Only staff members can use this command!", color=0xff0000)
            errMsg = await context.send(embed=errEmbed)
            addToDeletionQueue(errMsg)
            return

    if invite_link is not None:
        await context.reply(invite_link)

@courtBot.command()
async def help(context):
    if staff_only:
        if not context.author.guild_permissions.manage_messages:
            errEmbed = discord.Embed(description="Only staff members can use this command!", color=0xff0000)
            errMsg = await context.send(embed=errEmbed)
            addToDeletionQueue(errMsg)
            return

    dummyAmount = random.randint(2, 150)
    helpEmbed = discord.Embed(description="Discord bot that turns message chains into ace attorney scenes.\nIf you have any problems, please go to [the support server](https://discord.gg/pcS4MPbRDU).", color=0x3366CC    )
    helpEmbed.add_field(name="How to use?", value=f"`{prefix}render <number_of_messages> <music (optional)>`", inline=False)
    helpEmbed.add_field(name="Example", value=f"Turn the last {dummyAmount} messages into an ace attorney scene: `{prefix}render {dummyAmount}`", inline=False)
    helpEmbed.add_field(name="Example with music", value=f"`{prefix}render {dummyAmount} tat`", inline=False)
    helpEmbed.add_field(name="Know available music", value=f"`{prefix}music`", inline=False)
    helpEmbed.add_field(name="Starting message", value="By default the bot will load the specified number of messages from the last message (before using the command) going backwards, if you want the message count to start from another message, reply to it when using the command.", inline=False)
    await context.send(embed=helpEmbed)

# This command is only for the bot owner, it will ignore everybody else
@courtBot.command()
@commands.is_owner()
async def queue(context):

    filename = "queue.txt"
    with open(filename, 'w', encoding="utf-8") as queue:
        global renderQueue
        renderQueueSize = len(renderQueue)
        queue.write(f"There are {renderQueueSize} item(s) in the queue!\n")
        for positionInQueue, render in enumerate(iterable=renderQueue):
            queue.write(f"\n#{positionInQueue:04}\n")
            try: queue.write(f"Requested by: {render.getContext().author.name}#{render.getContext().author.discriminator}\n")
            except: pass
            try: queue.write(f"Number of messages: {len(render.getMessages())}\n")
            except: pass
            try: queue.write(f"Guild: {render.getFeedbackMessage().channel.guild.name}\n")
            except: pass
            try: queue.write(f"Channel: #{render.getFeedbackMessage().channel.name}\n")
            except: pass
            try: queue.write(f"State: {render.getStateString()}\n")
            except: pass
    await context.send(file=discord.File(filename))
    clean([], filename)

@courtBot.command()
async def render(context: commands.Context, numberOfMessages: int = 0, music: str = 'pwr'):
    if staff_only:
        if not context.author.guild_permissions.manage_messages:
            errEmbed = discord.Embed(description="Only staff members can use this command!", color=0xff0000)
            errMsg = await context.send(embed=errEmbed)
            addToDeletionQueue(errMsg)
            return
            
    global lastRender, cooldown
    if lastRender is not None and cooldown is not None:
        if (time.time() - lastRender) < cooldown:
            errEmbed = discord.Embed(description=f"Please wait **{round(cooldown - (time.time() - lastRender))}** seconds before using this command again.", color=0xff0000)
            errMsg = await context.send(embed=errEmbed)
            addToDeletionQueue(errMsg)
            return

    global renderQueue
    feedbackMessage = await context.send(content="`Checking queue...`")
    petitionsFromSameGuild = [x for x in renderQueue if x.discordContext.guild.id == context.guild.id]
    petitionsFromSameUser = [x for x in renderQueue if x.discordContext.author.id == context.author.id]
    try:
        if (len(petitionsFromSameGuild) > max_per_guild):
            raise Exception(f"Only up to {max_per_guild} renders per guild are allowed")
        if (len(petitionsFromSameUser) > max_per_user):
            raise Exception(f"Only up to {max_per_user} renders per user are allowed")
        await feedbackMessage.edit(content="`Fetching messages...`")
        if numberOfMessages == 0:
            raise Exception("Please specify the number of messages to be rendered!")
        if not (numberOfMessages in range(1, 101)):
            raise Exception("Number of messages must be between 1 and 100")

        # baseMessage is the message from which the specified number of messages will be fetch, not including itself
        baseMessage = context.message.reference.resolved if context.message.reference else context.message
        courtMessages = []
        discordMessages = []

        # If the render command was executed within a reply (baseMessage and context.Message aren't the same), we want
        # to append the message the user replied to (baseMessage) to the 'discordMessages' list and substract 1 from
        # 'numberOfMessages' that way we are taking the added baseMessage into consideration and avoid getting 1 extra message)
        if not baseMessage.id == context.message.id:
            numberOfMessages = numberOfMessages - 1
            discordMessages.append(baseMessage)

        # This will append all messages to the already existing discordMessages, if the message was a reply it should already
        # include one message (the one it was replying to), if not: it will be empty at this point.
        discordMessages += [history async for history in context.channel.history(limit=numberOfMessages, oldest_first=False, before=baseMessage)]
        
        for discordMessage in discordMessages:
            message = Message(discordMessage)
            if message.text.strip():
                courtMessages.insert(0, message.to_Comment())

        if len(courtMessages) < 1:
            raise Exception("There should be at least one person in the conversation.")

        newRender = Render(State.QUEUED, context, feedbackMessage, courtMessages, music)
        renderQueue.append(newRender)

        lastRender = time.time()

    except Exception as exception:
        exceptionEmbed = discord.Embed(description=str(exception), color=0xff0000)
        await feedbackMessage.edit(content="", embed=exceptionEmbed)
        addToDeletionQueue(feedbackMessage)

@tasks.loop(minutes=5)
async def garbageCollection():
    gc.collect()
    print("Garbage collected")

@tasks.loop(seconds=1)
async def deletionQueueLoop():
    global deletionQueue
    deletionQueueSize = len(deletionQueue)
    # Delete message and remove from queue if remaining time is less than (or equal to) 0
    if deletionQueueSize > 0:
        for index in reversed(range(deletionQueueSize)):
            if await deletionQueue[index].update():
                deletionQueue.pop(index)

@tasks.loop(seconds=5)
async def renderQueueLoop():
    global renderQueue
    renderQueueSize = len(renderQueue)
    await changeActivity(f"{prefix}help | queue: {renderQueueSize}")
    for positionInQueue, render in enumerate(iterable=renderQueue, start=1):
        try:
            if render.getState() == State.QUEUED:
                newFeedback = f"""
                `Fetching messages... Done!`
                `Position in the queue: #{(positionInQueue)}`
                """
                await render.updateFeedback(newFeedback)

            if render.getState() == State.INPROGRESS:
                newFeedback = f"""
                `Fetching messages... Done!`
                `Your video is being generated...`
                """
                await render.updateFeedback(newFeedback)

            if render.getState() == State.FAILED:
                newFeedback = f"""
                `Fetching messages... Done!`
                `Your video is being generated... Failed!`
                """
                await render.updateFeedback(newFeedback)
                render.setState(State.DONE)

            if render.getState() == State.RENDERED:
                newFeedback = f"""
                `Fetching messages... Done!`
                `Your video is being generated... Done!`
                `Uploading file to Discord...`
                """
                await render.updateFeedback(newFeedback)

                render.setState(State.UPLOADING)
                await render.getContext().send(content=render.getContext().author.mention, file=discord.File(render.getOutputFilename()))
                render.setState(State.DONE)
                newFeedback = f"""
                `Fetching messages... Done!`
                `Your video is being generated... Done!`
                `Uploading file to Discord... Done!`
                """
                await render.updateFeedback(newFeedback)
        except Exception as exception:
            print(f"Error: {exception}")
            try:
                render.setState(State.DONE)
            except:
                pass
        finally:
            if render.getState() == State.DONE:
                clean(render.getMessages(), render.getOutputFilename())
                addToDeletionQueue(render.getFeedbackMessage())

    # Remove from queue if state is DONE
    if renderQueueSize > 0:
        for index in reversed(range(renderQueueSize)):
            if renderQueue[index].getState() == State.DONE:
                renderQueue.pop(index)

@courtBot.event
async def on_ready():
    global currentActivityText
    print("Bot is ready!")
    print(f"Logged in as {courtBot.user.name}#{courtBot.user.discriminator} ({courtBot.user.id})")
    currentActivityText = f"{prefix}help"
    renderQueueLoop.start()
    deletionQueueLoop.start()

def clean(thread: List[Comment], filename):
    try:
        os.remove(filename)
    except Exception as exception:
        print(f"Error: {exception}")
    try:
        for comment in thread:
            if (comment.evidence_path is not None):
                os.remove(comment.evidence_path)
    except Exception as exception:
        print(f"Error: {exception}")

def renderThread():
    global renderQueue
    while True:
        time.sleep(2)
        try:
            for render in renderQueue:
                if render.getState() == State.QUEUED:
                    render.setState(State.INPROGRESS)
                    try:
                        render_comment_list(render.getMessages(), render.getOutputFilename(), music_code=render.music_code, resolution_scale=2)
                        render.setState(State.RENDERED)
                    except Exception as exception:
                        print(f"Error: {exception}")
                        render.setState(State.FAILED)
                    finally:
                        break
        except Exception as exception:
            print(f"Error: {exception}")

@courtBot.event
async def on_command_error(ctx, error):
        # Source: https://gist.github.com/EvieePy/7822af90858ef65012ea500bcecf1612
        ignored = (commands.CommandNotFound, )

        # Allows us to check for original exceptions raised and sent to CommandInvokeError.
        # If nothing is found. We keep the exception passed to on_command_error.
        error = getattr(error, 'original', error)

        # Anything in ignored will return and prevent anything happening.
        if isinstance(error, ignored):
            return
        
        # All other Errors not returned come here. And we can just print the default TraceBack.
        print('Ignoring exception in command {}:'.format(ctx.command), file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


backgroundThread = threading.Thread(target=renderThread, name="RenderThread")
backgroundThread.start()
# Even while threads in python are not concurrent in CPU, the rendering process may use a lot of disk I/O so having two threads
# May help speed up things
#backgroundThread2 = threading.Thread(target=renderThread, name="RenderThread2")
#backgroundThread2.start()

try:
    courtBot.run(token)
except Exception as e:
    print(str(e))
    os._exit(1)


backgroundThread.join()
#backgroundThread2.join()
