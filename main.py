import os
import re
import io
import discord
import traceback
import pytz
from discord import app_commands
from discord.ext import commands
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
intents.message_content = True
intents.guilds = True
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
        await log_channel.send(content=f"티켓 로그: {channel.name}", file=discord.File(fp=bio, filename=fname))
    except Exception:
        traceback.print_exc()

# ---------- 티켓 생성 ----------
async def create_ticket(interaction: discord.Interaction, selected_item: str):
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

    # 안내 메시지
    guide_embed = discord.Embed(
        title=f"{selected_item} 티켓 생성됨",
        description="담당자가 곧 응답합니다\n아래 버튼으로 티켓을 닫을 수 있습니다",
        color=0x000000
    ).set_footer(text="WIND Ticket Bot")

    close_button = {
        "type": 2,
        "style": 4,
        "label": "티켓 닫기",
        "emoji": {"name": "🔒"},
        "custom_id": "close_ticket"
    }

    await ticket_channel.send(
        embeds=[guide_embed],
        components=[[close_button]]
    )

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

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(embed=discord.Embed(
            title="티켓 생성",
            description=f"채널: {ticket_channel.mention}\n생성자: {interaction.user.mention} ({interaction.user.id})\n항목: `{selected_item}`",
            color=0x000000
        ))

# ---------- Select 메뉴 이벤트 ----------
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        if interaction.data.get("custom_id") == "ticket_select_v2":
            selected_item = interaction.data["values"][0]
            await interaction.response.defer(ephemeral=True)
            await create_ticket(interaction, selected_item)

        elif interaction.data.get("custom_id") == "close_ticket":
            await interaction.response.send_message("티켓을 닫는 중입니다...", ephemeral=True)
            try:
                log_channel = bot.get_channel(LOG_CHANNEL_ID)
                if log_channel:
                    await save_channel_logs_and_send(interaction.channel, log_channel)
                await interaction.channel.delete()
            except Exception:
                traceback.print_exc()

# ---------- /티켓 명령어 ----------
@app_commands.command(name="티켓", description="티켓 안내 메시지를 보냅니다")
async def ticket_cmd(interaction: discord.Interaction):
    components_v2 = [
        {
            "type": 1,  # Container
            "components": [
                {
                    "type": 2,  # Section
                    "components": [
                        {
                            "type": 3,  # TextDisplay
                            "text": "아래 드롭다운중 하나를 선택해 티켓을 열어주세요.\n티켓에서 맨션시 티켓답습니다"
                        },
                        { "type": 4 },  # Separator
                        {
                            "type": 5,  # ActionRow
                            "components": [
                                {
                                    "type": 6,  # StringSelectMenu
                                    "custom_id": "ticket_select_v2",
                                    "placeholder": "티켓 항목 선택",
                                    "options": [
                                        {
                                            "value": "ticket"  # 라벨, 설명, 이모지 없이 값만
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ]

    await interaction.response.send_message(
        components=components_v2,
        flags=discord.MessageFlags.is_components_v2()
    )

# ---------- 봇 실행 ----------
@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"✅ 슬래시 명령어 동기화 완료: {len(synced)}개")
    except Exception as e:
        print(f"명령어 동기화 실패: {e}")
    print(f"✅ 로그인됨: {bot.user} (ID: {bot.user.id})")

bot.tree.add_command(ticket_cmd)

keep_alive()
bot.run(TOKEN)
