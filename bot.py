import discord
from discord.ext import commands, tasks
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json, selenium
import time
import requests
from datetime import datetime
import os
from concurrent.futures import ThreadPoolExecutor
import asyncio

executor = ThreadPoolExecutor()

# Configuration
COOKIES_DIR = r'.\cookies'

COOKIE_PATH = r'.\BotSteamComment\cookie.json'
TEMOIN = r'.\cookie_temoin.json'
PROFILES_PATH = r'.\profiles.json'
CHANNEL_ID = XXXXX
BOT_TOKEN = "UR TOKEN"  # Move token to environment variable or config file



class SteamBot:
    @staticmethod
    def update_profile_ban(profile_id, ban_hours):
        with open(PROFILES_PATH, 'r') as f:
            profiles = json.load(f)
        
        profiles[profile_id]['ban'] = ban_hours
        
        with open(PROFILES_PATH, 'w') as f:
            json.dump(profiles, f, indent=4)

    @staticmethod
    def check_login_status(driver):
        try:
            element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, "persona_name_text_content"))
            )
            return True
        except selenium.common.exceptions.TimeoutException:
            print("Login element not found - user likely not logged in")
            return False

    @staticmethod
    def check_comment(profile_id, comment_text):
        url = f'https://steamcommunity.com/profiles/{profile_id}/allcomments'
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers)
        
        profile_not_found_messages = [
            "<h3>Profil spécifié introuvable.</h3>",
            "<h3>The specified profile could not be found.</h3>"
        ]
        
        try:
            # First try the profile page directly to get the name
            profile_url = f'https://steamcommunity.com/profiles/{profile_id}'
            profile_response = requests.get(profile_url, headers=headers)
            
            start_marker = '<span class="actual_persona_name">'
            end_marker = '</span>'
            
            start_index = profile_response.text.find(start_marker) + len(start_marker)
            end_index = profile_response.text.find(end_marker, start_index)
            
            name = profile_response.text[start_index:end_index].strip()
            
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            name = profile_id
        
        if any(message in response.text for message in profile_not_found_messages):
            return True, f"⛔ Profile **{name}** = {profile_id} not found", name
        
        return comment_text in response.text, f"📝 Comment already exists for **{name}** = {profile_id}", name
    


    @staticmethod
    def format_cookies(cookies):
        for cookie in cookies:
            if 'sameSite' in cookie:
                cookie['sameSite'] = 'None' if cookie['sameSite'] == 'no_restriction' else 'Lax'
            else:
                cookie['sameSite'] = 'Lax'
        return cookies

    @staticmethod
    def post_comments():
        # Load profiles at startup
        with open(PROFILES_PATH, 'r') as f:
            profiles = json.load(f)
        results = []
        driver = None
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--disable-gpu")
            driver = webdriver.Chrome(options=chrome_options)

            with open(COOKIE_PATH, 'r') as f:
                cookies = SteamBot.format_cookies(json.load(f))

            driver.get('https://steamcommunity.com')

            i = 0
            for profile_id, data in profiles.items():

                for cookie in cookies:
                    driver.add_cookie(cookie)
                    
                results.append(f"\n")
                
                exists, message, name = SteamBot.check_comment(profile_id, data['keyword'])
                results.append(f"🔄 Processing profile: **{name}** = {profile_id}")
                if data['ban'] > 0 : 
                    SteamBot.update_profile_ban(profile_id, data['ban'] - 1)
                    message = f"⏳ Ban remaining: {data['ban'] - 1} h"
                    exists = True

                if not exists:
                    driver.get(f'https://steamcommunity.com/profiles/{profile_id}')
                    #time.sleep(500)
                    try:
                        comment_box = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CLASS_NAME, "commentthread_textarea"))
                        )
                        comment_box.send_keys(data['comment'])
                    except selenium.common.exceptions.TimeoutException:
                        if not SteamBot.check_login_status(driver):
                            results.append("⚠️ Not logged in - Invalid cookies. Please update cookies.")
                        else :
                            boolver, response = SteamBot.shadow_ban_check(driver, profile_id, name)
                            if boolver :
                                results.append(f"Confirmed Banned Account MAIN ,Check ok with this account")
                                success, message = SteamBot.try_post_with_alternate_cookies(driver, profile_id, name, data['comment'])
                                
                                if success:
                                    results.append(message)
                                    driver.delete_all_cookies()
                                    with open(COOKIE_PATH, 'r') as f:
                                        cookies = SteamBot.format_cookies(json.load(f))
                                    continue
                            else :
                                results.append(response)
                                driver.delete_all_cookies()
                                with open(COOKIE_PATH, 'r') as f:
                                    cookies = SteamBot.format_cookies(json.load(f))
                            
                        continue  # Skip to next profile

                    submit_button = driver.find_element(By.CSS_SELECTOR, 
                        ".btn_green_white_innerfade.btn_small[id*='commentthread_Profile_']")
                    submit_button.click()
                        # Wait for error message if it appears
                    time.sleep(2)  # Short wait for error message to appear
                    error_messages = [
                        "Vous avez posté trop souvent et ne pouvez envoyer de nouveaux messages pour le moment",
                        "You've been posting too frequently"
                    ]
                    
                    page_source = driver.page_source
                    if any(message in page_source for message in error_messages):
                        results.append(f"⏰ Rate limited: Too many comments posted recently for **{name}** = {profile_id}")
                        SteamBot.update_profile_ban(profile_id, 24)
                        continue

                    results.append(f"✉️ Comment posted for **{name}** = {profile_id} ✉️")
                    time.sleep(5)
                    i += 1
                    
                else:
                    results.append(message)
                    i += 1
                
        except Exception as e:
            results.append(f"❌ Error: {str(e)}")
        finally:
            if driver:
                driver.quit()
       
        return "\n".join(results)
    


    @staticmethod
    def shadow_ban_check(driver, profile_id, name):
        with open(TEMOIN, 'r') as f:
            cookies = SteamBot.format_cookies(json.load(f))
            
        # Clear existing cookies and add new ones
        driver.delete_all_cookies()
        for cookie in cookies:
            driver.add_cookie(cookie)
            
        driver.refresh()
        
        if SteamBot.check_login_status(driver):
            try:
                # Try posting comment with new cookies
                comment_box = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "commentthread_textarea"))
                )
                return True, f"🕵️‍♂️ Shadow Ban Check Confirmed 🔴"
            except selenium.common.exceptions.TimeoutException:
                return False, f"🚫 Comments are disabled on profile: **{name}** = {profile_id}"
                 
        return False, f"⚠️ **ACCOUNT TEMOIN** Not logged in - Invalid cookies. Please update cookies."


    @staticmethod
    def try_post_with_alternate_cookies(driver, profile_id, name, comment):
        message = ""
        for cookie_file in os.listdir(COOKIES_DIR):
            if not cookie_file.endswith('.json'):
                continue
                
            cookie_path = os.path.join(COOKIES_DIR, cookie_file)
            with open(cookie_path, 'r') as f:
                cookies = SteamBot.format_cookies(json.load(f))
                
            driver.delete_all_cookies()
            for cookie in cookies:
                driver.add_cookie(cookie)
                
            driver.refresh()
            driver.get(f'https://steamcommunity.com/profiles/{profile_id}')
            
            if SteamBot.check_login_status(driver):
                try:
                    comment_box = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "commentthread_textarea"))
                    )
                    comment_box.send_keys(comment)
                    submit_button = driver.find_element(By.CSS_SELECTOR, 
                        ".btn_green_white_innerfade.btn_small[id*='commentthread_Profile_']")
                    submit_button.click()
                    message += f"✉️ Comment posted with alternate account **{cookie_file.replace('.json', '')}** for **{name}** = {profile_id}"

                    return True, message
                except selenium.common.exceptions.TimeoutException:
                    continue
            else :
                message += f"⚠️ **{cookie_file.replace('.json', '')}** Not logged in - Invalid cookies. Please update cookies."
                continue

        message += f"❌ Unable to post comment with any account for **{name}** = {profile_id}"
        return False, message





