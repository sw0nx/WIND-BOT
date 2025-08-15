import os
import io
import discord
import pytz
import traceback
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Select, Button
from flask import Flask
import threading

# ==== 설정 ====
TOKEN = os.getenv("BOT_TOKEN")
CATEGORY_ID = 1398263224062836829
TICKET_CATEGORY_NAME = "이용하기"
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
        self.tree.add_command(list_cmd)

bot = MyBot()
kst = pytz.timezone('Asia/Seoul')

# ---- Flask Keepalive ----
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is running!"
def run_web():
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
def keep_alive():
    threading.Thread(target=run_web, daemon=True).start()

# ---------- Helpers ----------
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

# ---------- UI ----------
class CloseTicketButton(Button):
    def __init__(self):
        super().__init__(label="티켓 닫기", style=discord.ButtonStyle.danger, custom_id="close_ticket_v2")

    async def callback(self, interaction: discord.Interaction):
        channel = interaction.channel
        if not channel.name.startswith("ticket-"):
            await interaction.response.send_message("이 버튼은 티켓 채널에서만 사용 가능합니다.", ephemeral=True)
            return

        await interaction.response.send_message("티켓을 닫는 중입니다...", ephemeral=True)

        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await save_channel_logs_and_send(channel, log_channel)

        await channel.delete(reason="티켓 닫기")

class CloseTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CloseTicketButton())

class ShopSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="구매하기", description="로블록스 아이템 또는 로벅스 구매")
        ]
        super().__init__(placeholder="원하는 항목을 선택하세요", options=options, custom_id="shop_select_v2")

    async def callback(self, interaction: discord.Interaction):
        existing = [
            ch for ch in interaction.guild.text_channels
            if (ch.name.startswith("ticket-")) and interaction.user in ch.members
        ]
        if existing:
            await interaction.response.send_message(f"이미 열린 티켓이 있습니다: {existing[0].mention}", ephemeral=True)
            return

        guild = interaction.guild
        category = guild.get_channel(CATEGORY_ID) or discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        if not category:
            category = await guild.create_category(TICKET_CATEGORY_NAME)

        # 유저 이름 그대로 표시
        channel_name = f"ticket-{interaction.user.display_name}-구매하기"

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        admin_role = guild.get_role(ADMIN_ROLE_ID)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        owner_role = guild.get_role(OWNER_ROLE_ID)
        if owner_role:
            overwrites[owner_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        ticket_channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)

        # 안내 임베드
        guide_embed = discord.Embed(
            description=(
                "구매 원하는 아이템을 미리 적어주세요.\n"
                "그래야 빠른 처리가 가능합니다."
            ),
            color=0x000000
        )
        await ticket_channel.send(embed=guide_embed, view=CloseTicketView())

        await interaction.response.send_message(f"티켓이 생성되었습니다: {ticket_channel.mention}", ephemeral=True)

        # 선택 UI 초기화
        self.view.clear_items()
        self.view.add_item(ShopSelect())
        await interaction.message.edit(view=self.view)

class ShopView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ShopSelect())

# ---------- Commands ----------
def owner_only():
    async def predicate(interaction: discord.Interaction):
        role = interaction.guild.get_role(OWNER_ROLE_ID)
        if role and role in interaction.user.roles:
            return True
        await interaction.response.send_message("이 명령어는 서버 오너만 사용할 수 있습니다.", ephemeral=True)
        return False
    return app_commands.check(predicate)

@app_commands.command(name="티켓")
@owner_only()
async def shop_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="티켓 안내",
        description=(
            "**• <#1398260667768635392> 필독 부탁드립니다\n"
            "• <#1398261912852103208> 재고 확인하고 티켓 열기\n"
            "• 장난문의는 제재 당할 수도 있습니다\n"
            "• 티켓 열고 잠수 탈 시 하루 탐아 당할 수 있습니다**"
        ),
        color=0x000000
    )
    await interaction.response.send_message(embed=embed, view=ShopView())

@app_commands.command(name="티켓목록")
@owner_only()
async def list_cmd(interaction: discord.Interaction):
    tickets = [ch.mention for ch in interaction.guild.text_channels if interaction.user in ch.members and ch.name.startswith("ticket-")]
    if not tickets:
        await interaction.response.send_message("현재 참여 중인 티켓이 없습니다.", ephemeral=True)
    else:
        await interaction.response.send_message("\n".join(tickets), ephemeral=True)

# ---------- Ready ----------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"로그인됨: {bot.user}")

keep_alive()
bot.run(TOKEN)
