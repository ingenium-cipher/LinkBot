import discord
from discord.ext import commands
import pymongo
from datetime import datetime
import schedule
import validators
import json
import os
import re
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
is_prod = os.environ['IS_HEROKU']

MONGO_URL = os.environ['MONGO_URL']
if is_prod == 'True':
    BOT_TOKEN = os.environ['BOT_TOKEN']
    bot = commands.Bot(command_prefix = '$')
else:
    BOT_TOKEN = os.environ['TEST_TOKEN']
    bot = commands.Bot(command_prefix = '~')

myclient = pymongo.MongoClient(MONGO_URL)
db = myclient["linkbot"]

collist = db.list_collection_names()
collections = ["schedules", "users", "courses"]

for collect in collections:
    if collect not in collist:
        db.create_collection(collect)

schedules = db["schedules"]
users = db["users"]
courses = db["courses"]

class Schedule():



    def __init__(self, subject, section, day, time, link):
        if validators.url(link):
            course = courses.find_one_and_update({"name": subject}, {"$set": {"name": subject}}, upsert= True, return_document = pymongo.ReturnDocument.AFTER)
            sched = schedules.find_one({"course": course['_id'], "section": section})
            if sched is None:
                schedules.insert_one({"course": course['_id'], "day": day.upper(), "time": time, "section": section, "link": [link]})
            else:
                raise Exception("Already registered! Use add_link to add a link to the record.")
        else:
            raise Exception("Invalid URL format.")

    #should be used when atleast two args are present    
    @staticmethod
    def argParser(*args):
        if (len(args) > 5):
            raise Exception("Too many arguments")
        keys = [1, 2, 3, 4, 5]
        argDict = {key: None for key in keys}
        for i in range(len(args)):
            argDict[Schedule.ParseHelper(args[i])] = args[i]            
        return tuple([argDict[i] for i in keys if argDict[i] is not None])
            
        
    @staticmethod
    def ParseHelper(arg):
        if validators.url(arg): #link
            return 5
        if arg.isdigit(): #time
            return 4
        if re.match(r'[mtw(th)fsMTW(TH)FS(Th)]+$', arg): #day
            return 3                                                           
        if re.match(r'[TtPpLl]\d+$', arg): #section
            return 2
        if re.match(r'[a-zA-Z0-9-]+$', arg):  #course
            return 1
        raise Exception("Unexpected arguments!")

    @staticmethod
    def get_course(name):
        return courses.find_one({"name": name})

    @staticmethod
    def get_schedule(name, section='N/A'):
        if section == 'N/A':
            return schedules.find({"course": Schedule.get_course(name)['_id']})
        return schedules.find_one({"course": Schedule.get_course(name)['_id'], "section": section})   
    #adds meet link corresponding to a course
    @staticmethod
    def add_link(*args):
        if validators.url(args[2]):
            course = courses.find_one_and_update({"name": args[0]}, {"$set": {"name": args[0]}}, upsert= True, return_document = pymongo.ReturnDocument.AFTER)
            sched = schedules.find_one({"course": course['_id'], "section": args[1]})
            # adds the incoming link if the link is not already present
            if args[2] in sched['link']:
                return 2
            else:
                schedules.update_one({"course": course['_id'], "section": args[1]}, {"$push": {"link": args[2]}})
                return 1
        return 0

    #retrieves link(s) of a subject from the db
    @staticmethod
    def get_link(name, section='N/A'):            
        sched = Schedule.get_schedule(name, section)
        if isinstance(sched, pymongo.cursor.Cursor):
            links = []
            for doc in sched:
                links.extend(doc['link'])
            return links
        else:
            return sched['link']
    
    @staticmethod
    def deregister(*args):
        if len(args) == 2:
            status = schedules.delete_many({"course": Schedule.get_course(args[0])['_id'], "section":args[1]})
            if schedules.find_one({"course": Schedule.get_course(args[0])['_id']}) is None:
                courses.delete_one({"name": args[0]})
        elif len(args) == 1:
            status = schedules.delete_many({"course":  Schedule.get_course(args[0])['_id']})
            courses.delete_one({"name": args[0]})
        else:
            return -1
        return status.deleted_count

    @staticmethod
    def remove_link(*args):
        sched = Schedule.get_schedule(args[0], args[1])
        if args[2] in sched['link']:
            sched['link'].remove(args[2])
            schedules.update_one(sched, {"$set": {"link": sched['link']}})  #Probably wrong. Link is being set to old link and not deleted. @ingenium-cipher fix this. 
            return 1
        return 0
    

    @staticmethod
    async def remove_all():
        courses.drop()
        schedules.drop()

@bot.event
async def on_ready():
    print(f'Bot Ready')
  

@bot.command(brief='The name says it all')
async def ping(ctx):
    await ctx.send(f'I am just {round(bot.latency * 1000)}ms away from you :cupid:.')

# Registers the course in the database
@bot.command(aliases=['register', 'add'], brief='Add a course to the DB')
async def register_course(ctx, *args):
    if len(args) != 5:
        await ctx.send('Usage: Course, day, time, section, link')
    else:
        try:
            Schedule(args[0], args[1], args[2], args[3], args[4])
            await ctx.message.add_reaction('\U0001F44C')
        except Exception as e:
            await ctx.send(f'{e}')

@bot.command(brief='Deregisters all sections of a course if no section is given, otherwise deregisters the given section.')
async def deregister(ctx, *args):
    status = Schedule.deregister(*args)
    if status > 0:
        await ctx.message.add_reaction('\U0001F44C')
    elif status == 0:
        await ctx.send("Course does not exist.")
    else:
        await ctx.send("C'mon, that's not even valid syntax")

@bot.command(aliases = ['add_link'], brief='Adds link to a course. Usage: <Course> <Section>')
async def addlink(ctx, *args):
    status = Schedule.add_link(*args)
    if status == 1:
        await ctx.message.add_reaction('\U0001F44C')
    elif status == 2:
        await ctx.send(f'Link already exists!')
    elif status == 0:
        await ctx.send('Invalid URL Format.')

@bot.command(brief='Retrieves link(s) of a course', description='Usage: $getlink [Course Name] [Section]=optional.\n Sends links of all sections of a course if section is omitted.')
async def getlink(ctx, *args):
    try:
        links = Schedule.get_link(*args)
        nospam = '>\n<'
        print(links)
        await ctx.send(f"<{nospam.join(links)}>")
    except:
        await ctx.send("You sure that course/link has been added?")
 
@bot.command(brief='Removes given link *****')
async def remove_link(ctx, *args):
    status = Schedule.remove_link(args[2])
    if status:
        await ctx.send(f"Link removed from {args[0]} {args[1]}")
    else:
        await ctx.send("Link not present.")

@bot.command(brief='Shows all registered courses')
async def show_all(ctx):
    for x in courses.find():  
        await ctx.send(x['name'] + '\n')
# Removes all courses and (maybe) all related collections
@bot.command(brief='Deregisters all courses. Use with caution!')
async def clear_database(ctx):
    await Schedule.remove_all()
    await ctx.send('Database cleared.')

@bot.command()
async def testcommand(ctx, arg1, arg2):
    print(arg1)

bot.run(BOT_TOKEN)