# Discord Bot Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Bot is ready as {bot.user}')
    check_comments.start()

@tasks.loop(hours=1)
async def check_comments():
    channel = bot.get_channel(CHANNEL_ID)
    try:
        loop = asyncio.get_running_loop()
        # Attendez correctement le résultat de l'exécution dans l'executor
        results = await loop.run_in_executor(executor, SteamBot.post_comments)
        await channel.send(f"**Automatic check completed at {datetime.now()}**\n{results}")
    except Exception as e:
        await channel.send(f"Error during automatic check: {str(e)}")

@bot.command()
async def update_cookies(ctx):
    if not ctx.message.attachments:
        await ctx.send("Please attach a cookies.json file")
        return
    
    attachment = ctx.message.attachments[0]
    if attachment.filename.endswith('.json'):
        await attachment.save(COOKIE_PATH)
        await ctx.send("Cookies updated successfully!")

@bot.command()
async def update_profiles(ctx):
    if not ctx.message.attachments:
        await ctx.send("Please attach a profiles.json file")
        return
    
    attachment = ctx.message.attachments[0]
    if attachment.filename.endswith('.json'):
        await attachment.save(PROFILES_PATH)
        global profiles
        with open(PROFILES_PATH, 'r') as f:
            profiles = json.load(f)
        await ctx.send("Profiles updated successfully!")

@bot.command()
async def force_check(ctx):
    await ctx.send("Starting forced check...")
    try:
        results = SteamBot.post_comments()
        await ctx.send(f"Check completed:\n```ansi\n{results}```")
    except Exception as e:
        await ctx.send(f"Error during check: {str(e)}")

@bot.command()
async def show_profiles(ctx):
    formatted_profiles = json.dumps(profiles, indent=2)
    await ctx.send(f"Current profiles:\n```json\n{formatted_profiles}```")

# Run the bot
bot.run(BOT_TOKEN)
