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

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Persistent View 등록
        self.add_view(ShopView())
        self.add_view(CloseTicketView())
        print("✅ Persistent views registered.")

bot = MyBot()
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
        try:
            await interaction.response.send_message("티켓을 닫는 중입니다...", ephemeral=True)
        except discord.InteractionResponded:
            pass

        channel = interaction.channel
        if not channel or not channel.name.startswith("ticket-"):
            await interaction.followup.send("이 버튼은 티켓 채널에서만 사용할 수 있습니다.", ephemeral=True)
            return

        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        try:
            if log_channel:
                await log_channel.send(embed=discord.Embed(
                    title="티켓 닫힘 (예정)",
                    description=f"채널 `{channel.name}`이 로그 저장 후 닫힙니다.",
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
                    description=f"채널 `{channel.name}` 삭제 중 오류:\n```\n{e}\n```",
                    color=discord.Color.red()
                ))

class CloseTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CloseTicketButton())

class ShopSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="구매하기", description="로블록스 아이템 또는 로벅스 구매", emoji="🛒"),
            discord.SelectOption(label="문의하기", description="문의사항 티켓 열기", emoji="🎫"),
            discord.SelectOption(label="파트너 & 상단배너", description="파트너 또는 상단배너 문의", emoji="👑")
        ]
        super().__init__(
            placeholder="티켓 항목 선택",  # 요청하신 placeholder 그대로
            options=options,
            custom_id="wind_shop_select_v1"
        )

    async def callback(self, interaction: discord.Interaction):
        selected_item = self.values[0]
        await interaction.response.defer()
        guild = interaction.guild
        if not guild:
            return

        category = guild.get_channel(CATEGORY_ID) if CATEGORY_ID else None
        if not isinstance(category, discord.CategoryChannel):
            category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
            if not category:
                try:
                    category = await guild.create_category(TICKET_CATEGORY_NAME)
                except:
                    category = None

        base = f"ticket-{selected_item}-{interaction.user.name}-{interaction.user.id}"
        channel_name = sanitize_channel_name(base)

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

        guide_embed = discord.Embed(
            title=f"{selected_item} 티켓 생성됨",
            description="담당자가 곧 응답합니다.\n아래 버튼으로 티켓을 닫을 수 있습니다.",
            color=0x000000
        ).set_footer(text="WIND Ticket Bot")
        await ticket_channel.send(embed=guide_embed, view=CloseTicketView())

        mentions = []
        if admin_role:
            mentions.append(admin_role.mention)
        if owner_role:
            mentions.append(owner_role.mention)
        mentions.append(interaction.user.mention)

        await ticket_channel.send(
            f"{' '.join(mentions)} 티켓이 생성되었습니다.",
            allowed_mentions=discord.AllowedMentions(roles=True, users=True)
        )

        await interaction.followup.send(f"✅ `{selected_item}` 티켓이 생성되었습니다: {ticket_channel.mention}", ephemeral=True)
        await interaction.message.edit(view=ShopView())

        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(embed=discord.Embed(
                title="📥 티켓 생성",
                description=f"채널: {ticket_channel.mention}\n생성자: {interaction.user.mention} ({interaction.user.id})\n항목: `{selected_item}`",
                color=0x000000
            ))

class ShopView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ShopSelect())

@bot.command(name="상점")
async def shop_cmd(ctx: commands.Context):
    embed = discord.Embed(
        description="아래 드롭다운중 하나를 선택해 티켓을 열어주세요.\n\n티켓에서 맨션시 티켓답습니다",
        color=0x000000
    )
    await ctx.send(embed=embed, view=ShopView())

@bot.event
async def on_ready():
    print(f"✅ 로그인됨: {bot.user} (ID: {bot.user.id})")

keep_alive()
bot.run(TOKEN)
