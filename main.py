import os
import re
import io
import discord
import asyncio
import traceback
import pytz
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Select, Button, Modal, TextInput
from flask import Flask
import threading

# ==== 설정 ====
TOKEN = os.getenv("BOT_TOKEN")
CATEGORY_ID = 1398263224062836829
TICKET_CATEGORY_NAME = "⠐ 💳 = 이용하기"
LOG_CHANNEL_ID = 1398267597299912744
ADMIN_ROLE_ID = 1398271188291289138
OWNER_ROLE_ID = 1398268476933542018
MAX_LOG_MESSAGES = 1000
# ==============

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.members = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(ShopView())
        self.add_view(CloseTicketView())
        self.tree.add_command(shop_cmd)
        self.tree.add_command(reopen_cmd)
        self.tree.add_command(list_cmd)

bot = MyBot()
kst = pytz.timezone('Asia/Seoul')

# ---- Flask Keepalive ----
app = Flask(__name__)
@app.route('/')
def home():
    return "✅ Bot is running!"
def run_web():
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
def keep_alive():
    threading.Thread(target=run_web, daemon=True).start()

# ---------- Helpers ----------
def sanitize_channel_name(s: str) -> str:
    s = s.lower()
    s = re.sub(r'[^a-z0-9\-_ ]', '', s)
    s = s.replace(' ', '-')
    return s[:90]

async def save_channel_logs_and_send(channel: discord.TextChannel, log_channel: discord.TextChannel):
    try:
        msgs = []
        async for m in channel.history(limit=MAX_LOG_MESSAGES, oldest_first=True):
            timestamp = m.created_at.astimezone(kst).strftime("%Y-%m-%d %H:%M:%S")
            author = f"{m.author} ({m.author.id})"
            content = m.content or ""
            att_urls = " ".join(att.url for att in m.attachments) if m.attachments else ""
            msgs.append(f"[{timestamp}] {author}: {content} {att_urls}")
        txt = "\n".join(msgs) if msgs else "채팅 기록이 비어 있습니다."
        bio = io.BytesIO(txt.encode("utf-8"))
        bio.seek(0)
        await log_channel.send(file=discord.File(fp=bio, filename=f"ticket-log-{channel.name}.txt"))
    except Exception:
        traceback.print_exc()

async def lock_ticket_channel(channel: discord.TextChannel):
    try:
        overwrites = channel.overwrites
        for target in overwrites:
            if isinstance(target, discord.Member):
                overwrites[target].send_messages = False
        await channel.edit(overwrites=overwrites)
    except:
        traceback.print_exc()

# ---------- UI ----------
class ReasonModal(Modal, title="티켓 사유 입력"):
    def __init__(self, selected_item: str, interaction_user: discord.Member):
        super().__init__()
        self.selected_item = selected_item
        self.user = interaction_user

        self.reason = TextInput(
            label="사유",
            placeholder="티켓을 여는 이유를 입력하세요.",
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        category = guild.get_channel(CATEGORY_ID) or discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        if not category:
            category = await guild.create_category(TICKET_CATEGORY_NAME)

        base = f"ticket-{self.selected_item}-{self.user.name}-{self.user.id}"
        channel_name = sanitize_channel_name(base)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            self.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        admin_role = guild.get_role(ADMIN_ROLE_ID)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        owner_role = guild.get_role(OWNER_ROLE_ID)
        if owner_role:
            overwrites[owner_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        ticket_channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)

        guide_embed = discord.Embed(
            title=f"{self.selected_item} 티켓 생성됨",
            description=f"**사유:** {self.reason.value}\n\n담당자가 곧 응답합니다.",
            color=0x000000
        )
        await ticket_channel.send(embed=guide_embed, view=CloseTicketView())

        await interaction.response.send_message(f"✅ 티켓이 생성되었습니다: {ticket_channel.mention}", ephemeral=True)

class CloseTicketButton(Button):
    def __init__(self):
        super().__init__(label="티켓 닫기", style=discord.ButtonStyle.danger, custom_id="wind_close_ticket_v2")

    async def callback(self, interaction: discord.Interaction):
        channel = interaction.channel
        if not channel.name.startswith("ticket-"):
            await interaction.response.send_message("이 버튼은 티켓 채널에서만 사용 가능합니다.", ephemeral=True)
            return

        await interaction.response.send_message("티켓을 닫는 중입니다...", ephemeral=True)

        # 로그 저장
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await save_channel_logs_and_send(channel, log_channel)

        # 채널 잠금 + 이름 변경
        await lock_ticket_channel(channel)
        await channel.edit(name=f"closed-{channel.name}")

class CloseTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CloseTicketButton())

class ShopSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="🛒 구매하기", description="로블록스 아이템 또는 로벅스 구매")
        ]
        super().__init__(placeholder="원하는 항목을 선택하세요", options=options)

    async def callback(self, interaction: discord.Interaction):
        existing = [
            ch for ch in interaction.guild.text_channels
            if (ch.name.startswith("ticket-") or ch.name.startswith("closed-ticket-")) and interaction.user in ch.members
        ]
        if existing:
            await interaction.response.send_message(f"⚠ 이미 열린 티켓이 있습니다: {existing[0].mention}", ephemeral=True)
            return

        await interaction.response.send_modal(ReasonModal(self.values[0], interaction.user))

class ShopView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ShopSelect())

# ---------- Commands ----------
@app_commands.command(name="티켓", description="티켓 메뉴를 표시합니다.")
async def shop_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        description=(
            "**• <#1398260667768635392> 필독 부탁드립니다\n"
            "• <#1398261912852103208> 재고 확인하고 티켓 열기\n"
            "• 장난문의는 제재 당할 수도 있습니다\n"
            "• 티켓 열고 잠수 탈 시 하루 탐아 당할 수 있습니다**\n\n"
            "원하는 항목을 선택해 티켓을 생성하세요."
        ),
        color=0x000000
    )
    await interaction.response.send_message(embed=embed, view=ShopView())

@app_commands.command(name="티켓재오픈", description="닫힌 티켓을 다시 엽니다.")
async def reopen_cmd(interaction: discord.Interaction):
    channel = interaction.channel
    if not channel.name.startswith("closed-ticket-"):
        await interaction.response.send_message("이 명령어는 닫힌 티켓 채널에서만 사용 가능합니다.", ephemeral=True)
        return
    await channel.edit(name=channel.name.replace("closed-", ""), overwrites={
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    })
    await interaction.response.send_message("✅ 티켓이 다시 열렸습니다.", ephemeral=True)

@app_commands.command(name="티켓목록", description="현재 티켓 목록을 확인합니다.")
async def list_cmd(interaction: discord.Interaction):
    tickets = [ch.mention for ch in interaction.guild.text_channels if interaction.user in ch.members and (ch.name.startswith("ticket-") or ch.name.startswith("closed-ticket-"))]
    if not tickets:
        await interaction.response.send_message("현재 참여 중인 티켓이 없습니다.", ephemeral=True)
    else:
        await interaction.response.send_message("📋 참여 중인 티켓:\n" + "\n".join(tickets), ephemeral=True)

# ---------- Ready ----------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ 로그인됨: {bot.user}")

keep_alive()
bot.run(TOKEN)
