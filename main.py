import os
import re
import io
import discord
import asyncio
import traceback
import datetime
import pytz
from discord.ext import commands
from discord.ui import View, Select, Button
from flask import Flask
import threading

# ==== 설정 ====
TOKEN = os.getenv("BOT_TOKEN")
CATEGORY_ID = 1398263224062836829
TICKET_CATEGORY_NAME = "⠐ 💳 = 이용하기"
LOG_CHANNEL_ID = 1398267597299912744
ADMIN_ROLE_ID = 123456789012345678
OWNER_ROLE_ID = 987654321098765432
MAX_LOG_MESSAGES = 1000
# ==============

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
kst = pytz.timezone('Asia/Seoul')

# ---- keepalive (Flask) ----
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
            line = f"[{timestamp}] {author}: {content} {att_urls}"
            msgs.append(line)
        txt = "\n".join(msgs) if msgs else "채팅 기록이 비어 있습니다."
        bio = io.BytesIO(txt.encode("utf-8"))
        bio.seek(0)
        fname = f"ticket-log-{channel.name}.txt"
        await log_channel.send(content=f"🗂 티켓 로그: {channel.name}", file=discord.File(fp=bio, filename=fname))
    except Exception:
        traceback.print_exc()

# ---------- UI 컴포넌트 ----------
class CloseTicketButton(Button):
    def __init__(self):
        super().__init__(label="티켓 닫기", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="wind_close_ticket_v1")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        channel = interaction.channel
        if not channel or not channel.name.startswith("ticket-"):
            await interaction.followup.send("이 버튼은 티켓 채널에서만 사용할 수 있습니다.", ephemeral=True)
            return

        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        try:
            if log_channel:
                await log_channel.send(embed=discord.Embed(
                    title="티켓 닫힘 (예정)",
                    description=f"채널 `{channel.name}`이(가) 닫힙니다. 로그를 저장합니다...",
                    color=0x000000
                ))
                await save_channel_logs_and_send(channel, log_channel)
        except Exception:
            traceback.print_exc()

        try:
            await channel.delete()
        except Exception as e:
            traceback.print_exc()
            if log_channel:
                await log_channel.send(embed=discord.Embed(
                    title="티켓 채널 삭제 실패",
                    description=f"채널 `{channel.name}` 삭제 중 오류가 발생했습니다:\n```\n{e}\n```",
                    color=discord.Color.red()
                ))

class ShopSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="구매하기", description="로블록스 아이템 또는 로벅스 구매", emoji="🛒"),
            discord.SelectOption(label="문의하기", description="문의사항 티켓 열기", emoji="🎫"),
            discord.SelectOption(label="파트너 & 상단배너", description="파트너 또는 상단배너 문의", emoji="👑")
        ]
        super().__init__(placeholder="원하는 항목을 선택하세요", options=options, custom_id="wind_shop_select_v1")

    async def callback(self, interaction: discord.Interaction):
        selected_item = self.values[0]
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("길드 정보가 없습니다.", ephemeral=True)
            return

        category = None
        try:
            if CATEGORY_ID:
                category = guild.get_channel(int(CATEGORY_ID))
                if category and not isinstance(category, discord.CategoryChannel):
                    category = None
        except Exception:
            category = None

        if not category:
            category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
            if not category:
                try:
                    category = await guild.create_category(TICKET_CATEGORY_NAME)
                except Exception:
                    category = None

        def user_has_ticket_channel():
            uname = interaction.user.name.lower()
            uid = str(interaction.user.id)
            for ch in guild.channels:
                if not isinstance(ch, discord.TextChannel):
                    continue
                cname = ch.name.lower()
                if cname.startswith("ticket-") and (uname in cname or uid in cname or ch.permissions_for(interaction.user).read_messages):
                    return ch
            return None

        existing_channel = user_has_ticket_channel()
        if existing_channel:
            try:
                await interaction.followup.send(f"⚠ 이미 티켓이 존재합니다: {existing_channel.mention}", ephemeral=True)
            except Exception:
                await interaction.followup.send("⚠ 이미 티켓이 존재합니다 (채널을 표시할 수 없음).", ephemeral=True)
            return

        base = f"ticket-{selected_item}-{interaction.user.name}-{interaction.user.id}"
        channel_name = sanitize_channel_name(base)

        if discord.utils.get(guild.channels, name=channel_name):
            channel_name = sanitize_channel_name(f"{channel_name}-{int(datetime.datetime.now().timestamp())}")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        try:
            if ADMIN_ROLE_ID:
                admin_role = guild.get_role(int(ADMIN_ROLE_ID))
                if admin_role:
                    overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            if OWNER_ROLE_ID:
                owner_role = guild.get_role(int(OWNER_ROLE_ID))
                if owner_role:
                    overwrites[owner_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        except Exception:
            traceback.print_exc()

        try:
            ticket_channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send("채널 생성 중 오류가 발생했습니다. 관리자에게 문의하세요.", ephemeral=True)
            log_ch = bot.get_channel(LOG_CHANNEL_ID)
            if log_ch:
                await log_ch.send(embed=discord.Embed(title="티켓 채널 생성 실패", description=str(e), color=discord.Color.red()))
            return

        guide_embed = discord.Embed(
            title=f"{selected_item} 티켓 생성됨",
            description="💬 담당자가 곧 응답할 예정입니다.\n아래 버튼을 눌러 티켓을 닫을 수 있습니다.",
            color=0x000000
        ).set_footer(text="WIND Ticket Bot")
        try:
            await ticket_channel.send(embed=guide_embed, view=View().add_item(CloseTicketButton()))
        except Exception:
            traceback.print_exc()

        try:
            await interaction.followup.send(f"✅ `{selected_item}` 티켓이 생성되었습니다: {ticket_channel.mention}", ephemeral=True)
        except Exception:
            await interaction.channel.send("✅ 티켓이 생성되었습니다.")

        try:
            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(embed=discord.Embed(
                    title="📥 티켓 생성",
                    description=f"**채널:** {ticket_channel.mention}\n**생성자:** {interaction.user.mention} ({interaction.user.id})\n**항목:** `{selected_item}`",
                    color=0x000000
                ))
        except Exception:
            traceback.print_exc()

class ShopView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ShopSelect())

# ---------- 커맨드 ----------
@bot.command(name="상점")
async def shop_cmd(ctx: commands.Context):
    embed = discord.Embed(
        title="구매하기",
        description="구매 또는 문의를 원하시면\n아래 선택하기 버튼을 눌려주세요",
        color=0x000000
    )
    view = ShopView()
    try:
        await ctx.send(embed=embed, view=view)
    except Exception:
        await ctx.send("임베드 전송 실패 — 권한을 확인하세요.")
        return
    try:
        bot.add_view(view)
    except Exception:
        pass

# ---------- on_ready ----------
@bot.event
async def on_ready():
    try:
        bot.add_view(ShopView())
    except Exception:
        pass
    print(f"✅ 로그인됨: {bot.user} (ID: {bot.user.id})")

# 실행
keep_alive()
bot.run(TOKEN)
